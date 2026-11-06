"""判讀模型斷路器：滿載太多次換備援、隔一陣子試探、其他錯誤不換模型（離線、零點數）。"""
import pytest
import requests

from app.config import settings
from app.services import model_breaker
from app.services.ai_service import AIService


class _Resp:
    def __init__(self, status, text=""):
        self.status_code = status
        self.text = text


def _http_error(status, text=""):
    return requests.exceptions.HTTPError(f"HTTP {status}", response=_Resp(status, text))


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    model_breaker.reset()
    monkeypatch.setattr(settings, "BREAKER_FAILURE_THRESHOLD", 3)
    monkeypatch.setattr(settings, "BREAKER_WINDOW_SECONDS", 120)
    monkeypatch.setattr(settings, "BREAKER_PROBE_SECONDS", 300)
    yield
    model_breaker.reset()


def _service(monkeypatch, behaviour):
    """behaviour: {model: 例外或結果 dict 或 callable}；回傳 (service, 被呼叫的模型清單)。"""
    svc = AIService.__new__(AIService)
    svc.cgu_base, svc.cgu_key = "http://x", "k"
    svc.cgu_model, svc.cgu_fallback_model = "primary", "backup"
    calls = []

    def fake(self, **kw):
        calls.append(kw["model"])
        b = behaviour[kw["model"]]
        if callable(b):
            b = b()
        if isinstance(b, BaseException):
            raise b
        return b

    monkeypatch.setattr(AIService, "_responses_analyze", fake)
    return svc, calls


def test_is_overload_classification():
    assert model_breaker.is_overload(requests.exceptions.ReadTimeout())
    assert model_breaker.is_overload(_http_error(503))
    assert model_breaker.is_overload(_http_error(502))
    assert model_breaker.is_overload(_http_error(429, '{"error":{"code":"queue_timeout"}}'))
    assert not model_breaker.is_overload(_http_error(429, '{"error":{"code":"insufficient_quota"}}'))
    assert not model_breaker.is_overload(_http_error(401, "invalid_api_key"))
    assert not model_breaker.is_overload(_http_error(403, "model_not_allowed"))


def test_overload_in_one_request_falls_to_backup(monkeypatch):
    svc, calls = _service(monkeypatch, {"primary": _http_error(503), "backup": {"ok": 1}})
    assert svc._cgu_analyze("t", None, False) == {"ok": 1}
    assert calls == ["primary", "backup"]


def test_breaker_opens_after_threshold_and_skips_primary(monkeypatch):
    svc, calls = _service(monkeypatch, {"primary": _http_error(503), "backup": {"ok": 1}})
    for _ in range(3):
        svc._cgu_analyze("t", None, False)
    assert model_breaker.is_open("primary")
    calls.clear()
    svc._cgu_analyze("t", None, False)
    assert calls == ["backup"]   # 斷路中：不再打主模型


def test_probe_lets_one_request_through_and_success_closes(monkeypatch):
    svc, calls = _service(monkeypatch, {"primary": _http_error(503), "backup": {"ok": 1}})
    for _ in range(3):
        svc._cgu_analyze("t", None, False)
    # 剛斷路：等滿 PROBE 秒才放第一個試探
    assert model_breaker.allow_request("primary") is False
    monkeypatch.setattr(settings, "BREAKER_PROBE_SECONDS", 0)
    assert model_breaker.allow_request("primary") is True
    monkeypatch.setattr(settings, "BREAKER_PROBE_SECONDS", 300)
    assert model_breaker.allow_request("primary") is False   # 剛放過一個，下一個要再等
    # 主模型恢復：試探成功就關閉斷路器
    monkeypatch.setattr(AIService, "_responses_analyze", lambda self, **kw: {"ok": kw["model"]})
    monkeypatch.setattr(settings, "BREAKER_PROBE_SECONDS", 0)
    assert svc._cgu_analyze("t", None, False) == {"ok": "primary"}
    assert not model_breaker.is_open("primary")


def test_non_overload_errors_do_not_switch_model(monkeypatch):
    for err in (_http_error(401, "invalid_api_key"), _http_error(429, "insufficient_quota"), _http_error(403, "model_not_allowed")):
        model_breaker.reset()
        svc, calls = _service(monkeypatch, {"primary": err, "backup": {"ok": 1}})
        with pytest.raises(requests.exceptions.HTTPError):
            svc._cgu_analyze("t", None, False)
        assert calls == ["primary"]
        assert not model_breaker.is_open("primary")


def test_model_missing_still_falls_back(monkeypatch):
    svc, calls = _service(monkeypatch, {"primary": _http_error(400, '{"error":{"code":"model_not_found"}}'), "backup": {"ok": 1}})
    assert svc._cgu_analyze("t", None, False) == {"ok": 1}
    assert calls == ["primary", "backup"]


def test_both_overloaded_raises_last(monkeypatch):
    svc, calls = _service(monkeypatch, {"primary": requests.exceptions.ReadTimeout(), "backup": _http_error(503)})
    with pytest.raises(requests.exceptions.HTTPError):
        svc._cgu_analyze("t", None, False)
    assert calls == ["primary", "backup"]


def test_failures_expire_after_window(monkeypatch):
    for _ in range(3):
        model_breaker.record_failure("primary", "HTTP 503")
    assert model_breaker.is_open("primary")
    monkeypatch.setattr(settings, "BREAKER_WINDOW_SECONDS", 0)
    assert not model_breaker.is_open("primary")


def test_status_shape():
    model_breaker.record_failure("primary", "HTTP 503")
    s = model_breaker.status(["primary", "backup"])
    assert s["primary"] == {"open": False, "recent_failures": 1, "last_reason": "HTTP 503"}
    assert s["backup"]["recent_failures"] == 0
