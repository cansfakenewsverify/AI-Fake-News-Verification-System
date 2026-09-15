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

    def fetch_rss_items(num_per_feed=4):
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
