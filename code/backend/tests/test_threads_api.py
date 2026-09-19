"""Threads API（T-10）與 sim 重播腳本（T-11）測試。

T-10：GET /api/threads/status、GET /api/threads/replies、POST /api/threads/poll
      （spec §5.2、§5.3、§5.6、§5.7；測試 FN-9、OP-3），以及排程工作對 PollInProgress 的容忍。
T-11：scripts/test_threads_bot.py 的 --reset-sim（清模擬紀錄、離線預熱 gold 種子）與 --poll
      （經 API 或後端未啟動時在本程序內跑），含「真管線、AI 與網路全擋」的離線閉環（FR-10 驗收 1）。

全部離線、零 AI 點數：
- monkeypatch.chdir(tmp_path)：後端的 data/ 相對路徑（threads_state.json、threads_replies.jsonl、
  tasks.parquet、knowledge_base.parquet、threads_sim/*、threads_token.json、threads_poll.lock）
  全部落在 tmp_path，不碰本機真實資料
- requests 與非 loopback socket 一律擋下並記錄，每個測試結束斷言 0 次
- AI：process_analysis_task_async 以假 AI 取代；離線閉環案例用真管線，但 AIService 任何呼叫即失敗
- 相關 settings 全部 monkeypatch，不依賴本機 .env
"""
import asyncio
import importlib.util
import io
import json
import logging
import os
import re
import shutil
import socket
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
import requests
from fastapi import BackgroundTasks
from fastapi.testclient import TestClient

import app.api.threads as threads_api
import app.main as main_module
import app.utils.share as share_mod
import app.workers.pandas_task_processor as proc
from app.config import settings
from app.main import app
from app.services import threads_state
from app.services.ai_service import AIService
from app.services.cache_service import CacheService
from app.services.pandas_store import PandasStore
from app.services.task_store import TaskStore
from app.services.threads_reply import _in_emoji_range, strip_emoji, threads_len
from app.utils.admin_auth import MSG_ADMIN_DISABLED, MSG_UNAUTHORIZED
from app.utils.source_tier import tier_of
from app.workers import threads_bot

BACKEND = Path(__file__).resolve().parent.parent
EXAMPLE_MENTIONS = BACKEND / "scripts" / "threads_sim_mentions.example.json"

TOKEN = "0123456789abcdef0123456789abcdef"
BASE = "https://fakenewsverify.example"
TIER1_URL = "https://www.mygopen.com/2026/08/line.html"
_LOOPBACK = ("127.0.0.1", "::1", "localhost")

STATUS_KEYS = {
    # spec §5.3 全部欄位
    "enabled", "mode", "configured", "poll_minutes", "replied_count", "last_poll_at",
    "last_poll_stats", "last_error", "backoff_until", "token_expires_at", "token_days_left",
    "authorized_at", "auth_days_left", "reply_quota", "daily_replies", "daily_cap", "dev_mode_notice",
    # T-10 另加（S-11 sim 路徑提示）
    "sim_mentions_path",
}
DEV_NOTICE = (
    "目前為開發模式：只有被加入為測試人員的 Threads 帳號 @factcheck_tw_bot 才會收到回覆。"
    "公開服務需通過 Meta App Review 與企業驗證，為本專題論文所述之上線條件。"
)
UNAUTHORIZED = {"detail": MSG_UNAUTHORIZED, "code": "unauthorized"}
ADMIN_DISABLED = {"detail": MSG_ADMIN_DISABLED, "code": "admin_disabled"}

AI_SCAM = {
    "is_risk": True, "risk_type": "SCAM", "category": "Phishing", "confidence_score": 0.93,
    "summary": "假冒健保署的釣魚訊息，點連結會被騙取個資", "explanation": "健保署不會以訊息要求點連結重新驗證。",
    "sources": [{"title": "MyGoPen：健保卡停用是假的", "url": TIER1_URL}],
}


# ── fixtures ─────────────────────────────────────────────────────
@pytest.fixture
def network_calls(monkeypatch):
    calls = []

    def fake_request(self, method, url, *args, **kwargs):
        calls.append((method, url))
        raise AssertionError(f"unexpected HTTP call: {method} {url}")

    def blocked(*args, **kwargs):
        calls.append(("requests", args[:1]))
        raise AssertionError("unexpected requests call")

    real_connect = socket.socket.connect

    def guarded_connect(self, address):
        host = address[0] if isinstance(address, tuple) else address
        if host not in _LOOPBACK:
            calls.append(("socket", address))
            raise AssertionError(f"unexpected socket connect: {address}")
        return real_connect(self, address)

    monkeypatch.setattr(requests.Session, "request", fake_request)
    for name in ("get", "post", "request"):
        monkeypatch.setattr(requests, name, blocked)
    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    yield calls
    assert calls == []


@pytest.fixture
def env(tmp_path, monkeypatch, network_calls):
    """sim 模式、ADMIN_TOKEN 已設、工作目錄 = tmp_path（data/ 全部隔離）。"""
    monkeypatch.chdir(tmp_path)
    data = tmp_path / "data"
    data.mkdir()
    assert Path("data").resolve() == data.resolve()
    for key, value in {
        "ADMIN_TOKEN": TOKEN,
        "THREADS_MODE": "sim",
        "ENABLE_THREADS_BOT": False,
        "THREADS_ACCESS_TOKEN": "",
        "THREADS_USER_ID": "",
        "THREADS_BASE_URL": "https://graph.threads.net/v1.0",
        "BOT_HANDLE": "factcheck_tw_bot",
        "PUBLIC_BASE_URL": BASE,
        "THREADS_POLL_MINUTES": 5,
        "THREADS_MAX_REPLIES_PER_POLL": 5,
        "THREADS_MAX_REPLIES_PER_DAY": 50,
    }.items():
        monkeypatch.setattr(settings, key, value)
    yield SimpleNamespace(root=tmp_path, data=data)
    assert not threads_bot._POLL_LOCK.locked()


@pytest.fixture
def client():
    return TestClient(app)  # 不進 lifespan：不動 SQLite、不啟排程


@pytest.fixture
def spy_tasks(monkeypatch):
    """BackgroundTasks.add_task 只記錄、不執行（live 模式不可真的去打 Threads API）。"""
    added = []

    def fake_add_task(self, func, *args, **kwargs):
        added.append((func, args, kwargs))

    monkeypatch.setattr(BackgroundTasks, "add_task", fake_add_task)
    return added


class FakeAI:
    """取代 process_analysis_task_async：以真的 _build_result 組結果並完成任務（零點數）。"""

    def __init__(self, analysis=None, cache_layer="hash"):
        self.analysis = analysis or AI_SCAM
        self.cache_layer = cache_layer
        self.calls = []

    async def __call__(self, task_id, input_data, input_type):
        self.calls.append({"task_id": task_id, "input_data": input_data, "input_type": input_type})
        result = proc._build_result(
            dict(self.analysis), cached=self.cache_layer is not None,
            cache_layer=self.cache_layer, result_id=task_id,
        )
        proc._complete(TaskStore(), task_id, result)
        return result


