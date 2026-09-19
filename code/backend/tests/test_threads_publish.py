"""T-12／T-13：ThreadsService（live 類別）的兩段式發佈與 HTTP 錯誤分類。

**T-17 實測後覆核**：以下假回應的形狀（container 的 {"id"}、GET /{container_id}?fields=status,error_message
回 {"status", "error_message"}、threads_publish 回 {"id"}、錯誤 body 的 {"error": {...}}）依 spec §7.6／§7.10
撰寫，尚未與真的 Threads API 回應核對；T-17（OP-5 live 探測）完成後請以實際 JSON 覆核本檔。

全部離線：threads_service.requests 的 get／post 以假函式取代並記錄每次呼叫，requests.Session.request
另外封鎖（任何漏網的真請求都會讓測試失敗）；等待一律注入或 patch time.sleep，不會真的睡；
AI 以假的 process_analysis_task_async 取代（零點數）。sim 模式（FakeThreadsService）的同一套行為
見 test_threads_bot_sim.py 的 test_container_*／test_backoff_*。
"""
import asyncio
import json
import logging
from datetime import datetime, timezone

import pytest
import requests

import app.workers.pandas_task_processor as proc
from app.config import settings
from app.services import threads_service as ts
from app.services import threads_state
from app.services.task_store import TaskStore
from app.services.threads_service import (
    ThreadsAPIError,
    ThreadsApiError,
    ThreadsClient,
    ThreadsService,
    ThreadsTransientError,
    is_link_limit_error,
)
from app.workers import threads_bot

BASE_URL = "https://graph.threads.net/v1.0"
USER_ID = "4242"
TOKEN = "LIVE-SECRET-TOKEN-123"
PUBLIC = "https://factcheck-demo.vercel.app"
RUMOR = "網傳吃香蕉配優格會中毒，腸胃不好的人千萬不要一起吃"
TIER1_URL = "https://www.mygopen.com/2026/09/banana-yogurt.html"
AI_MISINFO = {
    "is_risk": True, "risk_type": "MISINFO", "category": "Health", "confidence_score": 0.9,
    "summary": "香蕉配優格會中毒是沒有根據的謠言", "explanation": "查核機構已說明兩者一起吃沒有問題。",
    "sources": [{"title": "MyGoPen：香蕉配優格中毒是謠言", "url": TIER1_URL}],
}


@pytest.fixture(autouse=True)
def _no_real_network(monkeypatch):
    def _blocked(*args, **kwargs):
        raise AssertionError("real network access is not allowed in these tests")

    monkeypatch.setattr(requests.Session, "request", _blocked)
    for name in ("get", "post", "request"):
        monkeypatch.setattr(requests, name, _blocked)


@pytest.fixture(autouse=True)
def _no_leftover_poll_lock(tmp_path):
    yield
    assert [str(p) for p in tmp_path.rglob("threads_poll.lock")] == []
    assert not threads_bot._POLL_LOCK.locked()


def _response(status, payload=None, url=f"{BASE_URL}/x", text=None):
    resp = requests.Response()
    resp.status_code = status
    if text is not None:
        resp._content = text.encode("utf-8")
    else:
        resp._content = json.dumps(payload).encode("utf-8") if payload is not None else b""
    resp.url = url
    return resp


class FakeGraph:
    """假的 Threads Graph API：依路徑回應並記錄 (method, path, params)。

    routes：{(method, path): 回應或回應清單}。清單依序取用、用完停在最後一個；
    回應可以是 (status, payload)、requests.Response，或要丟出的例外。"""

    def __init__(self, routes):
        self.routes = {key: (list(value) if isinstance(value, list) else [value]) for key, value in routes.items()}
        self.calls = []

    def _handle(self, method, url, params):
        assert url.startswith(BASE_URL + "/"), url
        path = url[len(BASE_URL) + 1:]
        self.calls.append((method, path, dict(params or {})))
        queue = self.routes.get((method, path))
        assert queue, f"unexpected Threads API call: {method} {path}"
        item = queue.pop(0) if len(queue) > 1 else queue[0]
        if isinstance(item, BaseException):
            raise item
        if isinstance(item, requests.Response):
            return item
        status, payload = item
        # 真的 requests 會把 token 帶在 GET 的 URL 上：讓回應的 url 也含 token，驗證遮蔽
        return _response(status, payload, url=f"{url}?access_token={(params or {}).get('access_token')}")

    def get(self, url, params=None, timeout=None):
        assert timeout, "every Threads API call must have a timeout"
        return self._handle("GET", url, params)

    def post(self, url, data=None, timeout=None, **kwargs):
        assert timeout, "every Threads API call must have a timeout"
        assert not kwargs, f"token must go in the form body, not in {sorted(kwargs)}"
        return self._handle("POST", url, data)

    def paths(self):
        return [f"{method} {path}" for method, path, _ in self.calls]

    def count(self, method, path):
        return self.paths().count(f"{method} {path}")


