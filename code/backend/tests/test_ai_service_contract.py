"""AI 服務的解析與 fallback 契約測試（不呼叫任何外部 API）。"""
import pytest

from app.services.ai_service import AIService, _default_fallback_result
from app.services.threads_service import format_verdict_reply, THREADS_TEXT_LIMIT
from app.utils.verdict import frame_of
from app.workers.pandas_task_processor import (
    _build_result,
    _confidence_level,
    _is_fallback,
)


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


def test_confidence_level_bands():
    assert _confidence_level(0.95) == "高"
    assert _confidence_level(0.6) == "中"
    assert _confidence_level(0.1) == "低"


def test_build_result_reports_cache_layer():
    ai = {"is_risk": True, "risk_type": "SCAM", "category": "Investment",
          "confidence_score": 0.9, "summary": "s", "explanation": "e", "sources": []}
    hit = _build_result(ai, [], [], cached=True, cache_layer="vector")
    assert hit["cached"] is True and hit["cache_layer"] == "vector"
    miss = _build_result(ai, [], [], cached=False)
    assert miss["cached"] is False and miss["cache_layer"] is None


# ── Threads 回覆格式：500 字上限與必要元素 ────────────────────
def test_threads_reply_within_limit_and_has_verdict():
    result = {
        "risk_type": "SCAM", "confidence_level": "高",
        "summary": "假冒銀行釣魚簡訊", "explanation": "說明" * 300,  # 刻意超長
        "sources": [{"title": "165", "url": "https://165.npa.gov.tw/"}],
    }
    reply = format_verdict_reply(result)
    assert len(reply) <= THREADS_TEXT_LIMIT
    assert "詐騙" in reply
    assert "https://165.npa.gov.tw/" in reply     # 截斷時來源要保留


def test_threads_reply_unknown_type():
    reply = format_verdict_reply({"risk_type": "??", "summary": "s"})
    assert "尚待確認" in reply
