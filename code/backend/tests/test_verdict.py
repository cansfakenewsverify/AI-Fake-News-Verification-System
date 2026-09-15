"""verdict.frame_of 紅黃綠映射表格測試（spec §7.8、FN-6；離線、零點數）。"""
import pytest

from app.services.ai_service import AIService, _default_fallback_result
from app.utils.verdict import GREEN_MIN_CONFIDENCE, frame_of, is_fallback

RED = "\U0001F534"
YELLOW = "\U0001F7E1"
GREEN = "\U0001F7E2"


def _r(is_risk=False, risk_type="SAFE", confidence=0.9, ai_unavailable=False,
       verification_status="verified", drop_status=False):
    d = {
        "is_risk": is_risk,
        "risk_type": risk_type,
        "confidence_score": confidence,
        "ai_unavailable": ai_unavailable,
        "verification_status": verification_status,
    }
    if drop_status:
        d.pop("verification_status")
    return d


CASES = [
    # ── 表格 8 列（各一代表輸入）──
    ("row1_ai_unavailable", _r(ai_unavailable=True), ("grey", "AI 暫時無法使用", None)),
    ("row2_unverifiable", _r(risk_type="UNVERIFIABLE", confidence=0.0, verification_status="unverified"),
     ("yellow", "無法查證", YELLOW)),
    ("row3_scam", _r(is_risk=True, risk_type="SCAM"), ("red", "詐騙警告", RED)),
    ("row4_misinfo", _r(is_risk=True, risk_type="MISINFO"), ("red", "假訊息", RED)),
    ("row5_risk_other", _r(is_risk=True, risk_type="UNKNOWN"), ("red", "風險訊息", RED)),
    ("row6_safe_unverified", _r(risk_type="SAFE", confidence=0.95, verification_status="unverified"),
     ("yellow", "尚無查核機構證實", YELLOW)),
    ("row7_safe_verified_green", _r(risk_type="SAFE", confidence=0.95, verification_status="verified"),
     ("green", "查無異常", GREEN)),
    ("row8_low_conf_safe", _r(risk_type="SAFE", confidence=0.3, verification_status="verified"),
     ("yellow", "尚待確認", YELLOW)),
    # ── 11 組額外輸入（邊界、順序、缺鍵）──
    ("missing_status_is_unverified", _r(risk_type="SAFE", confidence=0.95, drop_status=True),
     ("yellow", "尚無查核機構證實", YELLOW)),
    ("safe_rule_green", _r(risk_type="SAFE", confidence=0.95, verification_status="rule"),
     ("green", "查無異常", GREEN)),
    ("safe_threshold_exact_green", _r(risk_type="SAFE", confidence=GREEN_MIN_CONFIDENCE),
     ("green", "查無異常", GREEN)),
    ("safe_just_below_threshold", _r(risk_type="SAFE", confidence=0.69),
     ("yellow", "尚待確認", YELLOW)),
    ("red_unaffected_by_unverified", _r(is_risk=True, risk_type="SCAM", confidence=0.4,
                                        verification_status="unverified"),
     ("red", "詐騙警告", RED)),
    ("ai_unavailable_beats_scam", _r(is_risk=True, risk_type="SCAM", ai_unavailable=True),
     ("grey", "AI 暫時無法使用", None)),
    ("unverifiable_beats_is_risk", _r(is_risk=True, risk_type="UNVERIFIABLE"),
     ("yellow", "無法查證", YELLOW)),
    ("unknown_not_risk_pending", _r(risk_type="UNKNOWN", confidence=0.95),
     ("yellow", "尚待確認", YELLOW)),
    ("safe_unverified_low_conf", _r(risk_type="SAFE", confidence=0.1, verification_status="unverified"),
     ("yellow", "尚無查核機構證實", YELLOW)),
    ("ai_unavailable_not_true_ignored", {"is_risk": False, "risk_type": "SAFE", "confidence_score": 0.9,
                                         "verification_status": "verified"},
     ("green", "查無異常", GREEN)),
    ("safe_bogus_status_is_unverified", _r(risk_type="SAFE", confidence=0.95, verification_status="bogus"),
     ("yellow", "尚無查核機構證實", YELLOW)),
    ("safe_capitalized_status_is_unverified", _r(risk_type="SAFE", confidence=0.95,
                                                 verification_status="Verified"),
     ("yellow", "尚無查核機構證實", YELLOW)),
    ("misinfo_missing_status_still_red", {"is_risk": True, "risk_type": "MISINFO", "confidence_score": 0.8},
     ("red", "假訊息", RED)),
]


@pytest.mark.parametrize("name,result,expected", CASES, ids=[c[0] for c in CASES])
def test_frame_of_table(name, result, expected):
    assert frame_of(result) == expected


def test_frame_of_green_requires_all_three_conditions():
    # 綠燈必須 SAFE、信心 >= 0.7、已證實（共識 §9 第 2 點）
    assert frame_of(_r(risk_type="SAFE", confidence=0.95, verification_status="verified"))[0] == "green"
    assert frame_of(_r(risk_type="SAFE", confidence=0.95, verification_status="unverified"))[0] != "green"
    assert frame_of(_r(risk_type="SAFE", confidence=0.5, verification_status="verified"))[0] != "green"
    assert frame_of(_r(risk_type="UNKNOWN", confidence=0.95, verification_status="verified"))[0] != "green"