@pytest.fixture
def live(monkeypatch, tmp_path):
    for key, value in {
        "THREADS_MODE": "live", "ENABLE_THREADS_BOT": False, "THREADS_ACCESS_TOKEN": TOKEN,
        "THREADS_USER_ID": USER_ID, "THREADS_BASE_URL": BASE_URL, "BOT_HANDLE": "factcheck_tw_bot",
        "PUBLIC_BASE_URL": PUBLIC, "THREADS_POLL_MINUTES": 5,
        "THREADS_MAX_REPLIES_PER_POLL": 5, "THREADS_MAX_REPLIES_PER_DAY": 50,
    }.items():
        monkeypatch.setattr(settings, key, value)
    monkeypatch.setattr(ts, "TOKEN_PATH", tmp_path / "no_token_file.json")

    def install(routes):
        graph = FakeGraph(routes)
        monkeypatch.setattr(ts.requests, "get", graph.get)
        monkeypatch.setattr(ts.requests, "post", graph.post)
        return graph

    return install


@pytest.fixture
def sleeps(monkeypatch):
    """T-12 第 5 點：patch time.sleep（wait_container 預設的等待）——只記錄秒數，不真的睡。"""
    recorded = []
    monkeypatch.setattr(ts.time, "sleep", recorded.append)
    return recorded


def _status(value, **extra):
    return (200, {"status": value, "id": "c-1", **extra})


# ══════════════════════════════════════════════════════════════════
# 兩段式發佈（spec §7.6）
# ══════════════════════════════════════════════════════════════════
def test_live_service_implements_protocol_with_container_steps(live):
    live({})
    svc = ThreadsService()
    assert svc.available is True and isinstance(svc, ThreadsClient)
    assert (svc.container_poll_interval, svc.container_poll_timeout) == (5.0, 60.0)   # spec §7.6：每 5 秒、最多 60 秒


def test_reply_to_publishes_only_after_container_is_finished(live, sleeps):
    graph = live({
        ("POST", f"{USER_ID}/threads"): (200, {"id": "c-1"}),
        ("GET", "c-1"): [_status("IN_PROGRESS"), _status("IN_PROGRESS"), _status("FINISHED")],
        ("POST", f"{USER_ID}/threads_publish"): (200, {"id": "media-9"}),
    })
    assert ThreadsService().reply_to("mention-1", "這是回覆") == "media-9"
    assert graph.paths() == [
        f"POST {USER_ID}/threads", "GET c-1", "GET c-1", "GET c-1", f"POST {USER_ID}/threads_publish",
    ]
    assert sleeps == [5.0, 5.0]                                  # FINISHED 之前每 5 秒查一次

    create, status, publish = graph.calls[0][2], graph.calls[1][2], graph.calls[-1][2]
    assert create == {"media_type": "TEXT", "text": "這是回覆", "reply_to_id": "mention-1", "access_token": TOKEN}
    assert status == {"fields": "status,error_message", "access_token": TOKEN}
    assert publish == {"creation_id": "c-1", "access_token": TOKEN}


def test_reply_to_finished_on_first_check_does_not_wait(live, sleeps):
    graph = live({
        ("POST", f"{USER_ID}/threads"): (200, {"id": "c-1"}),
        ("GET", "c-1"): _status("FINISHED"),
        ("POST", f"{USER_ID}/threads_publish"): (200, {"id": "media-9"}),
    })
    assert ThreadsService().reply_to("mention-1", "x") == "media-9"
    assert graph.count("GET", "c-1") == 1 and sleeps == []


