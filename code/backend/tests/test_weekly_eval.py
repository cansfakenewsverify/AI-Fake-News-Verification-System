"""每週新查核自動評測（FR-24，app/services/weekly_eval.py）與 /api/admin/weekly-eval。

全部離線、零 AI：查核來源、CGU 用量與 AI 判讀都換成假的，知識庫寫在 tmp_path 的 PandasStore。
驗證題目範圍（最近 7 天、一篇報告一題、SAFE 題也收）、額度護欄（保留額、讀不到用量、整批失敗就停）、
統計（偽陰性／偽陽性、風險判定一致率）與報告不含訊息原文。
"""
from datetime import date

import pytest
from fastapi.testclient import TestClient

import app.services.ai_service as ai_service
import app.services.factcheck_corpus as fc
import app.services.weekly_eval as we
from app.config import settings
from app.services.cache_service import CacheService
from app.services.pandas_store import PandasStore

TOKEN = "0123456789abcdef0123456789abcdef"
TODAY = date(2026, 10, 4)          # 週日；本週範圍 = 2026-09-27 起

MYGOPEN = [
    ("【錯誤】網傳喝檸檬水能殺死癌細胞？醫師：沒有科學根據", "2026-09-30"),
    ("【真】網傳郵局推出新的數位帳戶服務？確有其事", "2026-10-01"),
    ("【錯誤】網傳吃香蕉會讓血糖飆高到危險程度？", "2026-09-10"),      # 超出本週範圍
]
TFC_REPORT = "https://tfc-taiwan.org.tw/fact-check-reports/1"
TFC = [
    {"source": "TFC", "kind": "rumor_text", "use": "kb", "label": "MISINFO", "verdict_raw": "false",
     "text": "緊急通知！明天起全台自來水停水三天，請大家趕快儲水並轉傳給親友", "url": TFC_REPORT,
     "title": "網傳「全台停水三天」", "published": "2026-09-29", "requests": None, "scam_topic": False, "extra": ""},
    {"source": "TFC", "kind": "rumor_text", "use": "kb", "label": "MISINFO", "verdict_raw": "false",
     "text": "自來水公司宣布全台大停水三天，快轉給家人朋友儲水備用", "url": TFC_REPORT,
     "title": "網傳「全台停水三天」", "published": "2026-09-29", "requests": None, "scam_topic": False, "extra": ""},
    {"source": "TFC", "kind": "title_claim", "use": "analysis", "label": "SAFE", "verdict_raw": "correct",
     "text": "衛福部宣布十月起擴大流感疫苗公費接種對象", "url": "https://tfc-taiwan.org.tw/fact-check-reports/2",
     "title": "網傳「擴大公費接種」", "published": "2026-10-02", "requests": None, "scam_topic": False, "extra": ""},
    {"source": "TFC", "kind": "title_claim", "use": "kb", "label": "MISINFO", "verdict_raw": "false",
     "text": "網傳喝咖啡會導致骨質疏鬆症", "url": "https://tfc-taiwan.org.tw/fact-check-reports/3",
     "title": "舊報告", "published": "2026-08-01", "requests": None, "scam_topic": False, "extra": ""},
]
COFACTS_RUMOR = "恭喜您獲得週年慶抽獎一等獎，請點以下連結填寫個人資料領取 iPhone 17 一支"
COFACTS_SAFE = "中央氣象署提醒：颱風外圍環流影響，今晚北部山區有局部大雨，請注意安全"
FALSE_LEMON = "喝檸檬水能殺死癌細胞"


def _node(node_id, text, kind, created="2026-09-30T10:00:00Z"):
    return {"id": node_id, "text": text, "createdAt": created, "replyRequestCount": 5, "articleCategories": [],
            "articleReplies": [{"positiveFeedbackCount": 3, "negativeFeedbackCount": 0,
                                "reply": {"type": kind, "text": "查核回應"}}]}