@pytest.fixture
def fake_ai(monkeypatch):
    ai = FakeAI()
    monkeypatch.setattr(proc, "process_analysis_task_async", ai)
    return ai


def _auth(token=TOKEN):
    return {"X-Admin-Token": token}


def _copy_example_mentions(env):
    dest = env.data / "threads_sim" / "mentions.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(EXAMPLE_MENTIONS, dest)
    return dest


def _write_token_file(env, *, expires_in: timedelta, authorized_ago: timedelta, token="SECRET-FILE-TOKEN"):
    now = datetime.now(timezone.utc)
    path = env.data / "threads_token.json"
    path.write_text(json.dumps({
        "access_token": token, "user_id": "bot-user-1",
        "obtained_at": (now - timedelta(days=1)).isoformat(),
        "expires_at": (now + expires_in).isoformat(),
        "authorized_at": (now - authorized_ago).isoformat(),
    }), encoding="utf-8")
    return token


def _fresh_lock(env, age_seconds=0.0):
    lock = threads_bot.lock_path()
    assert lock.resolve() == (env.data / "threads_poll.lock").resolve()
    lock.write_text(json.dumps({
        "pid": os.getpid(), "token": "someone-else", "created_at": time.time() - age_seconds,
    }), encoding="utf-8")
    return lock


# ══════════════════════════════════════════════════════════════════
# T-10：GET /api/threads/status
# ══════════════════════════════════════════════════════════════════
def test_status_sim_full_schema(env, client):
    resp = client.get("/api/threads/status")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body) == STATUS_KEYS
    assert body["mode"] == "sim" and body["enabled"] is True and body["configured"] is True
    assert body["poll_minutes"] == 5 and body["daily_cap"] == 50
    assert body["replied_count"] == 0 and body["daily_replies"] == 0
    for key in ("last_poll_at", "last_poll_stats", "last_error", "backoff_until", "reply_quota",
                "token_expires_at", "token_days_left", "authorized_at", "auth_days_left"):
        assert body[key] is None, key
    assert body["dev_mode_notice"] == DEV_NOTICE
    assert body["sim_mentions_path"] == "data/threads_sim/mentions.json"
    # 驗收 curl 比對的是原始 JSON 字串（compact）
    assert '"mode":"sim"' in resp.text
    # 讀取 status 不建立任何 state 檔
    assert not threads_state.state_path().exists()


def test_status_bot_handle_substituted_and_at_prefix_tolerated(env, client, monkeypatch):
    monkeypatch.setattr(settings, "BOT_HANDLE", "@another_bot")
    notice = client.get("/api/threads/status").json()["dev_mode_notice"]
    assert notice == DEV_NOTICE.replace("@factcheck_tw_bot", "@another_bot")


def test_status_reflects_state_written_by_poll(env, client):
    today = threads_state.taipei_today()
    st = threads_state.load_state()
    st.update({
        "replied_ids": ["m1", "m2", "m3"],
        "last_poll_at": "2026-09-15T08:00:00+00:00",
        "last_stats": {"checked": 3, "replied": 2, "skipped": 1, "errors": 0},
        "last_error": "ai_unavailable",
        "backoff_until": "2026-09-15T09:00:00+00:00",
        "daily": {"date": today, "replies": 4},
        "reply_quota": {"usage": 12, "total": 1000},
    })
    threads_state.save_state(st)
    body = client.get("/api/threads/status").json()
    assert body["replied_count"] == 3
    assert body["last_poll_at"] == "2026-09-15T08:00:00+00:00"
    assert body["last_poll_stats"] == {"checked": 3, "replied": 2, "skipped": 1, "errors": 0}
    assert body["last_error"] == "ai_unavailable"
    assert body["backoff_until"] == "2026-09-15T09:00:00+00:00"
    assert body["daily_replies"] == 4
    assert body["reply_quota"] == {"usage": 12, "total": 1000}


def test_status_daily_replies_resets_on_new_taipei_day(env, client):
    st = threads_state.load_state()
    st["daily"] = {"date": "2000-01-01", "replies": 49}
    threads_state.state_path().write_text(json.dumps(st), encoding="utf-8")   # 繞過 save_state 的跨日重置
    assert client.get("/api/threads/status").json()["daily_replies"] == 0


@pytest.mark.parametrize("mode,legacy", [("off", False), (None, False)])
def test_status_off_mode(env, client, monkeypatch, mode, legacy):
    monkeypatch.setattr(settings, "THREADS_MODE", mode)
    monkeypatch.setattr(settings, "ENABLE_THREADS_BOT", legacy)
    body = client.get("/api/threads/status").json()
    assert set(body) == STATUS_KEYS
    assert body["mode"] == "off" and body["enabled"] is False and body["configured"] is False
    assert body["sim_mentions_path"] is None
    assert body["dev_mode_notice"] == DEV_NOTICE


