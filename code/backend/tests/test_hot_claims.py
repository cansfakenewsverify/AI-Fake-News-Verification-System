"""熱門查證：hot_claims.rank 的時間衰減排序、TaskStore.recent_kb_refs、GET /api/knowledge/hot。

全部離線、零 AI：知識庫與查證紀錄都在 tmp_path（monkeypatch knowledge._store／_task_store），
並擋下所有對外連線（來源分級走離線模式）。
"""
import socket
from datetime import datetime, timedelta

import pytest
import requests
from fastapi.testclient import TestClient

import app.api.knowledge as knowledge_api
from app.main import app
from app.services import hot_claims
from app.services.cache_service import CacheService
from app.services.pandas_store import PandasStore
from app.services.task_store import TaskStore

NOW = datetime(2026, 9, 22, 12, 0, 0)
MYGOPEN = {"title": "【錯誤】網傳某說法？", "url": "https://www.mygopen.com/2026/09/a.html"}
_LOOPBACK = ("127.0.0.1", "::1", "localhost")


def _ref(kb_id, hours_ago):
    return {"kb_id": kb_id, "created_at": NOW - timedelta(hours=hours_ago)}


# ── 排序 ────────────────────────────────────────────────────────
def test_recent_requests_outrank_an_older_burst():
    refs = [_ref("old", 30)] * 4 + [_ref("new", 0.5)] * 2
    ranked = hot_claims.rank(refs, NOW)
    assert [r["kb_id"] for r in ranked] == ["new", "old"]
    old = ranked[1]
    assert old["count_window"] == 4 and old["count_24h"] == 0


def test_score_halves_every_half_life_and_counts_are_exact():
    ranked = hot_claims.rank([_ref("a", 0), _ref("a", 3), _ref("a", 23.5), _ref("a", 25)], NOW)
    (item,) = ranked
    expected = 1 + 0.5 + 0.5 ** (23.5 / 3) + 0.5 ** (25 / 3)
    assert item["score"] == pytest.approx(expected, abs=1e-6)
    assert item["count_24h"] == 3 and item["count_window"] == 4
    assert item["last_seen"] == NOW


def test_requests_outside_the_window_are_ignored():
    ranked = hot_claims.rank([_ref("gone", 7 * 24 + 1), _ref("kept", 6 * 24)], NOW)
    assert [r["kb_id"] for r in ranked] == ["kept"]


def test_equal_scores_put_the_most_recent_first_then_kb_id():
    # b：兩次、各 3 小時前 → 0.5 + 0.5 = 1.0；a：一次、剛剛 → 1.0；同分時較近者在前
    ranked = hot_claims.rank([_ref("b", 3), _ref("b", 3), _ref("a", 0)], NOW)
    assert [r["kb_id"] for r in ranked] == ["a", "b"]
    ranked = hot_claims.rank([_ref("z", 1), _ref("y", 1)], NOW)
    assert [r["kb_id"] for r in ranked] == ["y", "z"]


def test_malformed_refs_are_skipped_and_future_times_count_as_now():
    refs = [
        {"kb_id": "", "created_at": NOW},
        {"kb_id": None, "created_at": NOW},
        {"kb_id": "x", "created_at": "2026-09-22T12:00:00"},
        {"kb_id": "x", "created_at": None},
        {"kb_id": "future", "created_at": NOW + timedelta(hours=2)},
    ]
    (item,) = hot_claims.rank(refs, NOW)
    assert item["kb_id"] == "future" and item["score"] == pytest.approx(1.0)


# ── 查證紀錄 ────────────────────────────────────────────────────
def test_task_store_returns_completed_tasks_with_a_kb_row_since_the_cutoff(tmp_path):
    tasks = TaskStore(data_dir=str(tmp_path))
    done = tasks.create_task("analyze_text", "a")
    tasks.update_task(done, status="completed", kb_id="kb-1")
    threads = tasks.create_task("threads_mention", "b", origin="threads")
    tasks.update_task(threads, status="completed", kb_id="kb-2")
    no_row = tasks.create_task("analyze_text", "c")
    tasks.update_task(no_row, status="completed")                 # 無法查證等：沒有對應的知識庫列
    failed = tasks.create_task("analyze_text", "d")
    tasks.update_task(failed, status="failed", kb_id="kb-3")
    tasks.create_task("analyze_text", "e")                        # pending
    old = tasks.create_task("analyze_text", "f")
    tasks.update_task(old, status="completed", kb_id="kb-4",
                      created_at=datetime.utcnow() - timedelta(days=10))

    refs = tasks.recent_kb_refs(datetime.utcnow() - timedelta(days=7))
    assert [(r["kb_id"], r["origin"]) for r in refs] == [("kb-1", "web"), ("kb-2", "threads")]
    assert all(isinstance(r["created_at"], datetime) for r in refs)
    assert "input_data" not in refs[0]                             # 不帶使用者輸入
    assert tasks.recent_kb_refs(datetime.utcnow() + timedelta(minutes=1)) == []
    assert TaskStore(data_dir=str(tmp_path / "empty")).recent_kb_refs(NOW) == []


