"""B-20：管理端點 X-Admin-Token（spec §5.6、§5.7；測試 FN-9）與覆寫寫入 label_source=admin（spec §6.2、FR-17 (b)）。

全部離線、零 AI：run_trending_fetch／run_threads_poll 與 BackgroundTasks.add_task 換成 no-op，
requests 與非 loopback socket 一律擋下並記錄，最後斷言對外呼叫 0 次；資料一律寫 tmp_path。
"""
import json
import socket

import numpy as np
import pytest
import requests
from fastapi import BackgroundTasks
from fastapi.testclient import TestClient

import app.api.admin as admin_api
import app.api.result as result_api
import app.api.threads as threads_api
import app.services.news_fetcher as news_fetcher
import app.utils.admin_auth as admin_auth
import app.workers.pandas_task_processor as proc
from app.config import settings
from app.main import app
from app.services.audit_store import AuditStore
from app.services.cache_service import CacheService
from app.services.pandas_store import PandasStore
from app.services.task_store import TaskStore
from app.utils.admin_auth import MSG_ADMIN_DISABLED, MSG_UNAUTHORIZED

TOKEN = "0123456789abcdef0123456789abcdef"
OVERRIDE_BODY = {"risk_type": "SCAM", "reason": "人工確認為詐騙", "admin_id": "admin-1"}
_LOOPBACK = ("127.0.0.1", "::1", "localhost")
UNAUTHORIZED = {"detail": MSG_UNAUTHORIZED, "code": "unauthorized"}
ADMIN_DISABLED = {"detail": MSG_ADMIN_DISABLED, "code": "admin_disabled"}


@pytest.fixture
def network_calls(monkeypatch):
    calls = []

    def fake_request(self, method, url, *args, **kwargs):
        calls.append((method, url))
        raise AssertionError(f"unexpected HTTP call: {method} {url}")

    real_connect = socket.socket.connect

    def guarded_connect(self, address):
        host = address[0] if isinstance(address, tuple) else address
        if host not in _LOOPBACK:
            calls.append(("socket", address))
            raise AssertionError(f"unexpected socket connect: {address}")
        return real_connect(self, address)

    monkeypatch.setattr(requests.Session, "request", fake_request)
    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    yield calls
    assert calls == []


@pytest.fixture
def scheduled(monkeypatch):
    """add_task 只記錄、不執行；真正的 fetch／poll 被呼叫就失敗。"""
    added = []

    def fake_add_task(self, func, *args, **kwargs):
        added.append(func)

    async def fake_trending_fetch(*args, **kwargs):
        raise AssertionError("run_trending_fetch must not run in tests")

    async def fake_threads_poll(*args, **kwargs):
        raise AssertionError("run_threads_poll must not run in tests")

    class FakeThreadsService:
        available = True

    monkeypatch.setattr(BackgroundTasks, "add_task", fake_add_task)
    monkeypatch.setattr(news_fetcher, "run_trending_fetch", fake_trending_fetch)
    monkeypatch.setattr(threads_api, "run_threads_poll", fake_threads_poll, raising=False)
    monkeypatch.setattr(threads_api, "ThreadsService", FakeThreadsService, raising=False)
    return added


@pytest.fixture
def stores(tmp_path, monkeypatch):
    ts = TaskStore(data_dir=str(tmp_path))
    kb = PandasStore(data_dir=str(tmp_path))
    audit = AuditStore(data_dir=str(tmp_path))
    monkeypatch.setattr(admin_api, "task_store", ts)
    monkeypatch.setattr(admin_api, "kb_store", kb)
    monkeypatch.setattr(admin_api, "audit_store", audit)
    monkeypatch.setattr(result_api, "task_store", ts)
    return ts, kb, audit


@pytest.fixture
def admin_env(monkeypatch, network_calls, scheduled, stores):
    monkeypatch.setattr(settings, "ADMIN_TOKEN", TOKEN)
    monkeypatch.setattr(settings, "THREADS_MODE", "sim")
    monkeypatch.setattr(settings, "ENABLE_THREADS_BOT", False)
    return scheduled


