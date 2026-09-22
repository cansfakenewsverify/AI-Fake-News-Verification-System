"""B-07: news_fetcher 的阻塞呼叫必須經過 asyncio.to_thread（不卡 event loop）。
離線、零點數：RSS / DB / AI / Parquet 全部 monkeypatch。"""
import asyncio

from app.services import news_fetcher as nf


def _install_recording_to_thread(monkeypatch):
    calls = []

    async def fake_to_thread(func, *args, **kwargs):
        calls.append(getattr(func, "__name__", repr(func)))
        return func(*args, **kwargs)

    monkeypatch.setattr(asyncio, "to_thread", fake_to_thread)
    return calls


def test_run_trending_fetch_offloads_blocking_calls(monkeypatch):
    calls = _install_recording_to_thread(monkeypatch)
    saved = []

    def fetch_rss_items(num_per_feed=4, include_cofacts=True):
        return [
            {"url": "https://example.com/a", "title": "新聞 A"},
            {"url": "https://example.com/b", "title": "新聞 B"},
        ]

    def _save_rss_record(item):
        saved.append(item["url"])

    def _cleanup_legacy_strings():
        return None

    async def retry_pending_records():
        return 0

    monkeypatch.setattr(nf.SearchService, "fetch_rss_items", staticmethod(fetch_rss_items))
    monkeypatch.setattr(nf, "_save_rss_record", _save_rss_record)
    monkeypatch.setattr(nf, "_cleanup_legacy_strings", _cleanup_legacy_strings)
    monkeypatch.setattr(nf, "retry_pending_records", retry_pending_records)

    asyncio.run(nf.run_trending_fetch())

    assert "_cleanup_legacy_strings" in calls
    assert "fetch_rss_items" in calls
    assert calls.count("_save_rss_record") == 2
    assert saved == ["https://example.com/a", "https://example.com/b"]


def test_run_trending_fetch_without_analysis_skips_the_ai_step(monkeypatch):
    """analyze_pending=False：只抓 RSS 與寫入確定性結論，不進 retry_pending_records（不呼叫判讀模型）。"""
    _install_recording_to_thread(monkeypatch)
    per_feed_seen = []
    saved = []

    def fetch_rss_items(num_per_feed=4, include_cofacts=True):
        per_feed_seen.append(num_per_feed)
        return [{"url": "https://www.mygopen.com/2026/09/a.html", "title": "【錯誤】網傳 A？"}]

    async def retry_pending_records():
        raise AssertionError("analyze_pending=False 不得呼叫 AI 分析")

    monkeypatch.setattr(nf.SearchService, "fetch_rss_items", staticmethod(fetch_rss_items))
    monkeypatch.setattr(nf, "_save_rss_record", lambda item: saved.append(item["url"]))
    monkeypatch.setattr(nf, "_cleanup_legacy_strings", lambda: None)
    monkeypatch.setattr(nf, "retry_pending_records", retry_pending_records)

    asyncio.run(nf.run_trending_fetch(analyze_pending=False, per_feed=25))

    assert per_feed_seen == [25]
    assert saved == ["https://www.mygopen.com/2026/09/a.html"]


def test_analyze_record_offloads_store_and_ai(monkeypatch):
    calls = _install_recording_to_thread(monkeypatch)

    class FakeCrawler:
        async def process_input(self, url, kind):
            return {"success": False}

    class FakeStore:
        def find_by_hash(self, h):
            return None

        def save_record(self, **kwargs):
            return None

    class FakeAI:
        def analyze_content(self, content, url=None, context=None):
            return {"risk_type": "SAFE", "confidence_score": 0.9, "summary": "ok",
                    "category": "新聞", "explanation": "x", "sources": []}

    class FakeSession:
        def query(self, *a, **k):
            return self

        def filter_by(self, **k):
            return self

        def first(self):
            return None

        def close(self):
            pass

    monkeypatch.setattr(nf, "_crawler", FakeCrawler())
    monkeypatch.setattr(nf, "_pandas_store", FakeStore())
    monkeypatch.setattr(nf, "_ai", FakeAI())
    monkeypatch.setattr(nf, "SessionLocal", FakeSession)

    result = asyncio.run(nf._analyze_record("https://example.com/n", "標題", "內" * 80))

    assert result == "ok"
    assert "find_by_hash" in calls
    assert "analyze_content" in calls
    assert "save_record" in calls
    assert "_apply_ai_result" in calls