SAFE_POOL = [_node(f"safe{i}", f"這是第{i}則經查證為正確的公告內容，請大家安心參考與分享", "NOT_RUMOR", "2025-01-01T00:00:00Z")
             for i in range(8)]


def _entry(title, published):
    return {"title": {"$t": title}, "published": {"$t": published + "T08:00:00+08:00"},
            "link": [{"rel": "alternate", "href": f"https://www.mygopen.com/{published}/{abs(hash(title)) % 10000}"}],
            "summary": {"$t": "摘要"}}


@pytest.fixture
def sources(monkeypatch):
    calls = []

    def mygopen_entries(cache=fc.no_cache, max_pages=None):
        calls.append(("mygopen", max_pages))
        return [_entry(t, d) for t, d in MYGOPEN]

    def tfc_rows(cache=fc.no_cache, report_pages=None, rumor_pages=None, skipped=None):
        calls.append(("tfc", report_pages, rumor_pages))
        return [dict(r) for r in TFC]

    def cofacts_nodes(reply_type, min_requests, limit, cache=fc.no_cache, order="requests"):
        calls.append(("cofacts", reply_type, min_requests, limit, order))
        if order == "replied":
            return [_node("r1", COFACTS_RUMOR, "RUMOR")] if reply_type == "RUMOR" else [_node("s1", COFACTS_SAFE, "NOT_RUMOR")]
        return SAFE_POOL if reply_type == "NOT_RUMOR" else []

    monkeypatch.setattr(fc, "mygopen_entries", mygopen_entries)
    monkeypatch.setattr(fc, "tfc_rows", tfc_rows)
    monkeypatch.setattr(fc, "cofacts_nodes", cofacts_nodes)
    return calls


@pytest.fixture
def usage(monkeypatch):
    """CGU 用量：remaining 依序取值（最後一個重複使用）；-1 代表讀不到。"""
    state = {"remaining": [3.5], "calls": 0}

    def cgu_usage():
        state["calls"] += 1
        values = state["remaining"]
        left = values[min(state["calls"] - 1, len(values) - 1)]
        if left < 0:
            return {"cost_usd": -1.0, "quota_usd": -1.0, "remaining_usd": -1.0}
        return {"cost_usd": round(10 - left, 4), "quota_usd": 10.0, "remaining_usd": left}

    monkeypatch.setattr(fc, "cgu_usage", cgu_usage)
    return state


PER_CALL_USD = (1000 * 0.55 + 500 * 2.20) / 1_000_000     # gpt-5.6-luna 閘道價 × FakeAI 的 usage


class FakeAI:
    """依文字回判定（預設 MISINFO）；每次 usage 1000／500 tokens（gpt-5.6-luna 約 USD 0.00165）。"""

    def __init__(self, answers=None, fallback=False):
        self.answers = answers or {}
        self.fallback = fallback
        self.calls = []

    def analyze_content(self, content, url=None, context=None, use_web_search=None):
        self.calls.append((content, use_web_search))
        if self.fallback:
            return ai_service._default_fallback_result("quota exhausted")
        risk = next((v for k, v in self.answers.items() if k in content), "MISINFO")
        return {"risk_type": risk, "confidence_score": 0.9, "model": "gpt-5.6-luna", "provider": "cgu",
                "usage": {"input_tokens": 1000, "output_tokens": 500}}


@pytest.fixture
def store(tmp_path):
    kb = PandasStore(data_dir=str(tmp_path))
    src = [{"title": "MyGoPen", "url": "https://www.mygopen.com/a", "tier": 1}]
    for i in range(6):
        text = f"查核機構已證實的第{i}則歷史謠言內容"
        kb.save_record(data_type="TEXT", raw_content=text, content_hash=CacheService.generate_hash(text),
                       content_vector=None, source_url=f"https://www.mygopen.com/2025/0{i + 1}/x.html",
                       ai_result={"is_risk": True, "risk_type": "MISINFO", "category": "Test", "confidence_score": 0.95,
                                  "summary": "摘要", "explanation": "解釋", "sources": src},
                       label_source="rule", origin=fc.ORIGIN)
    return kb