@pytest.mark.parametrize("status", ["ERROR", "EXPIRED"])
def test_reply_to_never_publishes_an_error_or_expired_container(live, sleeps, caplog, status):
    graph = live({
        ("POST", f"{USER_ID}/threads"): (200, {"id": "c-1"}),
        ("GET", "c-1"): _status(status, error_message="FAILED_PROCESSING"),
    })
    with caplog.at_level(logging.WARNING, logger="threads_service"):
        assert ThreadsService().reply_to("mention-1", "x") is None
    assert graph.count("POST", f"{USER_ID}/threads_publish") == 0
    assert any(status in r.getMessage() and "FAILED_PROCESSING" in r.getMessage() for r in caplog.records)
    assert sleeps == []


def test_wait_container_is_bounded_to_60_seconds_of_in_progress(live, sleeps):
    graph = live({("GET", "c-1"): _status("IN_PROGRESS")})
    assert ThreadsService().wait_container("c-1") == "TIMEOUT"
    assert graph.count("GET", "c-1") == 13                        # 60 // 5 + 1
    assert sleeps == [5.0] * 12 and sum(sleeps) == 60.0


def test_wait_container_timeout_means_reply_to_does_not_publish(live, sleeps):
    graph = live({
        ("POST", f"{USER_ID}/threads"): (200, {"id": "c-1"}),
        ("GET", "c-1"): _status("IN_PROGRESS"),
    })
    assert ThreadsService().reply_to("mention-1", "x") is None
    assert graph.count("POST", f"{USER_ID}/threads_publish") == 0


def test_wait_container_published_is_terminal_and_is_not_published_again(live, sleeps):
    graph = live({
        ("POST", f"{USER_ID}/threads"): (200, {"id": "c-1"}),
        ("GET", "c-1"): _status("PUBLISHED"),
    })
    svc = ThreadsService()
    assert svc.wait_container("c-1") == "PUBLISHED"
    assert svc.reply_to("mention-1", "x") is None and graph.count("POST", f"{USER_ID}/threads_publish") == 0


def test_wait_container_accepts_injected_sleep_interval_and_timeout(live):
    graph = live({("GET", "c-1"): [_status("IN_PROGRESS"), (200, {"id": "c-1"}), _status("finished")]})
    waited = []
    assert ThreadsService().wait_container("c-1", interval=2, timeout=10, sleep=waited.append) == "FINISHED"
    assert waited == [2.0, 2.0] and graph.count("GET", "c-1") == 3    # 缺 status 視為尚未完成；大小寫容忍

    graph = live({("GET", "c-2"): _status("IN_PROGRESS")})
    svc = ThreadsService()
    svc.container_sleep = waited.append                               # 實例層級注入
    svc.container_poll_interval, svc.container_poll_timeout = 1, 3
    assert svc.wait_container("c-2") == "TIMEOUT" and graph.count("GET", "c-2") == 4


def test_reply_to_without_container_id_returns_none(live, sleeps):
    graph = live({("POST", f"{USER_ID}/threads"): (200, {})})
    assert ThreadsService().reply_to("mention-1", "x") is None
    assert graph.paths() == [f"POST {USER_ID}/threads"]


def test_publish_text_uses_the_same_three_steps(live, sleeps):
    graph = live({
        ("POST", f"{USER_ID}/threads"): (200, {"id": "c-7"}),
        ("GET", "c-7"): [_status("IN_PROGRESS"), _status("FINISHED")],
        ("POST", f"{USER_ID}/threads_publish"): (200, {"id": "media-10"}),
    })
    assert ThreadsService().publish_text("每日查核摘要") == "media-10"
    assert graph.paths() == [f"POST {USER_ID}/threads", "GET c-7", "GET c-7", f"POST {USER_ID}/threads_publish"]
    assert "reply_to_id" not in graph.calls[0][2] and graph.calls[0][2]["text"] == "每日查核摘要"
    assert sleeps == [5.0]


# ══════════════════════════════════════════════════════════════════
# HTTP 錯誤 → ThreadsApiError(status, body)／ThreadsTransientError（spec §7.10）
# ══════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("status, transient", [
    (400, False), (401, False), (403, False), (404, False), (429, False), (500, True), (502, True), (503, True),
])
def test_non_2xx_raises_with_status_and_parsed_body(live, caplog, status, transient):
    body = {"error": {"message": "boom", "code": 4, "type": "OAuthException"}}
    live({("GET", "me"): (status, body)})
    with caplog.at_level(logging.WARNING, logger="threads_service"):
        with pytest.raises(ThreadsApiError) as ei:
            ThreadsService().get_profile()
    err = ei.value
    assert err.status == status and err.status_code == status and err.body == body
    assert isinstance(err, ThreadsAPIError)                       # 舊名相容
    assert isinstance(err, ThreadsTransientError) is transient
    assert err.__cause__ is None and err.__context__ is None
    # 非 2xx 一律把 body 寫進 log；token 不出現在例外訊息、body 或 log
    [record] = [r for r in caplog.records if r.name == "threads_service"]
    assert f"status={status}" in record.getMessage() and "OAuthException" in record.getMessage()
    assert "access_token=***" in str(err)
    for text in (str(err), json.dumps(err.body), record.getMessage()):
        assert TOKEN not in text