def test_retry_pending_records_offloads_sqlite(monkeypatch):
    calls = _install_recording_to_thread(monkeypatch)
    marked = []

    class Rec:
        def __init__(self, url):
            self.source_url = url
            self.news_title = "標題"
            self.content = ""

    def _get_pending_records(limit=10):
        return [Rec("https://example.com/short"), Rec("https://example.com/ok")]

    def _mark_unverifiable(url):
        marked.append(url)

    async def _analyze_record(url, title, content):
        return "short" if url.endswith("short") else "ok"

    async def fast_sleep(_s):
        return None

    monkeypatch.setattr(nf, "_get_pending_records", _get_pending_records)
    monkeypatch.setattr(nf, "_mark_unverifiable", _mark_unverifiable)
    monkeypatch.setattr(nf, "_analyze_record", _analyze_record)
    monkeypatch.setattr(asyncio, "sleep", fast_sleep)

    ok = asyncio.run(nf.retry_pending_records())

    assert ok == 1
    assert "_get_pending_records" in calls
    assert "_mark_unverifiable" in calls
    assert marked == ["https://example.com/short"]


# ── D-01：_analyze_record 寫知識庫前走 url_validator → grade_sources（FR-17 (a)）──

class _FakeRec:
    def __init__(self, url):
        self.source_url = url
        self.platform = None
        self.label_source = None
        self.verified = None
        self.source_tier = None


def _setup_analyze(monkeypatch, tmp_path, sources, alive):
    import json as _json
    import requests
    from app.services.pandas_store import PandasStore
    from app.utils import url_validator, source_tier

    def _no_net(*a, **k):
        raise AssertionError("test must stay offline")

    monkeypatch.setattr(requests, "get", _no_net)
    monkeypatch.setattr(requests, "post", _no_net)
    monkeypatch.setattr(requests, "head", _no_net)
    source_tier.cofacts_has_verdict.cache_clear()

    class FakeCrawler:
        async def process_input(self, url, kind):
            return {"success": False}

    class FakeAI:
        def analyze_content(self, content, url=None, context=None):
            return {"is_risk": True, "risk_type": "MISINFO", "confidence_score": 0.9,
                    "summary": "摘要", "category": "健康", "explanation": "x",
                    "sources": [dict(s) for s in sources]}

    rec = _FakeRec("https://example.com/n")

    class FakeSession:
        def query(self, *a, **k):
            return self

        def filter_by(self, **k):
            return self

        def first(self):
            return rec

        def commit(self):
            pass

        def close(self):
            pass

    store = PandasStore(data_dir=str(tmp_path))
    monkeypatch.setattr(nf, "_crawler", FakeCrawler())
    monkeypatch.setattr(nf, "_pandas_store", store)
    monkeypatch.setattr(nf, "_ai", FakeAI())
    monkeypatch.setattr(nf, "SessionLocal", FakeSession)
    monkeypatch.setattr(url_validator, "_is_url_alive", lambda u, timeout=3.0: alive(u))
    return store, rec, _json


def test_analyze_record_dead_tier1_verified_false(monkeypatch, tmp_path):
    store, rec, _ = _setup_analyze(
        monkeypatch, tmp_path,
        sources=[{"title": "MyGoPen", "url": "https://www.mygopen.com/2026/09/fake.html"}],
        alive=lambda u: False,
    )

    result = asyncio.run(nf._analyze_record("https://example.com/n", "一般新聞標題", "內" * 80))

    assert result == "ok"
    df = store.get_all_records()
    assert len(df) == 1
    row = df.iloc[0]
    assert bool(row["verified"]) is False
    assert list(row["sources"]) == []
    assert row["label_source"] == "ai"
    # SQLite 熱門列同步寫入
    assert rec.label_source == "ai"
    assert rec.verified is False
    assert rec.source_tier == 3
    assert rec.platform == "rss"


def test_analyze_record_tier3_moved_to_related(monkeypatch, tmp_path):
    store, rec, _json = _setup_analyze(
        monkeypatch, tmp_path,
        sources=[
            {"title": "TFC", "url": "https://tfc-taiwan.org.tw/articles/1"},
            {"title": "部落格", "url": "https://blog.example.com/p"},
        ],
        alive=lambda u: True,
    )

    result = asyncio.run(nf._analyze_record("https://example.com/n", "一般新聞標題", "內" * 80))

    assert result == "ok"
    row = store.get_all_records().iloc[0]
    assert bool(row["verified"]) is True
    urls = [s["url"] for s in row["sources"]]
    assert urls == ["https://tfc-taiwan.org.tw/articles/1"]
    assert all(int(s["tier"]) in (1, 2) and s["tier_label"] for s in row["sources"])
    related = _json.loads(row["related_discussions"])
    assert [r["url"] for r in related] == ["https://blog.example.com/p"]
    assert related[0]["tier"] == 3
    # trending 列 verified 只看 source_url（spec 6.3）：example.com 一般新聞 → Tier 3 → False
    assert rec.label_source == "ai"
    assert rec.source_tier == 3
    assert rec.verified is False


