"""AI 服務的解析與 fallback 契約測試（不呼叫任何外部 API）。"""
import pytest

from app.services.ai_service import AIService, _default_fallback_result
from app.services.threads_service import format_verdict_reply, THREADS_TEXT_LIMIT, threads_len
from app.utils.verdict import frame_of
from app.utils.verdict import is_fallback as _is_fallback
from app.workers.pandas_task_processor import _build_result


# ── JSON 鬆散解析 ─────────────────────────────────────────────
def test_parse_json_loose_plain_and_fenced():
    assert AIService._parse_json_loose('{"a": 1}') == {"a": 1}
    assert AIService._parse_json_loose('```json\n{"a": 1}\n```') == {"a": 1}
    assert AIService._parse_json_loose('前置說明 {"a": 1} 後置') == {"a": 1}


def test_parse_json_loose_invalid_raises():
    with pytest.raises(Exception):
        AIService._parse_json_loose("完全不是 JSON")


def test_validate_result_missing_field_raises():
    svc = AIService()
    with pytest.raises(ValueError):
        svc._validate_result({"is_risk": True})  # 缺其他必要欄位


def test_validate_result_bad_risk_type_coerced_to_safe():
    svc = AIService()
    r = {
        "is_risk": False, "risk_type": "WEIRD", "category": "Safe",
        "confidence_score": 0.5, "summary": "s", "explanation": "e", "sources": [],
    }
    svc._validate_result(r)
    assert r["risk_type"] == "SAFE"


# ── fallback 契約：三個前端靠這個字樣辨識，改字樣要三處一起改 ──
def test_fallback_summary_prefix_is_stable():
    res = _default_fallback_result("測試錯誤")
    assert res["summary"].startswith("AI 分析暫時無法使用")
    assert res["risk_type"] == "SAFE"
    assert res["confidence_score"] == 0.0
    assert _is_fallback(res)                      # 任務處理器不會快取它
    assert not _is_fallback(
        {"summary": "正常摘要", "risk_type": "SCAM"}
    )


# ── 紅黃綠框與信心等級 ────────────────────────────────────────
def test_frame_mapping():
    # spec §7.8 八列（FN-1 允許改寫）：統一由 verdict.frame_of 判定
    rows = [
        ({"ai_unavailable": True, "is_risk": True, "risk_type": "SCAM"}, ("grey", "AI 暫時無法使用")),
        ({"is_risk": False, "risk_type": "UNVERIFIABLE"}, ("yellow", "無法查證")),
        ({"is_risk": True, "risk_type": "SCAM", "confidence_score": 0.9}, ("red", "詐騙警告")),
        ({"is_risk": True, "risk_type": "MISINFO", "confidence_score": 0.9}, ("red", "假訊息")),
        ({"is_risk": True, "risk_type": "UNKNOWN", "confidence_score": 0.9}, ("red", "風險訊息")),
        ({"is_risk": False, "risk_type": "SAFE", "confidence_score": 0.9,
          "verification_status": "unverified"}, ("yellow", "尚無查核機構證實")),
        ({"is_risk": False, "risk_type": "SAFE", "confidence_score": 0.9,
          "verification_status": "verified"}, ("green", "查無異常")),
        ({"is_risk": False, "risk_type": "SAFE", "confidence_score": 0.3,
          "verification_status": "verified"}, ("yellow", "尚待確認")),
    ]
    for result, expected in rows:
        assert frame_of(result)[:2] == expected


def test_confidence_level_no_longer_follows_the_model_self_score():
    # 信心改依證據（app/services/evidence.py）：AI 自評 0.99、沒有任何證據 → 低（只有 AI 判斷）
    result = _build_result({"is_risk": True, "risk_type": "SCAM", "confidence_score": 0.99,
                            "summary": "s", "explanation": "e", "sources": []})
    assert (result["confidence_level"], result["confidence_basis"]) == ("低", "ai_only")
    assert result["confidence_score"] == 0.99          # 原始自評仍保留在欄位裡供稽核


def test_build_result_reports_cache_layer():
    ai = {"is_risk": True, "risk_type": "SCAM", "category": "Investment",
          "confidence_score": 0.9, "summary": "s", "explanation": "e", "sources": []}
    hit = _build_result(ai, cached=True, cache_layer="vector")
    assert hit["cached"] is True and hit["cache_layer"] == "vector"
    miss = _build_result(ai, cached=False)
    assert miss["cached"] is False and miss["cache_layer"] is None


# ── Threads 回覆格式（spec 7.7 模板；完整案例見 test_threads_reply_format.py）──
def test_threads_reply_within_limit_and_has_verdict():
    result = {
        "is_risk": True, "risk_type": "SCAM", "confidence_score": 0.95,
        "verification_status": "verified",
        "summary": "假冒銀行釣魚簡訊" * 40,  # 刻意超長
        "sources": [{"title": "165", "url": "https://www.mygopen.com/2026/01/a.html", "tier": 1}],
    }
    reply = format_verdict_reply(result, "https://demo.example.app/r/t1")
    assert threads_len(reply) <= THREADS_TEXT_LIMIT
    lines = reply.split("\n")
    assert lines[0] == "\U0001F534 詐騙警告"
    assert "完整判讀：https://demo.example.app/r/t1" in lines
    assert lines[-1] == "AI 自動判讀，請自行查證。"   # 截斷時結果頁連結與免責行保留


def test_threads_reply_unknown_type():
    reply = format_verdict_reply({"risk_type": "??", "summary": "s"}, "https://x.app/r/t2")
    assert reply.split("\n")[0] == "\U0001F7E1 尚待確認"
    assert "尚無查核機構證實" in reply   # 缺 verification_status 視為未證實


def test_run_analysis_attaches_usage_and_actual_provider(monkeypatch):
    # B-15 log 需要：回應附 usage、model 與「實際回應的」provider（cgu 失敗 → openai 接手）
    import json as _json

    import requests

    import app.services.ai_service as ai_mod

    payload = {
        "is_risk": True, "risk_type": "SCAM", "category": "Phishing",
        "confidence_score": 0.9, "summary": "s", "explanation": "e", "sources": [],
    }

    class _Resp:
        def __init__(self, ok):
            self.ok = ok

        def raise_for_status(self):
            if not self.ok:
                err = requests.exceptions.HTTPError("402")
                err.response = type("R", (), {"status_code": 402, "text": "insufficient"})()
                raise err

        def json(self):
            return {
                "output": [{"type": "message", "content": [
                    {"type": "output_text", "text": _json.dumps(payload)}]}],
                "usage": {"input_tokens": 1234, "output_tokens": 56, "total_tokens": 1290},
            }

    calls = []

    def _fake_post(url, headers=None, json=None, timeout=None):
        calls.append(url)
        return _Resp(ok=not url.startswith("https://cgu.invalid"))

    monkeypatch.setattr(ai_mod.requests, "post", _fake_post)
    svc = AIService()
    svc.providers = ["cgu", "openai"]
    svc.cgu_base, svc.cgu_key, svc.cgu_model = "https://cgu.invalid/v1", "k", "gpt-5.4-mini"
    svc.openai_base, svc.myai_key, svc.openai_model = "https://openai.invalid/v1", "k", "gpt-5-mini"

    result = svc._run_analysis("prompt", use_web_search=False)
    assert result["provider"] == "openai"
    assert result["model"] == "gpt-5-mini"
    assert result["usage"] == {"input_tokens": 1234, "output_tokens": 56}
    assert len(calls) == 2
