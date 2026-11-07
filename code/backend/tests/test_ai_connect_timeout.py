"""判讀呼叫連線卡住（學校主機對校外偶爾連不上）：連線最多等 AI_CONNECT_TIMEOUT_SECONDS，
換新連線重試 AI_CONNECT_RETRIES 次，再不行才換備援模型。讀取逾時不重試。離線、零點數。"""
import json as _json

import pytest
import requests

import app.services.ai_service as ai_mod
from app.services import model_breaker
from app.services.ai_service import AIService

PAYLOAD = {"is_risk": True, "risk_type": "SCAM", "category": "Phishing",
           "confidence_score": 0.9, "summary": "s", "explanation": "e", "sources": []}


class _Resp:
    def raise_for_status(self):
        pass

    def json(self):
        return {"output": [{"type": "message", "content": [
            {"type": "output_text", "text": _json.dumps(PAYLOAD)}]}]}


@pytest.fixture(autouse=True)
def _settings(monkeypatch):
    model_breaker.reset()
    monkeypatch.setattr(ai_mod.settings, "AI_TIMEOUT_SECONDS", 60)
    monkeypatch.setattr(ai_mod.settings, "AI_CONNECT_TIMEOUT_SECONDS", 5.0)
    monkeypatch.setattr(ai_mod.settings, "AI_CONNECT_RETRIES", 1)
    monkeypatch.setattr(ai_mod.settings, "BREAKER_FAILURE_THRESHOLD", 3)
    yield
    model_breaker.reset()


def _cgu_service():
    svc = AIService()
    svc.providers = ["cgu"]
    svc.cgu_base, svc.cgu_key = "https://cgu.invalid/v1", "k"
    svc.cgu_model, svc.cgu_fallback_model = "primary", "backup"
    return svc


def _fake_gateway(monkeypatch, plan):
    """plan[model] = 依序要丟的例外（用完就正常回應）；連線逾時時鐘前進連線上限，其他錯誤前進 10 秒。"""
    clock = {"now": 1000.0}
    calls = []
    monkeypatch.setattr(ai_mod.time, "monotonic", lambda: clock["now"])

    def _post(url, headers=None, json=None, timeout=None):
        calls.append((json["model"], timeout, clock["now"] - 1000.0))
        queue = plan.get(json["model"], [])
        if queue:
            exc = queue.pop(0)
            clock["now"] += timeout[0] if isinstance(exc, requests.exceptions.ConnectTimeout) else 10.0
            raise exc
        return _Resp()

    monkeypatch.setattr(ai_mod.requests, "post", _post)
    return calls


def test_request_timeout_caps_connect_separately_from_read():
    assert ai_mod._request_timeout() == (5.0, 60.0)
    ai_mod._deadline_local.deadline = ai_mod.time.monotonic() + 3.0
    try:
        connect, read = ai_mod._request_timeout()
        assert connect <= read <= 3.0   # 都不超過剩餘預算
    finally:
        ai_mod._deadline_local.deadline = None


def test_connect_timeout_retries_on_a_new_connection(monkeypatch):
    calls = _fake_gateway(monkeypatch, {"primary": [requests.exceptions.ConnectTimeout("syn dropped")]})
    result = _cgu_service()._run_analysis("prompt", use_web_search=False)
    assert result["model"] == "primary" and result["risk_type"] == "SCAM"
    assert [c[0] for c in calls] == ["primary", "primary"]
    assert calls[0][1] == (5.0, 60.0)
    assert not model_breaker.status(["primary"])["primary"]["recent_failures"]   # 重試成功不算主模型失敗


def test_connect_stuck_twice_moves_to_backup_within_seconds(monkeypatch):
    stuck = [requests.exceptions.ConnectTimeout("syn dropped"), requests.exceptions.ConnectTimeout("syn dropped")]
    calls = _fake_gateway(monkeypatch, {"primary": stuck})
    result = _cgu_service()._run_analysis("prompt", use_web_search=False)
    assert result["model"] == "backup"
    assert [c[0] for c in calls] == ["primary", "primary", "backup"]
    assert calls[2][2] <= 10.0   # 換備援前最多等 2 × 5 秒，不是等滿 60 秒
    assert model_breaker.status(["primary"])["primary"]["recent_failures"] == 1


def test_read_timeout_is_not_retried_on_the_same_model(monkeypatch):
    calls = _fake_gateway(monkeypatch, {"primary": [requests.exceptions.ReadTimeout("slow")]})
    result = _cgu_service()._run_analysis("prompt", use_web_search=False)
    assert result["model"] == "backup"
    assert [c[0] for c in calls] == ["primary", "backup"]   # 已經等滿，閘道也可能已經在算，不再送一次


def test_no_retry_when_budget_is_spent(monkeypatch):
    monkeypatch.setattr(ai_mod.settings, "AI_TIMEOUT_SECONDS", 4)
    calls = _fake_gateway(monkeypatch, {"primary": [requests.exceptions.ConnectTimeout("syn dropped")]})
    result = _cgu_service()._run_analysis("prompt", use_web_search=False)
    assert result["summary"].startswith("AI 分析暫時無法使用")
    assert [c[0] for c in calls] == ["primary"]


def test_complete_json_retries_a_connect_timeout(monkeypatch):
    calls = _fake_gateway(monkeypatch, {"gemma": [requests.exceptions.ConnectTimeout("syn dropped")]})
    svc = _cgu_service()
    assert svc.complete_json("提示", model="gemma", timeout=7) == PAYLOAD
    assert [c[0] for c in calls] == ["gemma", "gemma"]
    assert calls[0][1] == (5.0, 7.0)