def test_analyze_record_tier1_source_url_verified_true(monkeypatch, tmp_path):
    """spec 6.3 / FR-18 規則 4 同一定義：ai 且 source_url 為 Tier 1/2 → verified True，
    即使 AI 回的來源全死（知識庫列仍 verified False）。"""
    url = "https://www.mygopen.com/2026/09/news.html"
    store, rec, _ = _setup_analyze(
        monkeypatch, tmp_path,
        sources=[{"title": "TFC", "url": "https://tfc-taiwan.org.tw/articles/1"}],
        alive=lambda u: False,
    )
    rec.source_url = url

    result = asyncio.run(nf._analyze_record(url, "一般新聞標題", "內" * 80))

    assert result == "ok"
    row = store.get_all_records().iloc[0]
    assert bool(row["verified"]) is False
    assert rec.source_tier == 1
    assert rec.verified is True


def test_analyze_record_cache_hit_ignores_unvalidated_cached_sources(monkeypatch, tmp_path):
    """快取命中分支：舊 KB 列帶未驗證的 Tier 1 來源（網址已死）也不可讓熱門列 verified=True。"""
    from app.utils import url_validator

    store, rec, _ = _setup_analyze(
        monkeypatch, tmp_path, sources=[], alive=lambda u: False,
    )
    cached = {"ai_analysis": {
        "is_risk": True, "risk_type": "MISINFO", "confidence_score": 0.9,
        "summary": "舊摘要", "category": "健康", "explanation": "x",
        "sources": [{"title": "MyGoPen", "url": "https://www.mygopen.com/2020/01/dead.html"}],
    }, "verified": False}

    class CachedStore:
        def find_by_hash(self, h):
            return cached

        def save_record(self, **kwargs):
            raise AssertionError("cache hit must not rewrite the KB row")

    class NoAI:
        def analyze_content(self, *a, **k):
            raise AssertionError("cache hit must not call AI")

    monkeypatch.setattr(nf, "_pandas_store", CachedStore())
    monkeypatch.setattr(nf, "_ai", NoAI())
    assert url_validator._is_url_alive("https://www.mygopen.com/2020/01/dead.html") is False

    result = asyncio.run(nf._analyze_record("https://example.com/n", "一般新聞標題", "內" * 80))

    assert result == "ok"
    assert rec.risk_type == "MISINFO"
    assert rec.label_source == "ai"
    assert rec.source_tier == 3
    assert rec.verified is False


def test_fill_record_provenance_matches_rule4(monkeypatch):
    """_fill_record_provenance 與 clean_sources 規則 4 同一定義，且 Cofacts 離線 3 不降級先前線上分級。"""
    import requests

    def _no_net(*a, **k):
        raise AssertionError("test must stay offline")

    monkeypatch.setattr(requests, "post", _no_net)

    rule = _FakeRec("https://example.com/a")
    rule.label_source = "rule"
    nf._fill_record_provenance(rule, rule.source_url, "一般標題")
    assert (rule.platform, rule.source_tier, rule.verified) == ("rss", 3, True)

    ai_t1 = _FakeRec("https://tfc-taiwan.org.tw/articles/9")
    ai_t1.label_source = "ai"
    ai_t1.verified = False
    nf._fill_record_provenance(ai_t1, ai_t1.source_url, "一般標題")
    assert (ai_t1.source_tier, ai_t1.verified) == (1, True)

    ai_t3 = _FakeRec("https://example.com/b")
    ai_t3.label_source = "ai"
    ai_t3.verified = True   # 舊值不可殘留
    nf._fill_record_provenance(ai_t3, ai_t3.source_url, "一般標題")
    assert (ai_t3.source_tier, ai_t3.verified) == (3, False)

    cof = _FakeRec("https://cofacts.tw/article/abc")
    cof.label_source = "ai"
    cof.source_tier = 1     # 清洗腳本線上查到有回覆
    nf._fill_record_provenance(cof, cof.source_url, "")
    assert (cof.platform, cof.source_tier, cof.verified) == ("cofacts", 1, True)

    pending = _FakeRec("https://tfc-taiwan.org.tw/articles/10")
    nf._fill_record_provenance(pending, pending.source_url, "")
    assert (pending.source_tier, pending.verified) == (1, False)
