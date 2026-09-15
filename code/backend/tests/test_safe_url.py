"""SSRF 防護測試（B-18 / FN-2a）：全部 mock DNS 與 requests，離線、零點數。"""
import socket
import threading
import time

import pytest
import requests

import app.utils.safe_url as su
from app.config import settings


def _fake_getaddrinfo(mapping):
    def fake(host, port, *args, **kwargs):
        if host not in mapping:
            raise socket.gaierror("unknown host")
        out = []
        for addr in mapping[host]:
            family = socket.AF_INET6 if ":" in addr else socket.AF_INET
            sockaddr = (addr, port, 0, 0) if family == socket.AF_INET6 else (addr, port)
            out.append((family, socket.SOCK_STREAM, 6, "", sockaddr))
        return out
    return fake


class _FakeResp:
    def __init__(self, status=200, headers=None, chunks=(b"<html>ok</html>",)):
        self.status_code = status
        self.headers = headers or {}
        self._chunks = list(chunks)
        self.encoding = "utf-8"
        self.closed = False

    def iter_content(self, chunk_size=1):
        for c in self._chunks:
            yield c

    def close(self):
        self.closed = True


@pytest.fixture
def calls(monkeypatch):
    """記錄 requests.request 呼叫；回應由 test 以 calls.responses 排隊。"""
    class Recorder:
        def __init__(self):
            self.kwargs = []
            self.responses = []

    rec = Recorder()

    def fake_request(method, url, **kwargs):
        rec.kwargs.append({"method": method, "url": url, **kwargs})
        if rec.responses:
            r = rec.responses.pop(0)
            if isinstance(r, Exception):
                raise r
            return r
        return _FakeResp()

    monkeypatch.setattr(su.requests, "request", fake_request)
    return rec


BLOCKED_SAMPLES = [
    ("http://127.0.0.1/", {"127.0.0.1": ["127.0.0.1"]}),
    ("http://10.0.0.5/admin", {"10.0.0.5": ["10.0.0.5"]}),
    ("http://172.16.3.4/", {"172.16.3.4": ["172.16.3.4"]}),
    ("http://192.168.1.1/", {"192.168.1.1": ["192.168.1.1"]}),
    ("http://169.254.169.254/latest/meta-data", {"169.254.169.254": ["169.254.169.254"]}),
    ("http://[::1]/", {"::1": ["::1"]}),
    ("http://[fd00::1]/", {"fd00::1": ["fd00::1"]}),
    ("http://localhost/", {"localhost": ["127.0.0.1"]}),
    ("http://printer.local/", {"printer.local": ["93.184.216.34"]}),
    ("ftp://example.com/file", {"example.com": ["93.184.216.34"]}),
]


@pytest.mark.parametrize("url,dns", BLOCKED_SAMPLES)
def test_blocks_private_and_protocol_samples(monkeypatch, calls, url, dns):
    monkeypatch.setattr(su.socket, "getaddrinfo", _fake_getaddrinfo(dns))
    with pytest.raises(su.BlockedURL):
        su.check_url(url)
    with pytest.raises(su.BlockedURL):
        su.safe_get(url)
    assert len(calls.kwargs) == 0


def test_blocks_non_default_port_and_mixed_dns(monkeypatch, calls):
    monkeypatch.setattr(su.socket, "getaddrinfo", _fake_getaddrinfo(
        {"example.com": ["93.184.216.34"], "mixed.example.com": ["93.184.216.34", "10.1.2.3"]}))
    with pytest.raises(su.BlockedURL):
        su.check_url("http://example.com:8080/")
    with pytest.raises(su.BlockedURL):
        su.check_url("https://mixed.example.com/")
    assert len(calls.kwargs) == 0


@pytest.mark.parametrize("url,dns", [
    ("https://www.example.com/news/1", {"www.example.com": ["93.184.216.34"]}),
    ("http://tfc-taiwan.org.tw/articles/1", {"tfc-taiwan.org.tw": ["1.1.1.1"]}),
    ("https://v6.example.org:443/x", {"v6.example.org": ["2606:4700::1111"]}),
])
def test_allows_public_samples(monkeypatch, calls, url, dns):
    monkeypatch.setattr(su.socket, "getaddrinfo", _fake_getaddrinfo(dns))
    assert su.check_url(url) is None
    resp = su.safe_get(url)
    assert resp.status_code == 200
    assert resp.content == b"<html>ok</html>"
    assert len(calls.kwargs) == 1
    assert calls.kwargs[0]["allow_redirects"] is False


