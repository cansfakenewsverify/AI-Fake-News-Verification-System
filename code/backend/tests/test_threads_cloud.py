"""Threads 機器人在雲端執行（2026-10-01）：狀態、回覆紀錄、輪詢鎖與 token 存在資料庫。

離線：資料庫換成記憶體版 FakePg（行為對齊 app/services/threads_pg.py；真的 Postgres 行為由
test_pg_store.py 的 threads 契約測試守著）。AI 判讀換成假的，零點數。
"""
import asyncio
import copy
import json
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import app.workers.pandas_task_processor as proc
from app.config import settings
from app.services import threads_pg, threads_state
from app.services.task_store import TaskStore
from app.services.threads_service import ThreadsService
from app.services.threads_sim import FakeThreadsService
from app.workers import threads_bot

FIXTURE = Path(__file__).parent / "fixtures" / "threads_mentions.json"
AI_SCAM = {
    "is_risk": True, "risk_type": "SCAM", "category": "Phishing", "confidence_score": 0.93,
    "summary": "假冒健保署的釣魚簡訊", "explanation": "健保署不會以簡訊要求重新驗證。",
    "sources": [{"title": "MyGoPen：健保卡停用是假的", "url": "https://www.mygopen.com/2026/09/nhi-card-rumor.html"}],
}


class FakePg:
    """記憶體版 ThreadsPgStore。"""

    def __init__(self):
        self.kv, self.rows, self.lock, self.calls = {}, [], None, []

    def get(self, key):
        return copy.deepcopy(self.kv.get(key))

    def put(self, key, value):
        self.kv[key] = json.loads(json.dumps(value))     # 與 jsonb 一樣只存得下 JSON

    def append_reply(self, row):
        if any(r.get("mention_id") == row.get("mention_id") for r in self.rows):
            return False
        self.rows.append(dict(row))
        return True

    def replies(self, limit=None):
        out = list(reversed(self.rows))
        return out[:limit] if limit else out

    def reply_ids(self):
        return {str(r["reply_id"]) for r in self.rows if r.get("reply_id")}

    def acquire_lock(self, token, stale_seconds):
        self.calls.append(("acquire", token))
        if self.lock is not None:
            return False
        self.lock = token
        return True

    def release_lock(self, token):
        self.calls.append(("release", token))
        if self.lock == token:
            self.lock = None
            return True
        return False

    def lock_held(self, stale_seconds):
        return self.lock is not None


@pytest.fixture
def cloud(monkeypatch, tmp_path):
    fake = FakePg()
    monkeypatch.setattr(settings, "STORAGE_BACKEND", "supabase")
    monkeypatch.setattr(settings, "SUPABASE_DB_URL", "postgresql://fake-host/db")
    monkeypatch.setattr(settings, "THREADS_MODE", "live")
    threads_pg.set_threads_pg(fake)
    yield fake
    threads_pg.set_threads_pg(None)


def test_cloud_mode_needs_supabase_live_and_no_data_dir(cloud, monkeypatch, tmp_path):
    assert threads_state.use_db(None) is True
    assert threads_state.use_db(tmp_path) is False          # 測試與模擬指定目錄一律用檔案
    monkeypatch.setattr(settings, "THREADS_MODE", "sim")
    assert threads_state.use_db(None) is False
    monkeypatch.setattr(settings, "THREADS_MODE", "live")
    monkeypatch.setattr(settings, "STORAGE_BACKEND", "local")
    assert threads_state.use_db(None) is False


def test_state_is_read_and_written_in_the_database(cloud, tmp_path):
    assert threads_state.state_initialized() is False
    state = threads_state.load_state()
    assert state["replied_ids"] == [] and state["last_since"] == 0
    state["replied_ids"] = ["m1"]
    state["last_since"] = 1700000000
    threads_state.save_state(state)
    assert cloud.kv["state"]["replied_ids"] == ["m1"]
    assert threads_state.state_initialized() is True
    assert threads_state.load_state()["last_since"] == 1700000000
    # 指定 data_dir 仍是檔案，不碰資料庫
    assert threads_state.load_state(tmp_path)["replied_ids"] == []
    assert threads_state.state_initialized(tmp_path) is True


def test_reply_records_are_in_the_database(cloud):
    threads_state.append_reply_record({"mention_id": "m1", "reply_id": "r1", "reply_text": "回覆一"})
    threads_state.append_reply_record({"mention_id": "m2", "reply_id": "r2", "reply_text": "回覆二"})
    threads_state.append_reply_record({"mention_id": "m1", "reply_id": "r9"})    # 同一則提及不重複記
    assert [r["mention_id"] for r in threads_state.read_reply_records(10)] == ["m2", "m1"]
    assert [r["mention_id"] for r in threads_state.read_reply_records(1)] == ["m2"]
    assert threads_state.own_reply_ids() == {"r1", "r2"}
    assert set(threads_state.read_reply_records(10)[0]) == set(threads_state.REPLY_RECORD_FIELDS)


class _AvailableClient:
    available = True
    invalid_reason = None

    def get_mentions(self, *args, **kwargs):
        raise AssertionError("must not read mentions before the state is initialized")