def test_status_expired_token_reports_token_invalid(env, client, spy_tasks, network_calls, monkeypatch):
    """live 模式、過期 token 檔：尚未輪詢也要看到 token_invalid，且不發任何網路請求。"""
    settings_token = "SECRET-ENV-TOKEN"
    monkeypatch.setattr(settings, "THREADS_ACCESS_TOKEN", settings_token)
    monkeypatch.setattr(settings, "THREADS_MODE", "live")
    file_token = _write_token_file(env, expires_in=-timedelta(hours=2), authorized_ago=timedelta(days=61))

    resp = client.get("/api/threads/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["mode"] == "live" and body["enabled"] is True
    assert body["last_error"] == "token_invalid"
    assert body["configured"] is False
    assert body["token_days_left"] < 0
    assert body["token_expires_at"] and body["authorized_at"]
    assert isinstance(body["auth_days_left"], int) and 28 <= body["auth_days_left"] <= 29
    assert body["sim_mentions_path"] is None
    assert file_token not in resp.text and settings_token not in resp.text
    assert threads_state.load_state()["last_error"] is None     # status 只讀、不寫 state
    assert not threads_state.state_path().exists()

    # poll：授權通過後明確回「沒開始」（不排背景工作、不打 API）
    poll = client.post("/api/threads/poll", headers=_auth())
    assert poll.status_code == 200
    assert poll.json()["started"] is False and poll.json()["code"] == "token_invalid"
    assert file_token not in poll.text
    assert spy_tasks == [] and network_calls == []


def test_status_live_valid_token_days_left(env, client, spy_tasks, monkeypatch):
    monkeypatch.setattr(settings, "THREADS_MODE", "live")
    file_token = _write_token_file(env, expires_in=timedelta(days=59, hours=12), authorized_ago=timedelta(hours=1))
    resp = client.get("/api/threads/status")
    body = resp.json()
    assert body["configured"] is True and body["last_error"] is None
    assert 55 <= body["token_days_left"] <= 60            # T-15 驗收區間
    assert 88 <= body["auth_days_left"] <= 90
    assert file_token not in resp.text

    poll = client.post("/api/threads/poll", headers=_auth())
    assert poll.status_code == 202 and poll.json() == {"started": True}
    assert [(f, a) for f, a, _ in spy_tasks] == [(threads_api.run_poll_quietly, ("api",))]
    assert file_token not in poll.text


# ══════════════════════════════════════════════════════════════════
# T-10：POST /api/threads/poll
# ══════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("mode,legacy", [("off", False), (None, False)])
@pytest.mark.parametrize("admin_token", [TOKEN, ""])
def test_poll_off_mode_threads_disabled_before_auth(env, client, spy_tasks, monkeypatch, mode, legacy, admin_token):
    monkeypatch.setattr(settings, "THREADS_MODE", mode)
    monkeypatch.setattr(settings, "ENABLE_THREADS_BOT", legacy)
    monkeypatch.setattr(settings, "ADMIN_TOKEN", admin_token)
    for headers in (None, _auth("wrong"), _auth()):
        resp = client.post("/api/threads/poll", headers=headers)
        assert resp.status_code == 200
        assert resp.json() == {"started": False, "code": "threads_disabled"}
    assert spy_tasks == []


def test_poll_sim_auth_401_403_then_202(env, client, spy_tasks, monkeypatch):
    for headers in (None, _auth(""), _auth("wrong"), _auth(TOKEN[:-1])):
        resp = client.post("/api/threads/poll", headers=headers)
        assert resp.status_code == 401 and resp.json() == UNAUTHORIZED
    assert spy_tasks == []

    monkeypatch.setattr(settings, "ADMIN_TOKEN", "")
    resp = client.post("/api/threads/poll", headers=_auth())
    assert resp.status_code == 403 and resp.json() == ADMIN_DISABLED
    assert spy_tasks == []

    monkeypatch.setattr(settings, "ADMIN_TOKEN", TOKEN)
    resp = client.post("/api/threads/poll", headers=_auth())
    assert resp.status_code == 202
    assert resp.json() == {"started": True}
    assert TOKEN not in resp.text
    assert [(f, a) for f, a, _ in spy_tasks] == [(threads_api.run_poll_quietly, ("api",))]


def test_poll_live_without_token_is_not_configured_after_auth(env, client, spy_tasks, monkeypatch):
    monkeypatch.setattr(settings, "THREADS_MODE", "live")
    assert client.post("/api/threads/poll").status_code == 401     # 授權仍在「是否設定完成」之前
    resp = client.post("/api/threads/poll", headers=_auth())
    assert resp.status_code == 200
    body = resp.json()
    assert body["started"] is False and body["code"] == "threads_not_configured" and body["detail"]
    assert spy_tasks == []


def test_poll_lock_file_busy_409_then_stale_202(env, client, spy_tasks):
    lock = _fresh_lock(env)
    resp = client.post("/api/threads/poll", headers=_auth())
    assert resp.status_code == 409
    assert resp.json()["code"] == "poll_in_progress" and resp.json()["detail"]
    assert spy_tasks == []
    assert lock.exists()          # API 只檢查，不動別人的鎖

    _fresh_lock(env, age_seconds=threads_bot.LOCK_STALE_SECONDS + 60)   # 超過 15 分鐘 = 殘留
    resp = client.post("/api/threads/poll", headers=_auth())
    assert resp.status_code == 202 and len(spy_tasks) == 1
    lock.unlink()


def test_poll_in_process_lock_busy_409(env, client, spy_tasks):
    async def scenario():
        async with threads_bot._POLL_LOCK:          # 同行程另一輪（排程）正持有 asyncio.Lock
            return await asyncio.to_thread(client.post, "/api/threads/poll", headers=_auth())

    resp = asyncio.run(scenario())
    assert resp.status_code == 409 and resp.json()["code"] == "poll_in_progress"
    assert spy_tasks == []
    assert not threads_bot.lock_path().exists()


def test_poll_202_runs_sim_round_and_status_replies_follow(env, client, fake_ai):
    """202 後背景真的跑完一輪 sim（假 AI）：status.last_poll_at 更新、replies 看得到，二次 poll 不重複。"""
    _copy_example_mentions(env)
    before = client.get("/api/threads/status").json()
    assert before["last_poll_at"] is None

    resp = client.post("/api/threads/poll", headers=_auth())      # TestClient 會跑完背景工作才返回
    assert resp.status_code == 202 and resp.json() == {"started": True}

    st = client.get("/api/threads/status").json()
    assert st["last_poll_at"] is not None and st["last_error"] is None
    assert st["last_poll_stats"] == {"checked": 3, "replied": 3, "skipped": 0, "errors": 0}
    assert st["replied_count"] == 3 and st["daily_replies"] == 1   # 只有 m1 經 AI

    records = client.get("/api/threads/replies").json()["records"]
    assert [r["mention_id"] for r in records] == ["m3", "m2", "m1"]          # 倒序
    m1 = records[-1]
    assert m1["mode"] == "sim" and m1["frame_type"] == "red" and m1["risk_type"] == "SCAM"
    assert m1["reply_id"] == "sim_reply_1" and m1["result_id"] == fake_ai.calls[0]["task_id"]
    assert f"{BASE}/r/{m1['result_id']}" in m1["reply_text"]
    assert set(m1) == set(threads_state.REPLY_RECORD_FIELDS)
    sim_lines = (env.data / "threads_sim" / "replies.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(sim_lines) == 3
    assert not threads_bot.lock_path().exists()

    # 結果頁讀得到同一筆（origin=threads_sim）
    result = client.get(f"/api/result/{m1['result_id']}").json()
    assert result["origin"] == "threads_sim" and result["result"]["cache_layer"] == "hash"

    first_poll_at = st["last_poll_at"]
    time.sleep(0.01)
    assert client.post("/api/threads/poll", headers=_auth()).status_code == 202
    st2 = client.get("/api/threads/status").json()
    assert st2["last_poll_at"] != first_poll_at
    assert st2["last_poll_stats"]["replied"] == 0
    assert len((env.data / "threads_sim" / "replies.jsonl").read_text(encoding="utf-8").splitlines()) == 3
    assert len(fake_ai.calls) == 1


@pytest.mark.parametrize("http, last_error, minutes", [(401, "token_invalid", 60), (429, "rate_limited", 5)])
def test_status_shows_last_error_and_backoff_after_injected_mentions_error(env, client, fake_ai, http, last_error, minutes):
    """T-13 驗收：mentions 端點 401／429 注入後，status.last_error 正確且 backoff_until 非 null；
    backoff 期間再觸發 poll 仍回 202，但整輪略過（不打 API、last_poll_at 不變）。"""
    dest = _copy_example_mentions(env)
    data = json.loads(dest.read_text(encoding="utf-8"))
    data["mentions"][0]["_sim_error"] = {"on": "get_mentions", "http": http}
    dest.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    assert client.post("/api/threads/poll", headers=_auth()).status_code == 202
    st = client.get("/api/threads/status").json()
    assert set(st) == STATUS_KEYS                                   # spec §5.3 欄位不變
    assert st["last_error"] == last_error and st["backoff_until"] is not None
    assert st["last_poll_stats"] == {"checked": 0, "replied": 0, "skipped": 0, "errors": 1}
    until = datetime.fromisoformat(st["backoff_until"])
    left = (until - datetime.now(timezone.utc)).total_seconds() / 60
    assert minutes - 0.5 <= left <= minutes
    assert fake_ai.calls == [] and client.get("/api/threads/replies").json() == {"records": []}

    first_poll_at = st["last_poll_at"]
    time.sleep(0.01)
    assert client.post("/api/threads/poll", headers=_auth()).status_code == 202
    again = client.get("/api/threads/status").json()
    assert again["last_poll_at"] == first_poll_at and again["backoff_until"] == st["backoff_until"]
    assert again["last_error"] == last_error and not threads_bot.lock_path().exists()


def test_background_poll_race_poll_in_progress_is_swallowed(env, client, fake_ai, monkeypatch, caplog):
    """檢查通過後、背景工作開始前被另一輪搶到鎖：不丟例外、只有 threads_bot 的一行 warning。"""
    _copy_example_mentions(env)
    monkeypatch.setattr(threads_api, "poll_in_progress", lambda *a, **k: False)
    lock = _fresh_lock(env)
    with caplog.at_level(logging.DEBUG):
        resp = client.post("/api/threads/poll", headers=_auth())
    assert resp.status_code == 202
    busy = [r for r in caplog.records if "poll_in_progress" in r.getMessage() and r.levelno >= logging.INFO]
    assert len(busy) == 1 and busy[0].levelno == logging.WARNING
    assert not any(r.exc_info for r in caplog.records)
    assert not any(r.levelno >= logging.ERROR for r in caplog.records)
    assert fake_ai.calls == [] and threads_state.load_state()["last_poll_at"] is None
    lock.unlink()


# ══════════════════════════════════════════════════════════════════
# T-10：GET /api/threads/replies
# ══════════════════════════════════════════════════════════════════
def test_replies_newest_first_limit_fields_and_validation(env, client):
    for i in range(1, 13):
        threads_state.append_reply_record({
            "mention_id": f"r{i}", "mode": "sim", "result_id": f"task-{i}", "frame_type": "red",
            "risk_type": "SCAM", "username": "tester_a", "source_text_preview": "預覽",
            "reply_text": "回覆", "reply_id": f"sim_reply_{i}", "permalink": None,
        })
    path = threads_state.replies_path()
    with path.open("a", encoding="utf-8") as fh:
        fh.write("{broken json\n")
        fh.write(json.dumps({"mention_id": "r13", "mode": "sim", "reply_id": "sim_reply_13",
                             "access_token": "LEAK"}) + "\n")

    body = client.get("/api/threads/replies").json()
    ids = [r["mention_id"] for r in body["records"]]
    assert ids == ["r13", "r12", "r11", "r10", "r9", "r8", "r7", "r6", "r5", "r4"]   # 預設 10、倒序、壞行略過
    for rec in body["records"]:
        assert set(rec) == set(threads_state.REPLY_RECORD_FIELDS)
    assert "LEAK" not in client.get("/api/threads/replies?limit=1").text

    assert [r["mention_id"] for r in client.get("/api/threads/replies?limit=3").json()["records"]] == ["r13", "r12", "r11"]
    assert len(client.get("/api/threads/replies?limit=50").json()["records"]) == 13
    for bad in ("0", "51", "-1", "abc"):
        resp = client.get(f"/api/threads/replies?limit={bad}")
        assert resp.status_code == 422 and resp.json()["code"] == "validation_error"


def test_replies_empty_when_no_file(env, client):
    assert client.get("/api/threads/replies").json() == {"records": []}


# ══════════════════════════════════════════════════════════════════
# T-10：排程工作（app/main.py）
# ══════════════════════════════════════════════════════════════════
def test_scheduler_registers_quiet_poll_job(env, monkeypatch):
    monkeypatch.setattr(main_module, "init_sql_db", lambda: None)
    monkeypatch.setattr(share_mod, "warn_if_public_base_url_missing", lambda *a, **k: None)
    monkeypatch.setattr(settings, "ENABLE_SCHEDULER", False)
    monkeypatch.setattr(settings, "THREADS_POLL_MINUTES", 7)

    async def scenario():
        async with main_module.lifespan(app):
            job = app.state.scheduler.get_job("threads_poll")
            return job.func, dict(job.kwargs), job.trigger.interval

    func, kwargs, interval = asyncio.run(scenario())
    assert func is threads_api.run_poll_quietly
    assert kwargs == {"trigger": "scheduler"}
    assert interval == timedelta(minutes=7)
    del app.state.scheduler


def test_scheduler_job_poll_in_progress_one_log_line_no_traceback(env, caplog):
    _copy_example_mentions(env)
    lock = _fresh_lock(env)
    with caplog.at_level(logging.DEBUG):
        out = asyncio.run(threads_api.run_poll_quietly(trigger="scheduler"))
    assert out is None
    visible = [r for r in caplog.records if r.levelno >= logging.INFO]
    assert len(visible) == 1
    assert visible[0].levelno == logging.WARNING and "poll_in_progress" in visible[0].getMessage()
    assert not any(r.exc_info for r in caplog.records)
    assert json.loads(lock.read_text(encoding="utf-8"))["token"] == "someone-else"   # 不動別人的鎖
    lock.unlink()


def test_scheduler_job_unexpected_error_is_logged_not_raised(env, monkeypatch, caplog):
    async def boom():
        raise RuntimeError("boom")

    monkeypatch.setattr(threads_api, "run_threads_poll", boom)
    with caplog.at_level(logging.INFO):
        assert asyncio.run(threads_api.run_poll_quietly(trigger="scheduler")) is None
    errors = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert len(errors) == 1 and "scheduler" in errors[0].getMessage()


# ══════════════════════════════════════════════════════════════════
# T-11：scripts/test_threads_bot.py（--reset-sim 離線預熱、--poll）
# ══════════════════════════════════════════════════════════════════
SCRIPT_PATH = BACKEND / "scripts" / "test_threads_bot.py"
SEED_FILE = BACKEND / "scripts" / "threads_sim_seed.json"
FIXTURE_MENTIONS = Path(__file__).parent / "fixtures" / "threads_mentions.json"
P100_TEXT = "健保卡即日起停用！請點 https://nhi-verify.xyz 重新驗證，逾期停卡"
SEED_URL = "https://www.mygopen.com/2026/08/line.html"
RED = "\U0001F534"
HERO_LINE = "poll -> mention m1 -> cache hash -> sources: 1 x tier1 -> reply sim_reply_1"


def _load_script():
    spec = importlib.util.spec_from_file_location("threads_bot_script_under_test", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)   # 非 __main__：不會 chdir
    return module


script = _load_script()


@pytest.fixture
def sim(env, monkeypatch):
    """sim 重播環境：AI 任何呼叫即失敗（證明 hash 命中不花點數）、預設不做 embedding。"""
    ai_calls = []

    def no_ai(*args, **kwargs):
        ai_calls.append(args[1:2])
        raise AssertionError("AI must not be called in the sim replay")

    for name in ("analyze_content", "analyze_image", "_run_analysis", "generate_embedding"):
        monkeypatch.setattr(AIService, name, no_ai)
    monkeypatch.setattr(script, "_default_embedder", lambda: None)
    env.mentions = env.data / "threads_sim" / "mentions.json"
    env.sim_replies = env.data / "threads_sim" / "replies.jsonl"
    yield env
    assert ai_calls == []
    assert not threads_bot.lock_path().exists()


def _lines(path):
    return [json.loads(x) for x in Path(path).read_text(encoding="utf-8").splitlines() if x.strip()]


def _kb():
    return PandasStore().get_all_records()


def _no_sleep(_seconds):
    return None


def _mentions_only(env, ids):
    data = json.loads(EXAMPLE_MENTIONS.read_text(encoding="utf-8"))
    data["mentions"] = [m for m in data["mentions"] if m["id"] in ids]
    env.mentions.parent.mkdir(parents=True, exist_ok=True)
    env.mentions.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def test_seed_matches_sim_posts_and_is_gold_tier1_scam():
    seeds = script.load_seeds(SEED_FILE)
    assert list(seeds) == [CacheService.generate_hash(P100_TEXT)]
    example = json.loads(EXAMPLE_MENTIONS.read_text(encoding="utf-8"))
    fixture = json.loads(FIXTURE_MENTIONS.read_text(encoding="utf-8"))
    assert example["posts"]["p100"]["text"] == fixture["posts"]["p100"]["text"] == P100_TEXT

    seed = next(iter(seeds.values()))
    result = seed["result"]
    assert result["is_risk"] is True and result["risk_type"] == "SCAM" and result["category"] == "Phishing"
    assert len(result["summary"]) <= 120 and strip_emoji(result["summary"]) == result["summary"]
    [source] = result["sources"]
    assert source["url"] == SEED_URL and tier_of(source["url"], source["title"], offline=True) == 1

    built = proc._build_result(result, cached=True, cache_layer="hash", result_id="rid-1", label_source="gold")
    assert built["verification_status"] == "rule" and built["source_tier"] == 1
    reply = threads_bot.format_verdict_reply(built, f"{BASE}/r/rid-1")
    lines = reply.split("\n")
    assert lines[0] == RED + " 詐騙警告"
    assert f"查核來源：{SEED_URL}" in lines and f"完整判讀：{BASE}/r/rid-1" in lines
    assert threads_len(reply) <= 400 and len(re.findall(r"https?://", reply)) == 2


def test_reset_sim_copies_example_and_prewarms_once(sim, caplog):
    out = []
    with caplog.at_level(logging.DEBUG, logger="threads_bot"):
        assert script.reset_sim(out=out.append) == 0
    # 預熱試算 m3（403）時不印 threads_bot warning；logger 用完恢復
    assert [r for r in caplog.records if r.name == "threads_bot"] == []
    assert logging.getLogger("threads_bot").disabled is False
    assert json.loads(sim.mentions.read_text(encoding="utf-8")) == json.loads(EXAMPLE_MENTIONS.read_text(encoding="utf-8"))
    assert any("已從 scripts/threads_sim_mentions.example.json 複製" in x for x in out)
    assert "[reset-sim] 離線預熱：已預熱 1 則／已存在 0 則" in out
    assert any("p100：已預熱（gold，詐騙警告，sources: 1 x tier1；未寫入向量" in x for x in out)

    df = _kb()
    assert len(df) == 1
    row = df.iloc[0]
    assert row["data_hash"] == CacheService.generate_hash(P100_TEXT) and row["raw_content"] == P100_TEXT
    assert row["label_source"] == "gold" and bool(row["verified"]) is True and row["source_tier"] == 1
    assert row["origin"] == "threads_sim" and row["risk_type"] == "SCAM" and row["content_vector"] is None
    hit = PandasStore().find_by_hash(CacheService.generate_hash(P100_TEXT))      # 管線實際用的 L1 查詢
    assert hit["label_source"] == "gold" and hit["sources"][0]["url"] == SEED_URL

    out = []
    assert script.reset_sim(out=out.append) == 0
    assert "[reset-sim] 離線預熱：已預熱 0 則／已存在 1 則" in out
    assert len(_kb()) == 1


def test_reset_sim_clears_only_sim_records_and_keeps_live_state(sim):
    _copy_example_mentions(sim)
    sim.sim_replies.write_text("".join(
        json.dumps({"ts": "t", "mention_id": m, "reply_id": f"sim_reply_{i}", "result_id": None, "text": "x"},
                   ensure_ascii=False) + "\n" for i, m in enumerate(["m1", "m2", "m9"], 1)
    ), encoding="utf-8")
    live = {"mention_id": "17900011122", "mode": "live", "reply_id": "17900099988", "reply_text": "live"}
    threads_state.append_reply_record({"mention_id": "m1", "mode": "sim", "reply_id": "sim_reply_1"})
    threads_state.append_reply_record(live)
    threads_state.append_reply_record({"mention_id": "m8", "mode": "sim", "reply_id": "sim_reply_8"})
    with threads_state.replies_path().open("a", encoding="utf-8") as fh:
        fh.write("{not json\n")
    today = threads_state.taipei_today()
    st = threads_state.load_state()
    st.update({
        "replied_ids": ["17900011122", "m1", "m2", "m3", "m8", "m9"], "last_since": 1789372200,
        "last_poll_at": "2026-09-15T08:00:00+00:00", "daily": {"date": today, "replies": 3},
        "failed": {"m1": 1, "17900011122": 2}, "pending_publish": {"m2": {"container_id": "c"}},
    })
    threads_state.save_state(st)

    out = []
    assert script.reset_sim(out=out.append) == 0
    assert sim.sim_replies.exists() and sim.sim_replies.read_text(encoding="utf-8") == ""
    kept = threads_state.replies_path().read_text(encoding="utf-8").splitlines()
    assert len(kept) == 2 and json.loads(kept[0])["mode"] == "live" and kept[1] == "{not json"
    st = threads_state.load_state()
    assert st["replied_ids"] == ["17900011122"]          # live 的已回覆 id 保留（切回 live 不重複回覆）
    assert st["last_since"] == 0
    assert st["failed"] == {"17900011122": 2} and st["pending_publish"] == {}
    assert st["daily"]["replies"] == 3 and st["last_poll_at"] == "2026-09-15T08:00:00+00:00"
    assert "[reset-sim] 已清空 data/threads_sim/replies.jsonl（原 3 行）" in out
    assert "[reset-sim] data/threads_replies.jsonl：移除 mode=sim 2 行，保留其他 2 行" in out
    assert "[reset-sim] state：replied_ids 移除模擬 id 5 個（保留 1 個），last_since 歸零" in out


def test_reset_sim_broken_mentions_json_changes_nothing(sim):
    """錄影前手動刪 m2／m3 時打錯 JSON：明確報錯、回 1，回覆紀錄與 state 都不動、鎖已釋放。"""
    _copy_example_mentions(sim)
    good = sim.mentions.read_text(encoding="utf-8")
    sim.mentions.write_text(good.replace('"m3"', '"m3",,'), encoding="utf-8")
    sim.sim_replies.write_text('{"mention_id": "m1", "reply_id": "sim_reply_1"}\n', encoding="utf-8")
    st = threads_state.load_state()
    st.update({"replied_ids": ["m1"], "last_since": 1789372800})
    threads_state.save_state(st)

    out = []
    assert script.reset_sim(out=out.append) == 1
    assert any("JSON 格式錯誤（第" in x and "未做任何變更" in x for x in out)
    assert sim.sim_replies.read_text(encoding="utf-8").count("sim_reply_1") == 1
    st = threads_state.load_state()
    assert st["replied_ids"] == ["m1"] and st["last_since"] == 1789372800
    assert _kb().empty

    sim.mentions.write_text(json.dumps({"bot": {}}), encoding="utf-8")
    out = []
    assert script.reset_sim(out=out.append) == 1 and any("缺少 mentions 陣列" in x for x in out)

    sim.mentions.write_text(good, encoding="utf-8")
    assert script.reset_sim(out=[].append) == 0
    assert threads_state.load_state()["replied_ids"] == []


def test_reset_sim_strips_bom_so_backend_can_read_mentions(sim, tmp_path):
    """PowerShell 5.1 Set-Content -Encoding UTF8／舊記事本會加 BOM；後端以 utf-8 讀會變成 0 則 mention。"""
    from app.services.threads_sim import FakeThreadsService

    _copy_example_mentions(sim)
    sim.mentions.write_bytes(b"\xef\xbb\xbf" + sim.mentions.read_bytes())
    assert FakeThreadsService(mentions_path=sim.mentions).get_mentions(None) == []   # 前提：BOM 讓後端讀不到

    out = []
    assert script.reset_sim(out=out.append) == 0
    assert any("UTF-8 BOM" in x and "已移除" in x for x in out)
    assert not sim.mentions.read_bytes().startswith(b"\xef\xbb\xbf")
    assert [m["id"] for m in FakeThreadsService(mentions_path=sim.mentions).get_mentions(None)] == ["m1", "m2", "m3"]
    assert "[reset-sim] 離線預熱：已預熱 1 則／已存在 0 則" in out

    seed_with_bom = tmp_path / "seed_bom.json"
    seed_with_bom.write_bytes(b"\xef\xbb\xbf" + SEED_FILE.read_bytes())
    assert list(script.load_seeds(seed_with_bom)) == [CacheService.generate_hash(P100_TEXT)]


def test_reset_sim_keeps_non_utf8_live_line_bytes(sim):
    _copy_example_mentions(sim)
    path = threads_state.replies_path()
    live = json.dumps({"mention_id": "1790001", "mode": "live", "reply_id": "1790002"}).encode()
    odd = "舊編碼行".encode("cp950")
    sim_line = json.dumps({"mention_id": "m1", "mode": "sim", "reply_id": "sim_reply_1"}).encode()
    path.write_bytes(live + b"\n" + odd + b"\n" + sim_line + b"\n")
    sim.sim_replies.parent.mkdir(parents=True, exist_ok=True)
    sim.sim_replies.write_bytes(odd + b"\n" + sim_line + b"\n")

    assert script.reset_sim(out=[].append) == 0
    assert path.read_bytes() == live + b"\n" + odd + b"\n"
    assert sim.sim_replies.read_bytes() == b""


def test_reset_sim_refuses_while_poll_running_and_removes_stale_lock(sim, monkeypatch):
    lock = _fresh_lock(sim)                         # 本行程 pid（活著）、剛建立 → 真的在跑
    out = []
    assert script.reset_sim(out=out.append) == 2
    assert any("輪詢正在進行中" in x for x in out)
    assert lock.exists() and not sim.mentions.exists() and _kb().empty   # 什麼都沒動

    _fresh_lock(sim, age_seconds=threads_bot.LOCK_STALE_SECONDS + 5)
    out = []
    assert script.reset_sim(out=out.append) == 0
    assert any("已移除殘留的 data/threads_poll.lock（已超過 15 分鐘）" in x for x in out)

    _fresh_lock(sim)                                # 剛建立但寫鎖的行程已不在（後端被關掉）
    monkeypatch.setattr(script, "_pid_alive", lambda pid: False)
    out = []
    assert script.reset_sim(out=out.append) == 0
    assert any("已移除殘留的 data/threads_poll.lock（寫鎖的行程 pid" in x for x in out)


def test_pid_alive_detects_running_and_exited_process():
    assert script._pid_alive(os.getpid()) is True
    child = subprocess.Popen([sys.executable, "-c", "pass"])
    child.wait()
    assert script._pid_alive(child.pid) is False
    for bad in (None, 0, -1, True, "123"):
        assert script._pid_alive(bad) is None


def test_reset_sim_gold_row_shadows_older_unverified_duplicate(sim):
    _copy_example_mentions(sim)
    h = CacheService.generate_hash(P100_TEXT)
    old = PandasStore().save_record(
        data_type="TEXT", raw_content=P100_TEXT, content_hash=h, label_source="ai",
        ai_result={"is_risk": True, "risk_type": "SCAM", "confidence_score": 0.8, "summary": "舊判定",
                   "explanation": "e", "sources": [{"title": "臉書", "url": "https://www.facebook.com/x"}]},
    )
    assert old["verified"] is False
    out = []
    assert script.reset_sim(out=out.append) == 0
    assert "[reset-sim] 離線預熱：已預熱 1 則／已存在 0 則" in out
    df = _kb()
    assert len(df) == 2 and old["id"] in set(df["id"])     # 舊列保留、不刪資料
    hit = PandasStore().find_by_hash(h)
    assert hit["label_source"] == "gold" and bool(hit["verified"]) is True
    assert script.reset_sim(out=[].append) == 0 and len(_kb()) == 2


def test_reset_sim_keeps_existing_verified_ai_row(sim):
    _copy_example_mentions(sim)
    PandasStore().save_record(
        data_type="TEXT", raw_content=P100_TEXT, content_hash=CacheService.generate_hash(P100_TEXT),
        label_source="ai",
        ai_result={"is_risk": True, "risk_type": "SCAM", "confidence_score": 0.9, "summary": "AI 判定",
                   "explanation": "e", "sources": [{"title": "TFC", "url": "https://tfc-taiwan.org.tw/x/"}]},
    )
    out = []
    assert script.reset_sim(out=out.append) == 0
    assert "[reset-sim] 離線預熱：已預熱 0 則／已存在 1 則" in out
    df = _kb()
    assert len(df) == 1 and df.iloc[0]["label_source"] == "ai"


def test_reset_sim_writes_vector_when_embedding_available_and_backfills(sim):
    vec = [0.01 * (i % 7 + 1) for i in range(1536)]
    embed_calls = []

    def embed(text):
        embed_calls.append(text)
        return vec

    _copy_example_mentions(sim)
    assert script.reset_sim(out=[].append) == 0          # 第一次：斷網／未設定 → 只寫 hash
    assert _kb().iloc[0]["content_vector"] is None
    out = []
    assert script.reset_sim(embed=embed, out=out.append) == 0   # 之後 embedding 可用 → 補上向量
    assert any("已存在（" in x and "已補上向量" in x for x in out)
    assert embed_calls == [P100_TEXT]
    hit = PandasStore().find_similar_by_vector(vec, threshold=0.99)   # gold 已證實 → 參與 L2 語意比對
    assert hit is not None and hit["label_source"] == "gold"

    assert script.reset_sim(embed=embed, out=[].append) == 0
    assert embed_calls == [P100_TEXT]                    # 已有向量不再呼叫

    shutil.rmtree(sim.data)
    sim.data.mkdir()
    out = []
    assert script.reset_sim(embed=embed, out=out.append) == 0
    assert any("p100：已預熱（" in x and "已寫入向量" in x for x in out)
    assert len(_kb().iloc[0]["content_vector"]) == 1536


def test_reset_sim_embedding_failure_still_seeds_hash(sim):
    def broken(_text):
        raise RuntimeError("offline")

    assert script.reset_sim(embed=broken, out=[].append) == 0
    row = _kb().iloc[0]
    assert row["label_source"] == "gold" and row["content_vector"] is None


def test_reset_sim_reports_text_posts_without_seed(sim):
    data = json.loads(EXAMPLE_MENTIONS.read_text(encoding="utf-8"))
    data["mentions"].append({
        "id": "m40", "username": "tester_x", "media_type": "TEXT_POST",
        "text": "@factcheck_tw_bot 轉發這則訊息給十個群組就能領一千元禮券，今天截止",
        "timestamp": "2026-09-14T09:00:00+0000", "permalink": "https://www.threads.com/@tester_x/post/m40",
    })
    sim.mentions.parent.mkdir(parents=True)
    sim.mentions.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    out = []
    assert script.reset_sim(out=out.append) == 0
    assert "[reset-sim] 離線預熱：已預熱 1 則／已存在 0 則" in out
    assert any("m40：沒有種子，poll 時會呼叫 AI" in x for x in out)
    assert len(_kb()) == 1


def test_offline_closed_loop_reset_then_poll_via_api(sim, client):
    """FR-10 驗收 1＋T-11 驗收：真管線、無 Threads token、AI 與網路全擋 → hash 命中並回覆；二次 poll 不重複；reset 後可重播。"""
    assert settings.THREADS_ACCESS_TOKEN == "" and not (sim.data / "threads_token.json").exists()
    assert script.reset_sim(out=[].append) == 0

    out = []
    rc = script.poll_via_api("http://testserver", TOKEN, http=client, sleep=_no_sleep, timeout=5, out=out.append)
    assert rc == 0, out
    assert "[poll] 本輪結果：checked=3 replied=3 skipped=0 errors=0" in out
    assert HERO_LINE in out
    assert "poll -> mention m2 -> fixed reply (media_only) -> reply sim_reply_2" in out
    assert "poll -> mention m3 -> fixed reply (unreadable) -> reply sim_reply_3" in out
    assert "[poll] replied=3" in out
    assert not any(TOKEN in x for x in out)

    [line1, *_rest] = _lines(sim.sim_replies)
    text = line1["text"]
    assert line1["mention_id"] == "m1" and line1["reply_id"] == "sim_reply_1"
    assert text.split("\n")[0] == RED + " 詐騙警告"
    assert f"查核來源：{SEED_URL}" in text and f"{BASE}/r/{line1['result_id']}" in text
    assert threads_len(text) <= 400
    record = next(r for r in threads_state.read_reply_records(None) if r["mention_id"] == "m1")
    assert record["mode"] == "sim" and record["result_id"] == line1["result_id"]
    assert f"       result_id={record['result_id']} frame_type=red" in out
    # m3 固定文案是最後一筆，但「最新判定回覆」指向有 cache_layer 的 m1
    assert f"[poll] 最新判定回覆：result_id={record['result_id']} frame_type=red cache_layer=hash" in out

    page = client.get(f"/api/result/{record['result_id']}").json()
    assert page["origin"] == "threads_sim" and page["status"] == "completed"
    assert page["result"]["cache_layer"] == "hash" and page["result"]["frame_type"] == "red"
    assert [s["tier"] for s in page["result"]["sources"]] == [1]

    out = []
    assert script.poll_via_api("http://testserver", TOKEN, http=client, sleep=_no_sleep, timeout=5, out=out.append) == 0
    assert "[poll] replied=0" in out and "[poll] 本輪沒有新回覆" in out
    assert len(_lines(sim.sim_replies)) == 3

    out = []
    assert script.reset_sim(out=out.append) == 0
    assert "[reset-sim] 離線預熱：已預熱 0 則／已存在 1 則" in out
    out = []
    assert script.poll_via_api("http://testserver", TOKEN, http=client, sleep=_no_sleep, timeout=5, out=out.append) == 0
    assert HERO_LINE in out and "[poll] replied=3" in out
    assert len(_lines(sim.sim_replies)) == 3             # replies.jsonl 重設後重新編號


class _Resp:
    def __init__(self, status_code, body):
        self.status_code, self._body = status_code, body

    def json(self):
        return self._body


class _DownHttp:
    def get(self, url, **kwargs):
        raise requests.ConnectionError(f"refused: {url}")

    post = get


def test_poll_falls_back_in_process_when_backend_down_storyboard_mentions(sim):
    """錄影用 mentions.json 只留 p100＋m1（storyboard 準備清單 5）；後端沒開 → 本程序內跑一輪。"""
    _mentions_only(sim, {"m1"})
    assert script.reset_sim(out=[].append) == 0
    out = []
    assert script.run_poll("http://127.0.0.1:9", http=_DownHttp(), out=out.append) == 0, out
    assert any("後端未啟動" in x for x in out)
    mention_lines = [x for x in out if x.startswith("poll -> ")]
    assert mention_lines == [HERO_LINE]
    assert "[poll] 本輪結果：checked=1 replied=1 skipped=0 errors=0" in out and "[poll] replied=1" in out
    [line] = _lines(sim.sim_replies)
    assert any(x.startswith(f"[poll] 最新判定回覆：result_id={line['result_id']} frame_type=red cache_layer=hash")
               for x in out)
    task = TaskStore().get_task(line["result_id"])
    assert task["origin"] == "threads_sim" and json.loads(task["result_data"])["cache_layer"] == "hash"

    out = []
    assert script.run_poll("http://127.0.0.1:9", http=_DownHttp(), out=out.append) == 0
    assert "[poll] replied=0" in out


def test_poll_in_process_reports_poll_in_progress_and_off_mode(sim, monkeypatch):
    _mentions_only(sim, {"m1"})
    lock = _fresh_lock(sim)
    out = []
    assert script.run_poll("http://127.0.0.1:9", http=_DownHttp(), out=out.append) == 1
    assert any("poll_in_progress" in x for x in out)
    lock.unlink()

    monkeypatch.setattr(settings, "THREADS_MODE", "off")
    out = []
    assert script.run_poll("http://127.0.0.1:9", http=_DownHttp(), out=out.append) == 1
    assert any("threads_disabled" in x and "THREADS_MODE=sim" in x for x in out)


def test_poll_via_api_not_started_messages(env, client, spy_tasks, monkeypatch):
    def run(token=TOKEN):
        out = []
        rc = script.poll_via_api("http://testserver", token, http=client, sleep=_no_sleep, timeout=2, out=out.append)
        assert not any(TOKEN in x for x in out)
        return rc, "\n".join(out)

    rc, text = run(token="")
    assert rc == 1 and ".env 沒有 ADMIN_TOKEN" in text

    rc, text = run(token="wrong-token")
    assert rc == 1 and "unauthorized" in text

    lock = _fresh_lock(env)
    rc, text = run()
    assert rc == 1 and "poll_in_progress" in text
    lock.unlink()

    monkeypatch.setattr(settings, "THREADS_MODE", "live")
    rc, text = run()
    assert rc == 1 and "threads_not_configured" in text

    monkeypatch.setattr(settings, "THREADS_MODE", "off")
    rc, text = run()
    assert rc == 1 and "threads_disabled" in text and "THREADS_MODE=sim" in text

    monkeypatch.setattr(settings, "THREADS_MODE", "sim")
    monkeypatch.setattr(settings, "ADMIN_TOKEN", "")
    rc, text = run()
    assert rc == 1 and "admin_disabled" in text
    assert spy_tasks == []


class _StuckHttp:
    """POST 回 202，但 status.last_poll_at 永遠不變。"""

    def __init__(self, status):
        self.status, self.gets = status, 0

    def get(self, url, **kwargs):
        self.gets += 1
        if url.endswith("/api/threads/status"):
            return _Resp(200, dict(self.status))
        return _Resp(200, {"records": []})

    def post(self, url, **kwargs):
        assert kwargs["headers"] == {"X-Admin-Token": TOKEN}
        return _Resp(202, {"started": True})


def test_poll_via_api_times_out_and_detects_backoff(env):
    now = [0.0]

    def clock():
        return now[0]

    def sleep(seconds):
        now[0] += seconds

    http = _StuckHttp({"mode": "sim", "last_poll_at": "2026-09-15T08:00:00+00:00", "backoff_until": None})
    out = []
    assert script.poll_via_api("http://x", TOKEN, http=http, clock=clock, sleep=sleep, timeout=10, out=out.append) == 1
    assert any("等待逾時（10 秒）" in x for x in out)
    assert 5 <= http.gets <= 10

    future = (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat()
    http = _StuckHttp({"mode": "sim", "last_poll_at": None, "backoff_until": future})
    out = []
    assert script.poll_via_api("http://x", TOKEN, http=http, clock=clock, sleep=sleep, out=out.append) == 1
    assert any("輪詢暫停中" in x for x in out)


def test_describe_reply_formats(env):
    tier1 = {"url": SEED_URL, "tier": 1}
    rec = {"mention_id": "m1", "reply_id": "sim_reply_1", "result_id": "r1"}
    assert script.describe_reply(rec, {"cache_layer": "hash", "sources": [tier1]}) == HERO_LINE
    assert script.describe_reply(
        {"mention_id": "m9", "reply_id": "r9", "result_id": "x"},
        {"cache_layer": None, "sources": []},
    ) == "poll -> mention m9 -> cache miss -> AI -> sources: none -> reply r9"
    assert script.describe_reply(
        {"mention_id": "m5", "reply_id": "r5", "result_id": "x"},
        {"cache_layer": "vector", "sources": [tier1, {"url": "https://news.example/a", "tier": 2}, {"tier": 3}]},
    ) == "poll -> mention m5 -> cache vector -> sources: 1 x tier1, 1 x tier2 -> reply r5"
    assert script.describe_reply({"mention_id": "m2", "reply_id": "r2", "result_id": "x"}, None) == \
        "poll -> mention m2 -> cache ? -> sources: ? -> reply r2"
    fixed = {"mention_id": "m4", "reply_id": "r4", "result_id": None,
             "reply_text": threads_bot.reply_too_short()}
    assert script.describe_reply(fixed) == "poll -> mention m4 -> fixed reply (too_short) -> reply r4"


def test_dry_run_uses_threads_len_and_writes_sample(env):
    out = []
    assert script.dry_run(out=out.append) == 0
    sample = (env.data / "threads_reply_sample.txt").read_text(encoding="utf-8")
    assert sample.split("\n")[0] == RED + " 詐騙警告"
    assert "查核來源：https://165.npa.gov.tw/" in sample and threads_len(sample) <= 500
    assert any(f"threads_len={threads_len(sample)}" in x for x in out)
    assert any("ADMIN_TOKEN 已設定 = True" in x for x in out) and not any(TOKEN in x for x in out)
    source = SCRIPT_PATH.read_text(encoding="utf-8")
    assert "assert len(reply)" not in source


def test_live_check_without_token_exits_nonzero(env, monkeypatch):
    monkeypatch.setattr(settings, "THREADS_MODE", "live")
    out = []
    assert script.live_check(out=out.append) == 1
    assert any("未設定" in x for x in out)


def test_script_console_output_is_cp950_safe(monkeypatch):
    source = SCRIPT_PATH.read_text(encoding="utf-8")
    assert not any(_in_emoji_range(ch) for ch in source)
    assert "print(" not in source
    buf = io.TextIOWrapper(io.BytesIO(), encoding="cp950")
    monkeypatch.setattr(sys, "stdout", buf)
    script.say(RED + " 詐騙警告 ✓")
    buf.seek(0)
    written = buf.buffer.getvalue().decode("cp950")
    assert "\\U0001f534 詐騙警告" in written


def test_main_dispatch_and_workdir(env, monkeypatch):
    calls = []
    monkeypatch.setattr(script, "_default_embedder", lambda: None)
    monkeypatch.setattr(script, "reset_sim", lambda **kw: calls.append(("reset", kw)) or 0)
    monkeypatch.setattr(script, "run_poll", lambda api, **kw: calls.append(("poll", api)) or 0)
    assert script.main(["--reset-sim", "--poll", "--api", "http://127.0.0.1:8123"]) == 0
    assert calls == [("reset", {"embed": None}), ("poll", "http://127.0.0.1:8123")]
    calls.clear()
    assert script.main(["--poll"]) == 0 and calls == [("poll", "http://127.0.0.1:8000")]

    assert script._early_workdir(["--poll"]) == script.BACKEND_DIR
    assert script._early_workdir(["--workdir", str(env.root), "--reset-sim"]) == env.root.resolve()