def test_redirect_to_private_blocked(monkeypatch, calls):
    monkeypatch.setattr(su.socket, "getaddrinfo", _fake_getaddrinfo(
        {"evil.example.com": ["93.184.216.34"], "169.254.169.254": ["169.254.169.254"]}))
    calls.responses = [_FakeResp(302, {"Location": "http://169.254.169.254/latest/meta-data"})]
    with pytest.raises(su.BlockedURL):
        su.safe_get("https://evil.example.com/r")
    # 只發出第一跳，轉址目標未被請求
    assert len(calls.kwargs) == 1
    assert calls.kwargs[0]["url"] == "https://evil.example.com/r"


def test_redirects_followed_up_to_three(monkeypatch, calls):
    monkeypatch.setattr(su.socket, "getaddrinfo", _fake_getaddrinfo(
        {"a.example.com": ["93.184.216.34"]}))
    calls.responses = [_FakeResp(301, {"Location": f"/hop{i}"}) for i in range(3)] + [_FakeResp()]
    assert su.safe_get("https://a.example.com/").url == "https://a.example.com/hop2"
    calls.kwargs.clear()
    calls.responses = [_FakeResp(301, {"Location": f"/hop{i}"}) for i in range(4)]
    with pytest.raises(su.TooManyRedirects):
        su.safe_get("https://a.example.com/")
    assert len(calls.kwargs) == 4


def test_connect_timeout_is_10s(monkeypatch, calls):
    monkeypatch.setattr(su.socket, "getaddrinfo", _fake_getaddrinfo(
        {"www.example.com": ["93.184.216.34"]}))
    su.safe_get("https://www.example.com/")
    assert calls.kwargs[0]["timeout"][0] == 10
    calls.responses = [requests.exceptions.ConnectTimeout("connect timed out")]
    with pytest.raises(su.FetchTimeout):
        su.safe_get("https://www.example.com/")


def test_total_timeout_uses_crawler_timeout(monkeypatch, calls):
    monkeypatch.setattr(su.socket, "getaddrinfo", _fake_getaddrinfo(
        {"www.example.com": ["93.184.216.34"]}))
    monkeypatch.setattr(settings, "CRAWLER_TIMEOUT", 30)
    su.safe_get("https://www.example.com/")
    # read 逾時 = min(CRAWLER_TIMEOUT, 剩餘時間)：第一跳幾乎是完整的 30 s，且不超過
    assert 29.0 < calls.kwargs[0]["timeout"][1] <= 30

    # 牆鐘：開始於 t=1000，讀第二個 chunk 時已過 31 s -> 總逾時中止
    t = {"now": 1000.0}
    monkeypatch.setattr(su.time, "monotonic", lambda: t["now"])

    class _SlowChunks(_FakeResp):
        def iter_content(self, chunk_size=1):
            yield b"a" * 10
            t["now"] += 31.0
            yield b"b" * 10

    calls.responses = [_SlowChunks(200, {})]
    with pytest.raises(su.FetchTimeout):
        su.safe_get("https://www.example.com/")


# ---- 真實牆鐘：慢速 / 阻塞的伺服器不能把一次抓取拖過總時限 ----

class _TrickleResp(_FakeResp):
    """每個 chunk 前真的 sleep：模擬每幾秒才送一點資料的伺服器。"""

    def __init__(self, delay, n_chunks):
        super().__init__(200, {})
        self.delay = delay
        self.n = n_chunks

    def iter_content(self, chunk_size=1):
        assert chunk_size <= 8192
        for _ in range(self.n):
            time.sleep(self.delay)
            yield b"x"


class _BlockingResp(_FakeResp):
    """read 阻塞到被 close() 為止（模擬 urllib3 read(n) 等不到 n bytes 卡住）。"""

    def __init__(self):
        super().__init__(200, {})
        self._closed = threading.Event()

    def iter_content(self, chunk_size=1):
        yield b"partial"
        self._closed.wait(10)  # 看門狗應在 deadline close 我們
        return  # 假 EOF

    def close(self):
        self.closed = True
        self._closed.set()