@pytest.fixture(autouse=True)
def _fresh_state(monkeypatch):
    monkeypatch.setattr(settings, "WEEKLY_EVAL_MAX_USD", 6.0)
    monkeypatch.setattr(settings, "WEEKLY_EVAL_RESERVE_USD", 3.0)
    monkeypatch.setattr(we, "EST_USD_PER_CALL", 0.01)
    we._reset(0.0, False)
    we.STATUS["state"] = "idle"
    we.LAST.update(rows=[], meta=None)
    yield
    if we._lock.locked():
        we._lock.release()


def test_fresh_items_are_this_weeks_verdicts_one_per_report(sources):
    items, errors = we.fresh_items(7, TODAY)

    assert errors == {}
    by_source = {}
    for it in items:
        by_source.setdefault(it["source"], []).append(it["gold"])
    assert sorted(by_source["MyGoPen"]) == ["MISINFO", "SAFE"]          # 09-10 那篇超出範圍
    assert sorted(by_source["TFC"]) == ["MISINFO", "SAFE"]              # 同一篇報告兩則謠言原文只出一題；舊報告不收
    assert sorted(by_source["Cofacts"]) == ["MISINFO", "SAFE"]
    assert all(it["part"] == "fresh" and it["published"] >= "2026-09-27" for it in items)
    assert ("cofacts", "RUMOR", we.COFACTS_EVAL_MIN_REQUESTS, we.COFACTS_RECENT_LIMIT, "replied") in sources


def test_eval_judges_fresh_then_history_and_summarises(sources, usage, store):
    usage["remaining"] = [3.255]                    # 可用 0.255 → 本週 6 題、歷史 19 題（風險 13 → 實有 6、安全 3）
    ai = FakeAI({FALSE_LEMON: "SAFE", "流感疫苗": "MISINFO", "抽獎": "SCAM", "氣象署": "SAFE", "郵局": "SAFE",
                 "正確的公告": "SAFE"})

    result = we.run_eval(store=store, ai=ai, today=TODAY)

    assert result["state"] == "done" and result["error"] is None
    assert (result["planned_fresh"], result["planned_history"], result["done"]) == (6, 9, 15)
    assert result["available_fresh"] == 6 and result["stop_reason"] is None
    assert all(web is False for _, web in ai.calls)
    fresh = result["summary"]["fresh"]
    assert (fresh["n"], fresh["fn"], fresh["fp"]) == (6, 1, 1)
    assert fresh["risk_accuracy"] == round(4 / 6, 4) and fresh["exact_accuracy"] == round(3 / 6, 4)
    assert fresh["matrix"]["MISINFO"]["SCAM"] == 1       # Cofacts RUMOR 記 MISINFO，AI 判 SCAM：風險一致、三類不一致
    history = result["summary"]["history"]
    assert history["gold_counts"] == {"SCAM": 0, "MISINFO": 6, "SAFE": 3} and history["fn"] == 0
    assert result["spent_usd"] == pytest.approx(15 * PER_CALL_USD, abs=1e-4)


def test_report_and_csv_have_no_message_text(sources, usage, store):
    usage["remaining"] = [3.255]
    we.run_eval(store=store, ai=FakeAI({FALSE_LEMON: "SAFE"}), today=TODAY)

    report = we.report_markdown()
    assert report.startswith("# 每週新查核自動評測 2026-10-04")
    assert "偽陰性（真值有風險、AI 判 SAFE）1 筆" in report
    assert "風險判定不一致的題目" in report and "https://www.mygopen.com/2026-09-30/" in report
    table = we.results_csv()
    assert table.splitlines()[0] == ",".join(we.CSV_COLUMNS)
    assert len(table.splitlines()) == 1 + 15
    for text in (COFACTS_RUMOR, COFACTS_SAFE, TFC[0]["text"], "檸檬水", "歷史謠言"):
        assert text not in report and text not in table