# ── fallback 契約（spec §5.5、共識 §10、FN-7）──
def test_is_fallback_contract():
    err = "HTTP 402 insufficient_credits secret-upstream-detail"
    res = _default_fallback_result(err)
    # fallback 同時滿足旗標與 summary 前綴（前端靠前綴、後端靠旗標）
    assert res["ai_unavailable"] is True
    assert res["summary"].startswith("AI 分析暫時無法使用")
    assert is_fallback(res)
    # 上游錯誤原文不外洩給使用者
    assert err not in res["explanation"]
    assert "secret-upstream-detail" not in res["explanation"]
    assert res["explanation"] == "AI 服務暫時無法使用（額度用盡或連線問題），請稍後再試。"
    # fallback 映射到灰卡
    assert frame_of(res)[0] == "grey"

    # 正常結果回 False
    normal = {"is_risk": True, "risk_type": "SCAM", "confidence_score": 0.9,
              "summary": "假冒銀行釣魚簡訊", "explanation": "e", "sources": []}
    assert is_fallback(normal) is False
    assert is_fallback({"summary": "正常摘要", "ai_unavailable": False}) is False


@pytest.mark.parametrize("value", [
    None, "not a dict", [], {"ai_unavailable": True, "summary": "正常摘要"},
    {"summary": "AI 分析暫時無法使用：逾時"}, {"summary": "上游服務異常，請稍後"},
])
def test_is_fallback_each_condition(value):
    assert is_fallback(value) is True


def test_ai_service_available_property(monkeypatch):
    from app.config import settings
    for key in ("MYAI_API_KEY", "CGU_API_KEY"):
        monkeypatch.setattr(settings, key, "", raising=False)
    assert AIService().available is False

    monkeypatch.setattr(settings, "CGU_API_KEY", "dummy-key", raising=False)
    monkeypatch.setattr(settings, "CGU_BASE_URL", "https://example.invalid/v1", raising=False)
    assert AIService().available is True


# ── 限流/額度仍可機器判讀（explanation 改固定文案後的回歸，B-11）──
@pytest.mark.parametrize("err,kind,status", [
    ("cgu HTTP 429: Too Many Requests", "ratelimit", 429),
    ("openai HTTP 503: upstream down", "ratelimit", 503),
    ("cgu(no-search): 429 Client Error: Too Many Requests for url", "ratelimit", 429),
    ("gemini: RESOURCE_EXHAUSTED", "ratelimit", None),
    ("claude HTTP 402: insufficient_credits", "quota", 402),
    ("openai HTTP 400: no_pricing_info", "error", None),
    ("未設定可用 AI provider 金鑰或中繼網址", "error", None),
])
def test_fallback_error_kind_machine_readable(err, kind, status):
    res = _default_fallback_result(err)
    assert res["error_kind"] == kind
    assert res["upstream_status"] == status
    assert err not in res["explanation"]


def _run_analyze_record_with_ai_result(monkeypatch, ai_result):
    import asyncio
    from app.services import news_fetcher as nf

    async def fake_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    class FakeCrawler:
        async def process_input(self, url, kind):
            return {"success": False}

    class FakeStore:
        def find_by_hash(self, h):
            return None

        def save_record(self, **kwargs):
            raise AssertionError("fallback 結果不可寫入知識庫")

    class FakeAI:
        def analyze_content(self, content, url=None, context=None):
            return ai_result

    monkeypatch.setattr(asyncio, "to_thread", fake_to_thread)
    monkeypatch.setattr(nf, "_crawler", FakeCrawler())
    monkeypatch.setattr(nf, "_pandas_store", FakeStore())
    monkeypatch.setattr(nf, "_ai", FakeAI())
    return asyncio.run(nf._analyze_record("https://example.com/n", "標題", "內" * 80))


def test_analyze_record_ratelimit_from_429_fallback(monkeypatch):
    res = _default_fallback_result("cgu HTTP 429: Too Many Requests")
    assert _run_analyze_record_with_ai_result(monkeypatch, res) == "ratelimit"


def test_analyze_record_quota_fallback_stops_batch(monkeypatch):
    res = _default_fallback_result("claude HTTP 402: insufficient_credits")
    assert _run_analyze_record_with_ai_result(monkeypatch, res) == "ratelimit"


def test_analyze_record_other_fallback_is_ai_unavailable(monkeypatch):
    res = _default_fallback_result("openai HTTP 400: no_pricing_info")
    assert _run_analyze_record_with_ai_result(monkeypatch, res) == "ai_unavailable"


def test_retry_pending_stops_on_ratelimit(monkeypatch):
    import asyncio
    from app.services import news_fetcher as nf

    class Rec:
        def __init__(self, i):
            self.source_url = f"https://example.com/{i}"
            self.news_title = f"t{i}"
            self.content = "內" * 80

    calls = []

    async def fake_analyze(url, title, content):
        calls.append(url)
        return "ratelimit"

    async def fake_sleep(_s):
        return None

    monkeypatch.setattr(nf, "_get_pending_records", lambda limit=0: [Rec(i) for i in range(5)])
    monkeypatch.setattr(nf, "_analyze_record", fake_analyze)
    monkeypatch.setattr(asyncio, "sleep", fake_sleep)
    assert asyncio.run(nf.retry_pending_records()) == 0
    assert len(calls) == 1


def test_processor_frame_for_fallback_is_grey():
    # 任務處理器的框映射委派 verdict.frame_of：fallback（SAFE、信心 0）必須灰卡，不是黃框（spec §5.5、§7.8）
    from app.workers.pandas_task_processor import _ai_result_to_frame
    res = _default_fallback_result("cgu HTTP 429: Too Many Requests")
    assert _ai_result_to_frame(res) == ("grey", "AI 暫時無法使用")