def _public_dns(monkeypatch):
    monkeypatch.setattr(su.socket, "getaddrinfo", _fake_getaddrinfo(
        {"www.example.com": ["93.184.216.34"], "slow.example.com": ["93.184.216.34"]}))


def test_trickling_body_bounded_by_wall_clock(monkeypatch, calls):
    _public_dns(monkeypatch)
    monkeypatch.setattr(settings, "CRAWLER_TIMEOUT", 1)
    calls.responses = [_TrickleResp(delay=0.25, n_chunks=40)]  # 不設限要 10 s
    start = time.monotonic()
    with pytest.raises(su.FetchTimeout):
        su.safe_get("https://www.example.com/trickle")
    assert time.monotonic() - start < 1.8


def test_blocked_read_is_aborted_at_deadline(monkeypatch, calls):
    _public_dns(monkeypatch)
    monkeypatch.setattr(settings, "CRAWLER_TIMEOUT", 1)
    resp = _BlockingResp()
    calls.responses = [resp]
    start = time.monotonic()
    with pytest.raises(su.FetchTimeout):  # 被截斷的內文不能當成功回傳
        su.safe_get("https://www.example.com/stuck")
    assert time.monotonic() - start < 2.0
    assert resp.closed


def test_slow_headers_bounded_by_wall_clock(monkeypatch):
    _public_dns(monkeypatch)
    monkeypatch.setattr(settings, "CRAWLER_TIMEOUT", 1)

    def slow_request(method, url, **kwargs):
        time.sleep(3)  # 連線 / 回標頭一直拖
        return _FakeResp()

    monkeypatch.setattr(su.requests, "request", slow_request)
    start = time.monotonic()
    with pytest.raises(su.FetchTimeout):
        su.safe_get("https://www.example.com/")
    assert time.monotonic() - start < 1.8


def test_later_hop_gets_only_remaining_time(monkeypatch, calls):
    _public_dns(monkeypatch)
    monkeypatch.setattr(settings, "CRAWLER_TIMEOUT", 30)
    t = {"now": 1000.0}
    monkeypatch.setattr(su.time, "monotonic", lambda: t["now"])

    class _LateRedirect(_FakeResp):
        @property
        def headers(self):
            if not getattr(self, "_spent", False):
                self._spent = True
                t["now"] += 25.0  # 第一跳花掉 25 s
            return {"Location": "/next"}

        @headers.setter
        def headers(self, value):
            pass

    calls.responses = [_LateRedirect(302), _FakeResp()]
    su.safe_get("https://www.example.com/")
    connect2, read2 = calls.kwargs[1]["timeout"]
    assert connect2 <= 5.0 and read2 <= 5.0


def test_hanging_dns_is_bounded(monkeypatch, calls):
    def hang(*args, **kwargs):
        time.sleep(3)
        return []

    monkeypatch.setattr(su.socket, "getaddrinfo", hang)
    start = time.monotonic()
    with pytest.raises(su.FetchTimeout):
        su.safe_get("https://slow-dns.example.com/", timeout=(1, 1))
    assert time.monotonic() - start < 1.8
    assert len(calls.kwargs) == 0
    monkeypatch.setattr(su, "DNS_TIMEOUT", 0.5)
    with pytest.raises(su.FetchTimeout):
        su.check_url("https://slow-dns.example.com/")


def test_custom_timeout_overrides_crawler_defaults(monkeypatch, calls):
    _public_dns(monkeypatch)
    monkeypatch.setattr(settings, "CRAWLER_TIMEOUT", 30)
    su.safe_get("https://www.example.com/", method="HEAD", timeout=(3, 3))
    connect, read = calls.kwargs[0]["timeout"]
    assert connect <= 3 and read <= 3