# ── 端點 ────────────────────────────────────────────────────────
@pytest.fixture
def network_calls(monkeypatch):
    calls = []

    def fake_request(self, method, url, *args, **kwargs):
        calls.append((method, url))
        raise AssertionError(f"hot API must not make HTTP calls: {method} {url}")

    real_connect = socket.socket.connect

    def guarded_connect(self, address):
        host = address[0] if isinstance(address, tuple) else address
        if host not in _LOOPBACK:
            calls.append(("socket", address))
            raise AssertionError(f"hot API must not open sockets: {address}")
        return real_connect(self, address)

    monkeypatch.setattr(requests.Session, "request", fake_request)
    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    return calls


@pytest.fixture
def stores(tmp_path, monkeypatch, network_calls):
    kb = PandasStore(data_dir=str(tmp_path))
    tasks = TaskStore(data_dir=str(tmp_path))
    monkeypatch.setattr(knowledge_api, "_store", kb)
    monkeypatch.setattr(knowledge_api, "_task_store", tasks)
    yield kb, tasks
    assert network_calls == []


def _row(kb, text, *, verified=True):
    ai = {
        "is_risk": True, "risk_type": "MISINFO", "category": "Test", "confidence_score": 0.9,
        "summary": f"{text}的摘要", "explanation": "說明", "sources": [MYGOPEN] if verified else [],
    }
    return kb.save_record(
        data_type="TEXT", raw_content=text, content_hash=CacheService.generate_hash(text), ai_result=ai,
    )


def _asked(tasks, kb_id, times, status="completed"):
    for _ in range(times):
        tid = tasks.create_task("analyze_text", "使用者輸入")
        tasks.update_task(tid, status=status, kb_id=kb_id)


def test_hot_lists_verified_rows_by_recent_demand(stores):
    kb, tasks = stores
    busy = _row(kb, "很多人問的謠言")
    quiet = _row(kb, "只有一個人問的謠言")
    hidden = _row(kb, "還沒有查核來源的說法", verified=False)
    assert hidden["verified"] is False
    _asked(tasks, busy["id"], 3)
    _asked(tasks, quiet["id"], 1)
    _asked(tasks, hidden["id"], 5)                                 # 最多人問，但未證實 → 不公開
    _asked(tasks, quiet["id"], 4, status="pending")                # 未完成的不算

    body = TestClient(app).get("/api/knowledge/hot").json()

    assert body["window_days"] == 7 and body["half_life_hours"] == 3.0
    assert body["total"] == 2
    assert [r["id"] for r in body["records"]] == [busy["id"], quiet["id"]]
    top = body["records"][0]
    assert top["recent_24h"] == 3 and top["recent_7d"] == 3 and top["last_seen_at"]
    assert top["raw_content"] == "很多人問的謠言" and top["risk_type"] == "MISINFO"
    assert [s["tier"] for s in top["sources"]] == [1]
    listed = TestClient(app).get("/api/knowledge").json()["records"]
    same = next(r for r in listed if r["id"] == busy["id"])
    assert {k: top[k] for k in same} == same                       # 與 /api/knowledge 同一份欄位


def test_hot_limit_and_empty_state(stores):
    kb, tasks = stores
    client = TestClient(app)
    assert client.get("/api/knowledge/hot").json() == {
        "window_days": 7, "half_life_hours": 3.0, "total": 0, "records": [],
    }
    first = _row(kb, "第一名")
    second = _row(kb, "第二名")
    _asked(tasks, first["id"], 2)
    _asked(tasks, second["id"], 1)
    body = client.get("/api/knowledge/hot", params={"limit": 1}).json()
    assert body["total"] == 1 and body["records"][0]["id"] == first["id"]
    assert client.get("/api/knowledge/hot", params={"limit": 0}).status_code == 422
    assert client.get("/api/knowledge/hot", params={"limit": 51}).status_code == 422


def test_hot_skips_task_references_to_rows_that_no_longer_exist(stores):
    kb, tasks = stores
    row = _row(kb, "還在的列")
    _asked(tasks, "deleted-row", 3)
    _asked(tasks, row["id"], 1)
    body = TestClient(app).get("/api/knowledge/hot").json()
    assert [r["id"] for r in body["records"]] == [row["id"]]