def test_skips_when_remaining_quota_is_at_the_reserve(sources, usage, store):
    usage["remaining"] = [3.0]
    ai = FakeAI()

    result = we.run_eval(store=store, ai=ai, today=TODAY)

    assert result["state"] == "skipped" and result["stop_reason"] == "reserve"
    assert ai.calls == [] and sources == []
    assert "CGU 剩餘額度接近保留額" in we.report_markdown()


def test_unknown_usage_runs_this_weeks_items_only(sources, usage, monkeypatch):
    usage["remaining"] = [-1]

    class NoStore:
        def sample_verified(self, *args, **kwargs):
            raise AssertionError("history must not be sampled when usage is unknown")

    result = we.run_eval(store=NoStore(), ai=FakeAI(), today=TODAY)

    assert result["state"] == "done"
    assert result["allowed_usd"] == we.UNKNOWN_USAGE_CAP_USD
    assert (result["planned_fresh"], result["planned_history"]) == (6, 0)


def test_stops_when_a_whole_chunk_falls_back(sources, usage, store, monkeypatch):
    monkeypatch.setattr(we, "CHUNK", 2)
    usage["remaining"] = [3.255]

    result = we.run_eval(store=store, ai=FakeAI(fallback=True), today=TODAY)

    assert result["stop_reason"] == "ai_unavailable"
    assert result["done"] == 2 and result["fallbacks"] == 2
    assert result["summary"]["fresh"]["valid"] == 0


def test_stops_before_eating_into_the_users_reserve(sources, usage, store, monkeypatch):
    monkeypatch.setattr(we, "CHUNK", 2)
    monkeypatch.setattr(we, "USAGE_CHECK_EVERY", 2)
    usage["remaining"] = [3.255, 3.002]            # 開始後網站使用者用掉一些

    result = we.run_eval(store=store, ai=FakeAI(), today=TODAY)

    assert result["stop_reason"] == "reserve" and result["done"] == 2


def test_stops_when_actual_cost_reaches_the_allowance(sources, usage, monkeypatch, tmp_path):
    monkeypatch.setattr(we, "CHUNK", 2)
    monkeypatch.setattr(we, "EST_USD_PER_CALL", 0.0001)   # 預估偏低：實際每題約 0.00165
    usage["remaining"] = [3.004]

    result = we.run_eval(store=PandasStore(data_dir=str(tmp_path)), ai=FakeAI(), today=TODAY)

    assert result["stop_reason"] == "budget" and result["done"] == 2


def test_plan_only_calls_no_ai_and_keeps_the_last_report(sources, usage, store):
    usage["remaining"] = [3.255]
    we.run_eval(store=store, ai=FakeAI(), today=TODAY)
    report = we.report_markdown()
    ai = FakeAI()

    result = we.run_eval(plan_only=True, store=store, ai=ai, today=TODAY)

    assert result["state"] == "done" and result["planned"] == 15
    assert ai.calls == []
    assert we.report_markdown() == report


def test_history_has_no_safe_items_until_fact_checks_are_in_the_knowledge_base(sources, tmp_path):
    items = we.history_items(30, TODAY, set(), PandasStore(data_dir=str(tmp_path)))
    assert items == []


def test_history_moves_to_the_next_slice_each_week_and_wraps_around(store, monkeypatch):
    monkeypatch.setattr(we, "HISTORY_RISKY_PER_WEEK", 4)
    order = [r["data_hash"] for r in store.sample_verified(fc.ORIGIN, 10, seed=we.HISTORY_SEED)]
    assert len(order) == 6

    def week(n):
        day = we.HISTORY_EPOCH + __import__("datetime").timedelta(days=7 * n + 3)
        return [r["data_hash"] for r in we.history_risky_rows(store, 4, day)]

    assert week(0) == order[0:4]
    assert week(1) == order[4:6] + order[0:2]     # 第 4 筆起，到尾端從頭接上
    assert week(3) == order[0:4]                  # (3*4) % 6 == 0