def test_response_over_2mb_aborted(monkeypatch, calls):
    monkeypatch.setattr(su.socket, "getaddrinfo", _fake_getaddrinfo(
        {"www.example.com": ["93.184.216.34"]}))
    chunk = b"x" * (512 * 1024)
    calls.responses = [_FakeResp(200, {}, chunks=[chunk] * 5)]  # 2.5 MB，無 Content-Length
    with pytest.raises(su.TooLarge):
        su.safe_get("https://www.example.com/big")
    calls.responses = [_FakeResp(200, {"Content-Length": str(3 * 1024 * 1024)})]
    with pytest.raises(su.TooLarge):
        su.safe_get("https://www.example.com/big2")


def test_dns_failure_is_not_blocked(monkeypatch, calls):
    monkeypatch.setattr(su.socket, "getaddrinfo", _fake_getaddrinfo({}))
    with pytest.raises(su.UnresolvableURL) as ei:
        su.check_url("https://no-such-host.example/")
    assert not isinstance(ei.value, su.BlockedURL)
    assert len(calls.kwargs) == 0


# ---- crawler / url_validator 接線 ----

def test_crawler_blocked_url_error_code(monkeypatch, calls):
    import asyncio
    from app.services.crawler import CrawlerService

    monkeypatch.setattr(su.socket, "getaddrinfo", _fake_getaddrinfo(
        {"169.254.169.254": ["169.254.169.254"]}))
    res = asyncio.run(CrawlerService.crawl_url("http://169.254.169.254/latest/meta-data"))
    assert res["success"] is False
    assert res["error_code"] == "blocked_url"
    assert len(calls.kwargs) == 0


def test_crawler_error_codes_http_error_and_too_short(monkeypatch, calls):
    import asyncio
    from app.services.crawler import CrawlerService

    monkeypatch.setattr(su.socket, "getaddrinfo", _fake_getaddrinfo(
        {"www.example.com": ["93.184.216.34"]}))
    calls.responses = [_FakeResp(404)]
    res = asyncio.run(CrawlerService.crawl_url("https://www.example.com/404"))
    assert res["success"] is False and res["error_code"] == "http_error"

    calls.responses = [_FakeResp(200, {}, chunks=[b"<html><body>hi</body></html>"])]
    res = asyncio.run(CrawlerService.crawl_url("https://www.example.com/short"))
    assert res["success"] is False and res["error_code"] == "too_short"
    assert len(calls.kwargs) == 2  # 備援解析不重抓網頁


def test_crawler_success_uses_safe_get(monkeypatch, calls):
    import asyncio
    from app.services.crawler import CrawlerService

    monkeypatch.setattr(su.socket, "getaddrinfo", _fake_getaddrinfo(
        {"www.example.com": ["93.184.216.34"]}))
    body = "這是一段足夠長的新聞內文，用來測試爬蟲是否能正確擷取內容。" * 5
    html = f"<html><head><title>測試標題</title></head><body><p>{body}</p></body></html>"
    calls.responses = [_FakeResp(200, {}, chunks=[html.encode("utf-8")])]
    res = asyncio.run(CrawlerService.crawl_url("https://www.example.com/news"))
    assert res["success"] is True
    assert "足夠長的新聞內文" in res["content"]
    assert len(calls.kwargs) == 1


def test_url_validator_blocks_private_without_request(monkeypatch, calls):
    import app.utils.url_validator as uv

    monkeypatch.setattr(su.socket, "getaddrinfo", _fake_getaddrinfo(
        {"10.0.0.1": ["10.0.0.1"], "www.example.com": ["93.184.216.34"]}))
    assert uv._is_url_alive("http://10.0.0.1/") is False
    assert len(calls.kwargs) == 0

    calls.responses = [_FakeResp(405), _FakeResp(200)]
    assert uv._is_url_alive("https://www.example.com/") is True
    assert [k["method"] for k in calls.kwargs] == ["HEAD", "GET"]
    # 存活檢查維持 3 s 短預算，不沿用爬蟲的 (10, CRAWLER_TIMEOUT)
    for k in calls.kwargs:
        assert k["timeout"][0] <= 3.0 and k["timeout"][1] <= 3.0


# ---- B-19：端點 blocked_url 422、爬取失敗 UNVERIFIABLE、同網域來源剔除 ----

