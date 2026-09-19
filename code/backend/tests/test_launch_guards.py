"""
上線護欄接進端點後的行為（FN-10、spec §5.7）：每日 AI 次數上限、每 IP 限速、請求大小、圖片檔頭。
全 mock、離線、零 AI 點數；每日計數用 SQLite 暫存檔。
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

import app.api.analyze as analyze_api
import app.api.feedback as feedback_api
import app.main as main_module
import app.workers.pandas_task_processor as proc
from app.config import settings
from app.main import app
from app.services.ai_budget import AiBudget
from app.services.pandas_store import PandasStore
from app.services.task_store import TaskStore
from app.utils import rate_limit
from app.utils.body_limit import DEFAULT_MAX_BODY_BYTES, IMAGE_MAX_BYTES
from app.utils.rate_limit import SlidingWindowLimiter

RUMOR_A = "網傳吃香蕉配優格會中毒，醫師說千萬不要一起吃"
RUMOR_B = "緊急通知：健保卡即將失效，請點連結更新資料"

AI_OK = {
    "is_risk": True, "risk_type": "MISINFO", "category": "Health",
    "confidence_score": 0.9, "summary": "網傳說法沒有根據",
    "explanation": "香蕉與優格一起吃不會中毒。", "sources": [],
}

PNG_HEAD = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


class FakeAI:
    def __init__(self):
        self.calls = 0

    def analyze_content(self, content, url=None, context=None, use_web_search=None):
        self.calls += 1
        return dict(AI_OK)

    def analyze_image(self, image_path, url=None):
        self.calls += 1
        return dict(AI_OK)


class FakeVector:
    def vectorize_content(self, text):
        return []          # 向量層停用：只靠 hash 層命中


class ForbiddenCrawler:
    async def process_input(self, data, input_type):
        raise AssertionError("這些測試不應該爬網頁")


@pytest.fixture
def client():
    # 不進 lifespan：不啟動排程、不碰真的資料庫
    return TestClient(app)


@pytest.fixture
def pipeline(tmp_path, monkeypatch):
    """處理器與端點都指到 tmp_path，AI／向量／爬蟲全部換成假的。回傳 FakeAI 供斷言呼叫次數。"""
    fake_ai = FakeAI()
    task_store = TaskStore(data_dir=str(tmp_path))
    monkeypatch.setattr(analyze_api, "task_store", task_store)
    monkeypatch.setattr(analyze_api.settings, "DEMO_MODE", False)
    monkeypatch.setattr(proc, "TaskStore", lambda: TaskStore(data_dir=str(tmp_path)))
    monkeypatch.setattr(proc, "PandasStore", lambda: PandasStore(data_dir=str(tmp_path)))
    monkeypatch.setattr(proc, "CrawlerService", ForbiddenCrawler)
    monkeypatch.setattr(proc, "AIService", lambda: fake_ai)
    monkeypatch.setattr(proc, "VectorService", FakeVector)
    return fake_ai


@pytest.fixture
def budget(tmp_path, monkeypatch):
    """獨立的每日計數器（SQLite 暫存檔），換掉三個模組持有的單例。上限由各測試自己設。"""
    engine = create_engine(
        f"sqlite:///{tmp_path / 'budget.db'}", connect_args={"check_same_thread": False},
    )
    fresh = AiBudget(engine=engine)
    for module in (analyze_api, proc, main_module):
        monkeypatch.setattr(module, "ai_budget", fresh)
    yield fresh
    engine.dispose()


@pytest.fixture
def limiter(monkeypatch):
    fresh = SlidingWindowLimiter()
    monkeypatch.setattr(rate_limit, "limiter", fresh)
    return fresh


def _sync(client, content):
    return client.post("/api/analyze/sync", json={"content": content})


# ── 每日 AI 次數上限（FR-14／FN-10）────────────────────────────
def test_second_uncached_request_gets_429_and_ai_is_not_called(client, pipeline, budget, monkeypatch):
    monkeypatch.setattr(settings, "DAILY_AI_CALL_CAP", 1)

    first = _sync(client, RUMOR_A)
    assert first.status_code == 200 and first.json()["ai_unavailable"] is False
    assert pipeline.calls == 1

    second = _sync(client, RUMOR_B)
    assert second.status_code == 429
    assert second.json()["code"] == "daily_cap_reached"
    assert 1 <= int(second.headers["Retry-After"]) <= 24 * 3600
    assert pipeline.calls == 1                       # AI 沒有被呼叫第二次


def test_cache_hit_still_works_when_cap_is_reached(client, pipeline, budget, monkeypatch):
    monkeypatch.setattr(settings, "DAILY_AI_CALL_CAP", 1)
    assert _sync(client, RUMOR_A).status_code == 200

    again = _sync(client, RUMOR_A)                   # 同一段文字：hash 層命中
    assert again.status_code == 200
    body = again.json()
    assert body["cached"] is True and body["cache_layer"] == "hash"
    assert pipeline.calls == 1


@pytest.mark.parametrize("path", ["/api/analyze/text", "/api/analyze/url"])
def test_async_endpoints_refuse_before_creating_a_task(client, pipeline, budget, monkeypatch, path):
    monkeypatch.setattr(settings, "DAILY_AI_CALL_CAP", 1)
    monkeypatch.setattr(analyze_api, "blocked_url_response", _not_blocked)
    enqueued = []
    monkeypatch.setattr(analyze_api, "enqueue_analysis_task", lambda *a: enqueued.append(a))
    assert budget.try_consume() is True              # 今天的額度用完

    content = "https://example.org/rumor" if path.endswith("/url") else RUMOR_B
    resp = client.post(path, json={"content": content})
    assert resp.status_code == 429 and resp.json()["code"] == "daily_cap_reached"
    assert enqueued == []
    assert analyze_api.task_store._load_tasks().empty


async def _not_blocked(url):
    return None


def test_processor_backstop_returns_fallback_without_calling_ai(tmp_path, pipeline, budget, monkeypatch):
    """繞過端點直接進處理器（Threads 機器人、同時送出的競態）：額度用完就不呼叫 AI、不寫知識庫。"""
    import asyncio

    monkeypatch.setattr(settings, "DAILY_AI_CALL_CAP", 1)
    assert budget.try_consume() is True

    store = TaskStore(data_dir=str(tmp_path))
    task_id = store.create_task("analyze_text", RUMOR_B)
    result = asyncio.run(proc.process_analysis_task_async(task_id, RUMOR_B, "text"))

    assert result["ai_unavailable"] is True
    assert pipeline.calls == 0
    assert PandasStore(data_dir=str(tmp_path)).get_all_records().empty
    assert budget.calls_today() == 1                 # 被擋下的那次不計數


def test_cap_zero_means_unlimited(client, pipeline, budget, monkeypatch):
    monkeypatch.setattr(settings, "DAILY_AI_CALL_CAP", 0)
    assert _sync(client, RUMOR_A).status_code == 200
    assert _sync(client, RUMOR_B).status_code == 200
    assert pipeline.calls == 2


def test_health_reports_used_and_cap(client, budget, monkeypatch):
    monkeypatch.setattr(settings, "DAILY_AI_CALL_CAP", 5)
    budget.try_consume()
    budget.try_consume()
    body = client.get("/health").json()
    assert body["daily_ai_calls"] == {"used": 2, "cap": 5}


# ── 每 IP 限速 ─────────────────────────────────────────────────
def test_rate_limit_blocks_third_request_and_creates_no_task(client, pipeline, limiter, monkeypatch):
    monkeypatch.setattr(settings, "RATE_LIMIT_PER_MINUTE", 2)
    enqueued = []
    monkeypatch.setattr(analyze_api, "enqueue_analysis_task", lambda *a: enqueued.append(a))

    codes = [client.post("/api/analyze/text", json={"content": RUMOR_A}).status_code for _ in range(2)]
    assert codes == [200, 200]
    blocked = client.post("/api/analyze/text", json={"content": RUMOR_A})
    assert blocked.status_code == 429
    assert blocked.json()["code"] == "rate_limited"
    assert 1 <= int(blocked.headers["Retry-After"]) <= 60
    assert len(enqueued) == 2


def test_rate_limit_is_per_forwarded_client(client, pipeline, limiter, monkeypatch):
    monkeypatch.setattr(settings, "RATE_LIMIT_PER_MINUTE", 1)
    monkeypatch.setattr(analyze_api, "enqueue_analysis_task", lambda *a: None)

    def post(ip):
        return client.post(
            "/api/analyze/text", json={"content": RUMOR_A}, headers={"X-Forwarded-For": ip},
        ).status_code

    assert [post("198.51.100.7"), post("198.51.100.7"), post("198.51.100.8")] == [200, 429, 200]


def test_invalid_input_is_rejected_before_it_counts(client, pipeline, limiter, monkeypatch):
    monkeypatch.setattr(settings, "RATE_LIMIT_PER_MINUTE", 1)
    monkeypatch.setattr(analyze_api, "enqueue_analysis_task", lambda *a: None)
    assert client.post("/api/analyze/text", json={"content": "  "}).status_code == 422
    assert client.post("/api/analyze/url", json={"content": "not a url"}).status_code == 422
    assert client.post("/api/analyze/text", json={"content": RUMOR_A}).status_code == 200


def test_feedback_has_its_own_bucket_and_length_caps(client, tmp_path, limiter, monkeypatch):
    monkeypatch.setattr(settings, "RATE_LIMIT_PER_MINUTE", 1)
    store = TaskStore(data_dir=str(tmp_path))
    task_id = store.create_task("analyze_text", RUMOR_A)
    saved = []

    class FakeAudit:
        def append_feedback(self, **kwargs):
            saved.append(kwargs)

    monkeypatch.setattr(feedback_api, "task_store", store)
    monkeypatch.setattr(feedback_api, "audit_store", FakeAudit())
    url = f"/api/feedback/tasks/{task_id}"

    assert client.post(url, json={"rating": "agree", "comment": "字" * 2001}).status_code == 422
    assert client.post(url, json={"rating": "agree"}).status_code == 200
    second = client.post(url, json={"rating": "agree"})
    assert second.status_code == 429 and second.json()["code"] == "rate_limited"
    assert len(saved) == 1


# ── 請求大小 ───────────────────────────────────────────────────
def test_oversized_json_is_413_before_validation(client, pipeline):
    resp = client.post("/api/analyze/text", json={"content": "字" * (DEFAULT_MAX_BODY_BYTES // 2)})
    assert resp.status_code == 413
    assert resp.json() == {"detail": "內容太大，無法處理。", "code": "payload_too_large"}


def test_oversized_body_without_content_length_is_413(client, pipeline):
    def chunks():
        yield b'{"content": "'
        yield b"a" * (DEFAULT_MAX_BODY_BYTES + 10)
        yield b'"}'

    resp = client.post(
        "/api/analyze/text", content=chunks(), headers={"Content-Type": "application/json"},
    )
    assert resp.status_code == 413
    assert resp.json()["code"] == "payload_too_large"


def test_normal_sized_request_is_untouched(client, pipeline, monkeypatch):
    monkeypatch.setattr(analyze_api, "enqueue_analysis_task", lambda *a: None)
    assert client.post("/api/analyze/text", json={"content": "字" * 20000}).status_code == 200


# ── 圖片上傳（FR-03 驗收 1）────────────────────────────────────
@pytest.fixture
def image_env(tmp_path, monkeypatch, pipeline):
    monkeypatch.chdir(tmp_path)                       # 端點把上傳檔寫到相對路徑 data/uploads
    enqueued = []
    monkeypatch.setattr(analyze_api, "enqueue_analysis_task", lambda *a: enqueued.append(a))
    return enqueued


def _upload(client, data, filename="x.png"):
    return client.post("/api/analyze/image", files={"file": (filename, data, "image/png")})


def test_image_with_wrong_magic_bytes_is_415(client, image_env):
    resp = _upload(client, b"<html>not an image</html>", filename="evil.png")
    assert resp.status_code == 415 and resp.json()["code"] == "unsupported_media"
    assert image_env == []


def test_image_over_10mb_is_413(client, image_env):
    resp = _upload(client, PNG_HEAD + b"\x00" * IMAGE_MAX_BYTES)
    assert resp.status_code == 413 and resp.json()["code"] == "payload_too_large"
    assert image_env == []


@pytest.mark.parametrize("head, ext", [
    (PNG_HEAD, "png"),
    (b"\xff\xd8\xff\xe0" + b"\x00" * 32, "jpg"),
    (b"RIFF\x24\x00\x00\x00WEBPVP8 " + b"\x00" * 32, "webp"),
])
def test_valid_image_is_accepted_and_named_by_detected_type(client, image_env, tmp_path, head, ext):
    resp = _upload(client, head, filename="photo.exe")           # 檔名不可信
    assert resp.status_code == 200
    body = resp.json()
    assert body["result_id"] == body["task_id"]
    (task_id, path, kind), = image_env
    assert kind == "image" and path.endswith(f"{task_id}.{ext}")
    assert (tmp_path / path).read_bytes() == head


def test_image_is_refused_when_daily_cap_is_reached(client, image_env, budget, monkeypatch):
    monkeypatch.setattr(settings, "DAILY_AI_CALL_CAP", 1)
    assert budget.try_consume() is True
    resp = _upload(client, PNG_HEAD)
    assert resp.status_code == 429 and resp.json()["code"] == "daily_cap_reached"
    assert image_env == []