def test_wilson_interval():
    lo, hi = we.wilson(0, 90)
    assert lo == 0.0 and hi == pytest.approx(0.0409, abs=1e-4)
    lo, hi = we.wilson(90, 90)
    assert lo == pytest.approx(0.9591, abs=1e-4) and hi == 1.0
    assert we.wilson(0, 0) == (0.0, 0.0)


# ── 管理端點 ─────────────────────────────────────────────────────

@pytest.fixture
def client(monkeypatch, store):
    monkeypatch.setattr(settings, "ADMIN_TOKEN", TOKEN)
    monkeypatch.setattr(we, "get_knowledge_store", lambda: store)
    monkeypatch.setattr(we, "today_taipei", lambda: TODAY)
    monkeypatch.setattr(ai_service, "AIService", FakeAI)
    return TestClient(__import__("app.main", fromlist=["app"]).app)


HEADERS = {"X-Admin-Token": TOKEN}


def test_endpoints_require_admin_token(client):
    assert client.post("/api/admin/weekly-eval").status_code == 401
    assert client.get("/api/admin/weekly-eval").status_code == 401
    assert client.get("/api/admin/weekly-eval/report.md").status_code == 401


def test_post_runs_eval_and_reports_are_downloadable(client, sources, usage):
    usage["remaining"] = [3.255]
    assert client.get("/api/admin/weekly-eval/report.md", headers=HEADERS).status_code == 404

    resp = client.post("/api/admin/weekly-eval", headers=HEADERS)

    assert resp.status_code == 202 and resp.json()["started"] is True and resp.json()["max_usd"] == 6.0
    status = client.get("/api/admin/weekly-eval", headers=HEADERS).json()
    assert status["state"] == "done" and status["done"] == 15
    report = client.get("/api/admin/weekly-eval/report.md", headers=HEADERS)
    assert report.status_code == 200 and report.headers["content-type"].startswith("text/markdown")
    assert report.text.startswith("# 每週新查核自動評測 2026-10-04")
    table = client.get("/api/admin/weekly-eval/results.csv", headers=HEADERS)
    assert table.status_code == 200 and len(table.text.splitlines()) == 16


def test_post_limits_max_usd_and_rejects_bad_values(client, sources, usage):
    usage["remaining"] = [9.0]
    resp = client.post("/api/admin/weekly-eval?max_usd=0.05&plan_only=true", headers=HEADERS)
    assert resp.status_code == 202 and resp.json()["max_usd"] == 0.05
    status = client.get("/api/admin/weekly-eval", headers=HEADERS).json()
    assert status["allowed_usd"] == 0.05 and status["planned"] == 5     # 0.05／每題 0.01
    assert client.post("/api/admin/weekly-eval?max_usd=11", headers=HEADERS).status_code == 422
    assert client.post("/api/admin/weekly-eval?days=0", headers=HEADERS).status_code == 422


def test_running_eval_blocks_new_runs_and_report_downloads(client):
    assert we._lock.acquire(blocking=False)
    try:
        assert client.post("/api/admin/weekly-eval", headers=HEADERS).json()["code"] == "eval_in_progress"
        assert client.get("/api/admin/weekly-eval/report.md", headers=HEADERS).status_code == 409
    finally:
        we._lock.release()


def test_fresh_items_alternate_sources_so_a_small_budget_covers_each_source(sources):
    items, _ = we.fresh_items(7, TODAY)
    assert [i["source"] for i in items[:3]] == ["Cofacts", "MyGoPen", "TFC"]