def _proc_patch(monkeypatch, tmp_path, crawler_cls, fake_ai):
    import app.workers.pandas_task_processor as proc
    from app.services.pandas_store import PandasStore
    from app.services.task_store import TaskStore

    class NoVector:
        def vectorize_content(self, text):
            return []

    monkeypatch.setattr(proc, "TaskStore", lambda: TaskStore(data_dir=str(tmp_path)))
    monkeypatch.setattr(proc, "PandasStore", lambda: PandasStore(data_dir=str(tmp_path)))
    monkeypatch.setattr(proc, "CrawlerService", crawler_cls)
    monkeypatch.setattr(proc, "AIService", lambda: fake_ai)
    monkeypatch.setattr(proc, "VectorService", NoVector)
    return proc


class _CountingAI:
    def __init__(self, result=None):
        self.calls = 0
        self.result = result or {
            "is_risk": True, "risk_type": "MISINFO", "category": "Health",
            "confidence_score": 0.9, "summary": "不實健康訊息", "explanation": "查核機構已澄清。",
            "sources": [],
        }

    def analyze_content(self, content, url=None, context=None, use_web_search=None):
        self.calls += 1
        return dict(self.result)


def _run_url(proc, tmp_path, url):
    import asyncio
    from app.services.task_store import TaskStore

    ts = TaskStore(data_dir=str(tmp_path))
    tid = ts.create_task("analyze_url", url, input_type="url", origin="web")
    result = asyncio.run(proc.process_analysis_task_async(tid, url, "url"))
    return ts, tid, result


@pytest.mark.parametrize("path", ["/api/analyze/url", "/api/analyze/sync"])
def test_blocked_url_endpoint_422_no_request(monkeypatch, calls, tmp_path, path):
    from fastapi.testclient import TestClient

    import app.api.analyze as analyze_api
    import app.workers.pandas_task_processor as proc
    from app.main import app
    from app.services.task_store import TaskStore

    monkeypatch.setattr(su.socket, "getaddrinfo", _fake_getaddrinfo(
        {"169.254.169.254": ["169.254.169.254"], "127.0.0.1": ["127.0.0.1"]}))
    ts = TaskStore(data_dir=str(tmp_path))
    monkeypatch.setattr(analyze_api, "task_store", ts)
    monkeypatch.setattr(analyze_api.settings, "DEMO_MODE", False)
    created, enqueued, processed = [], [], []
    real_create = ts.create_task

    def spy_create(*a, **kw):
        created.append(a)
        return real_create(*a, **kw)

    monkeypatch.setattr(ts, "create_task", spy_create)
    monkeypatch.setattr(analyze_api, "enqueue_analysis_task", lambda *a: enqueued.append(a))

    async def fake_process(*a):
        processed.append(a)
        return {}

    monkeypatch.setattr(proc, "process_analysis_task_async", fake_process)

    client = TestClient(app)
    for url in ("http://169.254.169.254/latest/meta-data", " http://127.0.0.1/admin "):
        resp = client.post(path, json={"content": url})
        assert resp.status_code == 422
        body = resp.json()
        assert body["code"] == "blocked_url"
        assert isinstance(body["detail"], str) and body["detail"]
    assert len(calls.kwargs) == 0
    assert created == [] and enqueued == [] and processed == []


@pytest.mark.parametrize("error_code,reason", [
    ("timeout", "連線逾時"),
    ("too_large", "網頁超過 2 MB"),
    ("http_error", "網頁無法存取"),
    ("too_short", "網頁內文過短"),
    ("blocked_url", "網址指向內部或保留位址"),
])
def test_crawl_failure_returns_unverifiable_no_ai(monkeypatch, tmp_path, error_code, reason):
    from app.services.pandas_store import PandasStore

    class FailingCrawler:
        async def process_input(self, data, input_type):
            return {"success": False, "error_code": error_code, "error": error_code, "url": data}

    fake_ai = _CountingAI()
    proc = _proc_patch(monkeypatch, tmp_path, FailingCrawler, fake_ai)
    ts, tid, result = _run_url(proc, tmp_path, "https://www.example.com/news/1")

    assert fake_ai.calls == 0
    assert result["risk_type"] == "UNVERIFIABLE"
    assert result["frame_type"] == "yellow" and result["frame_label"] == "無法查證"
    assert result["explanation"] == f"無法讀取此網頁內容（{reason}），請改貼文字內容再試"
    assert result["ai_unavailable"] is False
    assert result["verification_status"] == "unverified" and result["sources"] == []
    assert ts.get_task(tid)["status"] == "completed"
    assert PandasStore(data_dir=str(tmp_path)).get_all_records().empty