def test_poll_waits_until_the_cloud_state_is_initialized(cloud):
    out = asyncio.run(threads_bot.run_threads_poll(client=_AvailableClient()))
    assert out == {"started": False, "reason": "threads_state_not_initialized"}
    assert cloud.calls == []


@pytest.fixture
def bot(cloud, monkeypatch, tmp_path):
    mentions = tmp_path / "threads_sim" / "mentions.json"
    mentions.parent.mkdir(parents=True)
    shutil.copy(FIXTURE, mentions)
    data = json.loads(mentions.read_text(encoding="utf-8"))
    data["mentions"] = [m for m in data["mentions"] if m["id"] == "m1"]
    mentions.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(settings, "PUBLIC_BASE_URL", "https://factcheck-demo.vercel.app/")
    monkeypatch.setattr(settings, "BOT_HANDLE", "factcheck_tw_bot")
    monkeypatch.setattr(settings, "THREADS_MAX_REPLIES_PER_POLL", 5)
    monkeypatch.setattr(settings, "THREADS_MAX_REPLIES_PER_DAY", 50)
    store = TaskStore(data_dir=str(tmp_path / "tasks"))
    monkeypatch.setattr(threads_bot, "get_task_store", lambda: store)
    calls = []

    async def fake_ai(task_id, input_data, input_type):
        calls.append(input_data)
        result = proc._build_result(dict(AI_SCAM), cached=True, cache_layer="hash", result_id=task_id)
        proc._complete(store, task_id, result)
        return result

    monkeypatch.setattr(proc, "process_analysis_task_async", fake_ai)
    threads_state.save_state(threads_state.default_state())    # 搬遷腳本建好的初始狀態
    return FakeThreadsService(mentions_path=mentions), calls


def test_cloud_poll_uses_database_state_lock_and_records(cloud, bot):
    client, ai_calls = bot

    out = asyncio.run(threads_bot.run_threads_poll(client=client))

    assert out["started"] is True and out["replied"] == 1 and len(ai_calls) == 1
    assert cloud.kv["state"]["replied_ids"] == ["m1"]
    assert [r["mention_id"] for r in cloud.rows] == ["m1"]
    assert [c[0] for c in cloud.calls] == ["acquire", "release"] and cloud.lock is None
    # 第二輪：同一則不再回覆
    again = asyncio.run(threads_bot.run_threads_poll(client=client))
    assert again["replied"] == 0 and len(ai_calls) == 1


def test_database_lock_held_elsewhere_blocks_the_poll(cloud, bot):
    client, ai_calls = bot
    cloud.lock = "another-machine"
    assert threads_bot.poll_in_progress() is True
    with pytest.raises(threads_bot.PollInProgress):
        asyncio.run(threads_bot.run_threads_poll(client=client))
    assert ai_calls == [] and cloud.lock == "another-machine"


def _token(days_left, obtained_days_ago):
    now = datetime.now(timezone.utc)
    return {"access_token": "OLD-TOKEN", "user_id": "4242",
            "obtained_at": (now - timedelta(days=obtained_days_ago)).isoformat(),
            "expires_at": (now + timedelta(days=days_left, hours=1)).isoformat(),
            "authorized_at": (now - timedelta(days=obtained_days_ago)).isoformat()}


def test_token_is_read_from_the_database_in_cloud_mode(cloud, monkeypatch, tmp_path):
    monkeypatch.setattr("app.services.threads_service.TOKEN_PATH", tmp_path / "no_token_file.json")
    cloud.put("token", _token(40, 20))
    svc = ThreadsService()
    assert svc.token_source == "db" and svc.token == "OLD-TOKEN" and svc.user_id == "4242"
    assert svc.token_days_left == 40 and svc.available is True


@pytest.mark.parametrize("days_left,obtained_days_ago,due", [(5, 30, True), (40, 20, False), (5, 0.5, False)])
def test_cloud_token_is_refreshed_when_due(cloud, monkeypatch, tmp_path, days_left, obtained_days_ago, due):
    monkeypatch.setattr("app.services.threads_service.TOKEN_PATH", tmp_path / "no_token_file.json")
    cloud.put("token", _token(days_left, obtained_days_ago))
    svc = ThreadsService()
    refreshed = []

    def fake_refresh():
        refreshed.append(1)
        svc.token = "NEW-TOKEN"
        svc.token_expires_at = datetime.now(timezone.utc) + timedelta(days=60)
        return {"expires_in": 60 * 86400}

    monkeypatch.setattr(svc, "refresh_token", fake_refresh)
    assert svc.refresh_if_due() is due
    assert bool(refreshed) is due
    saved = cloud.kv["token"]
    assert saved["access_token"] == ("NEW-TOKEN" if due else "OLD-TOKEN")
    if due:
        assert saved["user_id"] == "4242" and ThreadsService().token_days_left >= 59


def test_file_token_is_not_auto_refreshed(monkeypatch, tmp_path):
    token_file = tmp_path / "threads_token.json"
    token_file.write_text(json.dumps(_token(5, 30)), encoding="utf-8")
    monkeypatch.setattr(settings, "THREADS_MODE", "live")
    svc = ThreadsService(token_path=token_file)
    assert svc.token_source == "file"
    monkeypatch.setattr(svc, "refresh_token", lambda: pytest.fail("file tokens are refreshed by threads_auth.py"))
    assert svc.refresh_if_due() is False