@pytest.fixture
def client():
    return TestClient(app)  # 不進 lifespan：不動真實 SQLite、不啟排程


def _auth(token=TOKEN):
    return {"X-Admin-Token": token}


def _admin_calls(client, headers=None):
    """三類管理端點各打一次，回傳 (refresh, override, poll) 回應。"""
    return (
        client.post("/api/trending/refresh", headers=headers),
        client.post("/api/admin/tasks/no-such-task/override", json=OVERRIDE_BODY, headers=headers),
        client.post("/api/threads/poll", headers=headers),
    )


def test_no_token_401(client, admin_env):
    wrong = ["", "wrong", TOKEN[:-1], TOKEN + "x", TOKEN.upper(), "x" * len(TOKEN)]
    for headers in [None] + [_auth(w) for w in wrong]:
        for resp in _admin_calls(client, headers):
            assert resp.status_code == 401, (headers, resp.request.url, resp.text)
            assert resp.json() == UNAUTHORIZED
            assert TOKEN not in resp.text
    # 驗證在 body 驗證之前：未授權者探不到 422 細節
    resp = client.post("/api/admin/tasks/x/override", json={"risk_type": "SCAM"})
    assert resp.status_code == 401 and resp.json()["code"] == "unauthorized"
    assert admin_env == []  # 沒有排任何背景工作


@pytest.mark.parametrize("configured", ["", "   "])
def test_empty_admin_token_403(client, admin_env, monkeypatch, configured):
    monkeypatch.setattr(settings, "ADMIN_TOKEN", configured)
    for headers in (None, _auth(), _auth("")):
        for resp in _admin_calls(client, headers):
            assert resp.status_code == 403, (headers, resp.request.url, resp.text)
            assert resp.json() == ADMIN_DISABLED
    assert admin_env == []


def test_correct_token_passes(client, admin_env, monkeypatch):
    compared = []
    real_compare = admin_auth.hmac.compare_digest

    def spy_compare(a, b):
        compared.append(True)
        return real_compare(a, b)

    monkeypatch.setattr(admin_auth.hmac, "compare_digest", spy_compare)
    resp = client.post("/api/trending/refresh", headers=_auth())
    assert resp.status_code == 200
    assert admin_env == [news_fetcher.run_trending_fetch]  # 路由真的走到排背景工作（no-op）
    assert compared  # 固定時間比對（hmac.compare_digest），不是 ==

    # 通過授權後才輪到業務邏輯：不存在的任務 404
    resp = client.post("/api/admin/tasks/no-such-task/override", json=OVERRIDE_BODY, headers=_auth())
    assert resp.status_code == 404

    for mode in ("sim", "live"):
        monkeypatch.setattr(settings, "THREADS_MODE", mode)
        assert client.post("/api/threads/poll").status_code == 401
        resp = client.post("/api/threads/poll", headers=_auth())
        assert resp.status_code in (200, 202, 409), resp.text
        assert resp.json().get("code") not in ("unauthorized", "admin_disabled", "threads_disabled")


@pytest.mark.parametrize("mode,legacy", [("off", False), (None, False)])
@pytest.mark.parametrize("admin_token", [TOKEN, ""])
def test_poll_off_mode_returns_threads_disabled_without_token(
    client, admin_env, monkeypatch, mode, legacy, admin_token,
):
    monkeypatch.setattr(settings, "THREADS_MODE", mode)
    monkeypatch.setattr(settings, "ENABLE_THREADS_BOT", legacy)
    monkeypatch.setattr(settings, "ADMIN_TOKEN", admin_token)
    for headers in (None, _auth("wrong"), _auth()):
        resp = client.post("/api/threads/poll", headers=headers)
        assert resp.status_code == 200
        assert resp.json() == {"started": False, "code": "threads_disabled"}
    assert admin_env == []


def _vec(seed):
    return list(np.random.default_rng(seed).normal(size=1536).astype(float))