def test_timeout_and_connection_errors_are_transient_without_status(live):
    secret_url = f"{BASE_URL}/me?access_token={TOKEN}"
    for exc in (requests.Timeout(f"read timed out: {secret_url}"), requests.ConnectionError(f"refused: {secret_url}")):
        live({("GET", "me"): exc})
        with pytest.raises(ThreadsTransientError) as ei:
            ThreadsService().get_profile()
        assert ei.value.status is None and ei.value.body is None
        assert TOKEN not in str(ei.value) and ei.value.__context__ is None


def test_2xx_with_non_json_body_is_transient(live):
    live({("GET", "me"): _response(200, text="<html>gateway</html>")})
    with pytest.raises(ThreadsTransientError) as ei:
        ThreadsService().get_profile()
    assert ei.value.status == 200 and threads_bot.classify_api_error(ei.value) == "transient"


def test_link_limit_error_is_detected_from_the_body(live, sleeps):
    body = {"error": {"message": "Param text has too many links", "error_user_title": "THREADS_API__LINK_LIMIT_EXCEEDED"}}
    live({("POST", f"{USER_ID}/threads"): (400, body)})
    with pytest.raises(ThreadsApiError) as ei:
        ThreadsService().create_reply_container("mention-1", "x")
    assert ei.value.status == 400 and is_link_limit_error(ei.value)
    assert is_link_limit_error(ThreadsApiError(400, "... THREADS_API__LINK_LIMIT_EXCEEDED ..."))
    assert not is_link_limit_error(ThreadsApiError(400, {"error": {"message": "other"}}))
    assert not is_link_limit_error(ThreadsApiError(400, None))
    assert not is_link_limit_error(RuntimeError("no body"))


# ══════════════════════════════════════════════════════════════════
# 機器人 × live 客戶端（requests 全 mock）：HTTP 層的「重複回覆率 0」與 backoff
# ══════════════════════════════════════════════════════════════════
class FakeAI:
    def __init__(self, store):
        self.store, self.calls = store, []

    async def __call__(self, task_id, input_data, input_type):
        self.calls.append(task_id)
        result = proc._build_result(dict(AI_MISINFO), cached=True, cache_layer="hash", result_id=task_id)
        proc._complete(self.store, task_id, result)
        return result


@pytest.fixture
def livebot(live, tmp_path, monkeypatch):
    data = tmp_path / "data"
    ai = FakeAI(TaskStore(data_dir=str(data)))
    monkeypatch.setattr(proc, "process_analysis_task_async", ai)

    def poll():
        return asyncio.run(threads_bot.run_threads_poll(client=ThreadsService(), data_dir=data))

    return data, ai, poll


def _mentions_page(*ids):
    return (200, {"data": [
        {"id": mid, "username": "tester_b", "text": f"@factcheck_tw_bot {RUMOR}", "media_type": "TEXT_POST",
         "permalink": f"https://www.threads.com/@tester_b/post/{mid}", "timestamp": "2026-09-14T08:00:00+0000"}
        for mid in ids
    ]})


