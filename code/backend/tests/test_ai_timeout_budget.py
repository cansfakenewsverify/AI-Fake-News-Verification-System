"""B-09：AI_TIMEOUT_SECONDS 是整條 provider fallback 鏈的 wall-clock 總預算（spec §9）。離線、零點數。"""
import app.services.ai_service as ai_mod
from app.services.ai_service import AIService


def _svc():
    svc = AIService()
    svc.providers = ["cgu", "openai", "claude"]
    svc.cgu_base, svc.cgu_key, svc.cgu_model = "https://cgu.invalid/v1", "k", "m"
    svc.openai_base, svc.myai_key, svc.openai_model = "https://openai.invalid/v1", "k", "m"
    svc.claude_base, svc.claude_model = "https://claude.invalid/v1", "m"
    return svc


def test_request_timeout_never_exceeds_setting(monkeypatch):
    monkeypatch.setattr(ai_mod.settings, "AI_TIMEOUT_SECONDS", 60)
    seen = []

    def _fake_post(url, headers=None, json=None, timeout=None):
        seen.append(timeout)
        raise ai_mod.requests.exceptions.ConnectionError("offline")

    monkeypatch.setattr(ai_mod.requests, "post", _fake_post)
    result = _svc()._run_analysis("prompt", use_web_search=False)
    assert result["summary"].startswith("AI 分析暫時無法使用")
    assert seen and all(0 < t <= 60 for t in seen)
    assert getattr(ai_mod._deadline_local, "deadline", None) is None


def test_chain_stops_when_total_budget_spent(monkeypatch):
    monkeypatch.setattr(ai_mod.settings, "AI_TIMEOUT_SECONDS", 60)
    clock = {"now": 1000.0}
    monkeypatch.setattr(ai_mod.time, "monotonic", lambda: clock["now"])
    calls = []

    def _fake_post(url, headers=None, json=None, timeout=None):
        calls.append((url, timeout))
        clock["now"] += 61  # 第一個 provider 就把 60 s 預算用完
        raise ai_mod.requests.exceptions.ReadTimeout("slow")

    monkeypatch.setattr(ai_mod.requests, "post", _fake_post)
    result = _svc()._run_analysis("prompt", use_web_search=True)
    assert len(calls) == 1  # 不再嘗試 openai / claude / no-search 重試
    assert calls[0][1] == 60
    assert result["summary"].startswith("AI 分析暫時無法使用")