def test_crawl_failure_real_crawler_http_404(monkeypatch, calls, tmp_path):
    """真的 CrawlerService（safe_get mock 回 404）→ UNVERIFIABLE，不 raise、不呼叫 AI。"""
    from app.services.crawler import CrawlerService

    monkeypatch.setattr(su.socket, "getaddrinfo", _fake_getaddrinfo(
        {"www.example.com": ["93.184.216.34"]}))
    calls.responses = [_FakeResp(404)]
    fake_ai = _CountingAI()
    proc = _proc_patch(monkeypatch, tmp_path, CrawlerService, fake_ai)
    ts, tid, result = _run_url(proc, tmp_path, "https://www.example.com/gone")
    assert fake_ai.calls == 0
    assert result["risk_type"] == "UNVERIFIABLE" and result["frame_label"] == "無法查證"
    assert "網頁無法存取" in result["explanation"]
    assert ts.get_task(tid)["status"] == "completed"


@pytest.mark.parametrize("url", [
    "https://www.youtube.com/watch?v=abc",
    "https://youtu.be/abc",
    "https://www.facebook.com/somepage/posts/1",
    "https://www.instagram.com/p/xyz/",
])
def test_unsupported_platform_unverifiable_copy(monkeypatch, calls, tmp_path, url):
    from app.services.crawler import CrawlerService
    from app.services.pandas_store import PandasStore

    monkeypatch.setattr(su.socket, "getaddrinfo", _fake_getaddrinfo({}))
    fake_ai = _CountingAI()
    proc = _proc_patch(monkeypatch, tmp_path, CrawlerService, fake_ai)
    ts, tid, result = _run_url(proc, tmp_path, url)

    assert fake_ai.calls == 0
    assert len(calls.kwargs) == 0
    assert result["risk_type"] == "UNVERIFIABLE"
    assert result["frame_type"] == "yellow" and result["frame_label"] == "無法查證"
    assert result["explanation"] == "目前不支援影片與 Facebook／Instagram 連結，請貼上文字內容"
    assert ts.get_task(tid)["status"] == "completed"
    assert PandasStore(data_dir=str(tmp_path)).get_all_records().empty


def test_same_domain_source_removed(monkeypatch, tmp_path):
    from app.services.pandas_store import PandasStore

    input_url = "https://news.example.com.tw/article/123"

    class OkCrawler:
        async def process_input(self, data, input_type):
            body = "網傳某縣市自來水含有致癌物質，喝了會生病，請大家趕快轉傳給親友知道。" * 3
            return {"success": True, "url": data, "title": "網傳自來水致癌", "content": body}

    fake_ai = _CountingAI({
        "is_risk": True, "risk_type": "MISINFO", "category": "Health",
        "confidence_score": 0.9, "summary": "不實健康訊息", "explanation": "查核機構已澄清。",
        "sources": [
            {"title": "原文", "url": "https://news.example.com.tw/article/123"},
            {"title": "同站其他頁", "url": "https://www.example.com.tw/fact"},
            {"title": "同站根網域", "url": "http://example.com.tw/"},
            {"title": "台灣事實查核中心", "url": "https://tfc-taiwan.org.tw/articles/999"},
            {"title": "衛福部澄清", "url": "https://www.mohw.gov.tw/cp-1.html"},
        ],
    })
    proc = _proc_patch(monkeypatch, tmp_path, OkCrawler, fake_ai)
    seen = {}

    def passthrough(sources):
        seen["validated"] = [s["url"] for s in sources]
        return sources

    monkeypatch.setattr(proc, "filter_valid_sources", passthrough)
    ts, tid, result = _run_url(proc, tmp_path, input_url)

    assert fake_ai.calls == 1
    urls = [s.get("url") or "" for s in result["sources"] + result["related_discussions"]]
    assert not any("example.com.tw" in u for u in urls)
    assert [s["url"] for s in result["sources"]] == [
        "https://tfc-taiwan.org.tw/articles/999", "https://www.mohw.gov.tw/cp-1.html",
    ]
    # 剔除發生在來源驗證／分級之前
    assert not any("example.com.tw" in u for u in seen["validated"])
    df = PandasStore(data_dir=str(tmp_path)).get_all_records()
    assert len(df) == 1
    assert "example.com.tw/article" not in str(df.iloc[0]["ai_analysis"]).replace(input_url, "")
    assert "www.example.com.tw" not in str(df.iloc[0].get("sources"))