def test_bot_live_publish_failure_is_republished_with_the_same_container(live, livebot, sleeps, caplog):
    """T-12 驗收：「publish 失敗 → 下輪補發」整個情境 POST …/threads 只出現 1 次。"""
    data, ai, poll = livebot
    graph = live({
        ("GET", f"{USER_ID}/mentions"): _mentions_page("17900000000000001"),
        ("POST", f"{USER_ID}/threads"): (200, {"id": "c-1"}),
        ("GET", "c-1"): _status("FINISHED"),
        ("POST", f"{USER_ID}/threads_publish"): [(500, {"error": {"message": "temporarily unavailable"}}),
                                                 (200, {"id": "17900000000000777"})],
    })
    with caplog.at_level(logging.DEBUG):
        first = poll()
        assert (first["replied"], first["errors"]) == (0, 1)
        st = threads_state.load_state(data)
        assert st["pending_publish"]["17900000000000001"]["container_id"] == "c-1" and st["replied_ids"] == []
        assert st["pending_publish"]["17900000000000001"]["mode"] == "live"

        second = poll()
    assert (second["checked"], second["replied"], second["errors"]) == (1, 1, 0)
    assert graph.count("POST", f"{USER_ID}/threads") == 1                  # container 只建 1 次
    assert graph.count("POST", f"{USER_ID}/threads_publish") == 2          # 同一個 creation_id 補發
    assert [c[2]["creation_id"] for c in graph.calls if c[1].endswith("threads_publish")] == ["c-1", "c-1"]
    assert len(ai.calls) == 1                                               # 不重跑 AI
    st = threads_state.load_state(data)
    assert st["replied_ids"] == ["17900000000000001"] and st["pending_publish"] == {}
    [rec] = threads_state.read_reply_records(None, data)
    assert rec["reply_id"] == "17900000000000777" and rec["mode"] == "live" and rec["result_id"] == ai.calls[0]
    assert f"{PUBLIC}/r/{ai.calls[0]}" in rec["reply_text"] and f"查核來源：{TIER1_URL}" in rec["reply_text"]
    assert poll()["replied"] == 0 and graph.count("POST", f"{USER_ID}/threads") == 1
    assert all(TOKEN not in r.getMessage() for r in caplog.records)         # log 不含 token


def test_bot_live_container_error_is_not_published_and_retried_once(live, livebot, sleeps):
    data, ai, poll = livebot
    graph = live({
        ("GET", f"{USER_ID}/mentions"): _mentions_page("17900000000000002"),
        ("POST", f"{USER_ID}/threads"): [(200, {"id": "c-1"}), (200, {"id": "c-2"})],
        ("GET", "c-1"): _status("ERROR", error_message="FAILED_PROCESSING"),
        ("GET", "c-2"): _status("ERROR", error_message="FAILED_PROCESSING"),
    })
    assert poll()["errors"] == 1 and poll()["errors"] == 1 and poll()["checked"] == 0
    assert graph.count("POST", f"{USER_ID}/threads") == 2                  # 第一次＋重試一次，之後放棄
    assert graph.count("POST", f"{USER_ID}/threads_publish") == 0
    st = threads_state.load_state(data)
    assert st["failed"]["17900000000000002"]["final"] is True and st["replied_ids"] == []
    assert threads_state.read_reply_records(None, data) == [] and len(ai.calls) == 2


def test_bot_live_http_429_sets_backoff_and_next_poll_makes_no_request(live, livebot, sleeps):
    data, ai, poll = livebot
    graph = live({("GET", f"{USER_ID}/mentions"): (429, {"error": {"message": "rate limit", "code": 4}})})
    out = poll()
    assert (out["started"], out["errors"], out["stopped"]) == (True, 1, "rate_limited")
    st = threads_state.load_state(data)
    until = threads_state.parse_until(st["backoff_until"])
    left = (until - datetime.now(timezone.utc)).total_seconds() / 60
    assert 4.5 <= left <= 5 and st["backoff_n"] == 1 and st["last_error"] == "rate_limited"

    assert poll()["skipped"] == "backoff"
    assert graph.count("GET", f"{USER_ID}/mentions") == 1 and ai.calls == []


def test_bot_live_unknown_4xx_on_container_creation_marks_failed_without_reply(live, livebot, sleeps):
    data, ai, poll = livebot
    graph = live({
        ("GET", f"{USER_ID}/mentions"): _mentions_page("17900000000000003"),
        ("POST", f"{USER_ID}/threads"): (400, {"error": {"message": "Invalid parameter", "code": 100}}),
    })
    out = poll()
    assert (out["replied"], out["errors"], out["stopped"]) == (0, 1, None)
    st = threads_state.load_state(data)
    assert st["failed"]["17900000000000003"]["final"] is True and st["failed"]["17900000000000003"]["status"] == 400
    assert st["replied_ids"] == [] and st["backoff_until"] is None
    assert poll()["checked"] == 0 and graph.count("POST", f"{USER_ID}/threads") == 1 and len(ai.calls) == 1