def test_override_sets_label_source_admin(client, admin_env, stores):
    ts, kb, audit = stores
    text = "網傳領取振興券要先輸入信用卡號"
    vec = _vec(5)
    ai = {
        "is_risk": False, "risk_type": "SAFE", "category": "Safe", "confidence_score": 0.9,
        "summary": "看起來是官方公告", "explanation": "e",
        "sources": [{"title": "部落格", "url": "https://blog.example.com/p"}],
    }
    row = kb.save_record(
        data_type="TEXT", raw_content=text, content_hash=CacheService.generate_hash(text),
        content_vector=vec, ai_result=ai, label_source="ai",
    )
    assert row["verified"] is False
    assert kb.find_similar_by_vector(vec, threshold=0.5) is None  # 未證實列不參與向量命中

    tid = ts.create_task("analyze_text", text, input_type="text")
    built = proc._build_result(ai, result_id=tid, label_source="ai", kb_id=row["id"])
    proc._complete(ts, tid, built)
    assert built["frame_type"] == "yellow" and built["verification_status"] == "unverified"

    resp = client.post(f"/api/admin/tasks/{tid}/override", json=OVERRIDE_BODY, headers=_auth())
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["label_source"] == "admin" and body["risk_type"] == "SCAM" and body["is_risk"] is True
    assert body["verification_status"] == "rule" and body["verified"] is True
    assert (body["frame_type"], body["frame_label"]) == ("red", "詐騙警告")

    # tasks 列
    task = ts.get_task(tid)
    assert task["label_source"] == "admin"
    assert task["verified"] is True
    stored = json.loads(task["result_data"])
    assert stored["label_source"] == "admin" and stored["verification_status"] == "rule"
    assert stored["frame_type"] == "red" and stored["risk_type"] == "SCAM"
    assert stored["kb_id"] == row["id"]

    # 知識庫列：確定性標記 → verified，且判定換成覆寫後的值（快取命中讀 ai_analysis）
    df = kb.get_all_records()
    assert len(df) == 1
    kb_row = df.iloc[0]
    assert kb_row["label_source"] == "admin"
    assert isinstance(kb_row["verified"], (bool, np.bool_)) and bool(kb_row["verified"]) is True
    assert kb_row["risk_type"] == "SCAM" and bool(kb_row["is_risk"]) is True
    assert kb_row["ai_analysis"]["risk_type"] == "SCAM" and kb_row["ai_analysis"]["is_risk"] is True
    assert kb_row["ai_analysis"]["summary"] == "看起來是官方公告"   # 其他欄位保留
    hit = kb.find_similar_by_vector(vec, threshold=0.5)
    assert hit is not None and hit["id"] == row["id"]

    # 結果頁讀到的是覆寫後的一致狀態
    result = client.get(f"/api/result/{tid}").json()["result"]
    assert result["label_source"] == "admin" and result["frame_type"] == "red"
    assert result["verification_status"] == "rule"

    # 稽核紀錄寫在 tmp_path
    overrides = audit._load_overrides()
    assert len(overrides) == 1 and overrides.iloc[0]["task_id"] == tid


def test_override_without_kb_id_leaves_kb_untouched(client, admin_env, stores):
    ts, kb, _audit = stores
    other = kb.save_record(
        data_type="TEXT", raw_content="別的列", content_hash=CacheService.generate_hash("別的列"),
        ai_result={"is_risk": True, "risk_type": "SCAM", "confidence_score": 0.9, "summary": "s",
                   "explanation": "e", "sources": []},
    )
    tid = ts.create_task("analyze_text", "沒有知識庫列的任務", input_type="text")
    proc._complete(ts, tid, proc._build_result(
        {"is_risk": True, "risk_type": "MISINFO", "confidence_score": 0.8, "summary": "s",
         "explanation": "e", "sources": []}, result_id=tid))
    resp = client.post(f"/api/admin/tasks/{tid}/override",
                       json={"risk_type": "SAFE", "confidence_score": 0.95, "reason": "r", "admin_id": "a"},
                       headers=_auth())
    assert resp.status_code == 200
    body = resp.json()
    assert body["label_source"] == "admin" and body["frame_type"] == "green"
    assert ts.get_task(tid)["label_source"] == "admin"
    row = kb.get_all_records().iloc[0]
    assert row["id"] == other["id"] and row["label_source"] == "ai" and row["risk_type"] == "SCAM"