@pytest.mark.parametrize("layer", ["url", "hash", "vector"])
def test_same_domain_source_removed_on_cache_hit(monkeypatch, tmp_path, layer):
    """FR-02 驗收 6：快取命中（L0 url／L1 hash／L2 向量）也要剔除與輸入網址同站的來源。"""
    from app.services.pandas_store import PandasStore

    input_url = "https://www.mygopen.com/2026/09/abc.html"
    row = {
        "id": "kb-1",
        "label_source": "ai",
        "ai_analysis": {
            "is_risk": True, "risk_type": "MISINFO", "category": "Health",
            "confidence_score": 0.9, "summary": "不實健康訊息", "explanation": "查核機構已澄清。",
        },
        "sources": [
            {"title": "MyGoPen 本文", "url": "https://www.mygopen.com/2026/09/abc.html", "tier": 1},
            {"title": "MyGoPen 子網域", "url": "https://m.mygopen.com/other", "tier": 1},
            {"title": "台灣事實查核中心", "url": "https://tfc-taiwan.org.tw/articles/999", "tier": 1},
        ],
        "related_discussions": [
            {"title": "MyGoPen 討論", "url": "https://mygopen.com/talk", "tier": 3},
            {"title": "PTT 討論", "url": "https://www.ptt.cc/bbs/x.html", "tier": 3},
        ],
    }

    class OkCrawler:
        async def process_input(self, data, input_type):
            body = "網傳某縣市自來水含有致癌物質，喝了會生病，請大家趕快轉傳給親友知道。" * 3
            return {"success": True, "url": data, "title": "網傳自來水致癌", "content": body}

    class HitStore(PandasStore):
        def find_by_url(self, url):
            return dict(row) if layer == "url" else None

        def find_by_hash(self, content_hash):
            return dict(row) if layer == "hash" else None

        def find_similar_by_vector(self, vector, *a, **kw):
            return dict(row) if layer == "vector" else None

    class SomeVector:
        def vectorize_content(self, text):
            return [0.1, 0.2, 0.3]

    fake_ai = _CountingAI()
    proc = _proc_patch(monkeypatch, tmp_path, OkCrawler, fake_ai)
    monkeypatch.setattr(proc, "PandasStore", lambda: HitStore(data_dir=str(tmp_path)))
    monkeypatch.setattr(proc, "VectorService", SomeVector)
    ts, tid, result = _run_url(proc, tmp_path, input_url)

    assert fake_ai.calls == 0
    assert result["cached"] is True and result["cache_layer"] == layer
    urls = [s.get("url") or "" for s in result["sources"] + result["related_discussions"]]
    assert not any("mygopen.com" in u for u in urls)
    assert [s["url"] for s in result["sources"]] == ["https://tfc-taiwan.org.tw/articles/999"]
    assert [s["url"] for s in result["related_discussions"]] == ["https://www.ptt.cc/bbs/x.html"]
    assert result["verification_status"] == "verified"


def test_site_domain_helper():
    import app.workers.pandas_task_processor as proc

    assert proc._site_domain("https://www.mygopen.com/x") == "mygopen.com"
    assert proc._site_domain("https://a.b.mygopen.com/x") == "mygopen.com"
    assert proc._site_domain("https://news.ltn.com.tw/x") == "ltn.com.tw"
    assert proc._site_domain("https://www.cdc.gov.tw/x") == "cdc.gov.tw"
    assert proc._site_domain("ftp://example.com") == ""
    kept = proc._drop_same_domain_sources(
        [{"url": "https://www.cdc.gov.tw/a"}, {"url": "https://www.mohw.gov.tw/b"}],
        "https://cdc.gov.tw/news",
    )
    assert kept == [{"url": "https://www.mohw.gov.tw/b"}]
