"""Threads 機器人 sim 模式測試（FN-4）。

- T-05：ThreadsClient Protocol 與 FakeThreadsService 自身（test_fake_*）。
- T-08：單則 mention 處理 handle_mention／resolve_target（test_bot_*、test_resolve_*）。
- T-09：run_threads_poll 互斥鎖、since 游標、本地上限（test_poll_*）。
- T-13：HTTP 狀態碼分流與 backoff（test_backoff_*、test_unknown_4xx_*、test_link_limit_*、test_transient_*）。
- T-12：兩段式發佈＋FINISHED 狀態檢查＋pending_publish（test_container_*、test_fake_container_*）；
        ThreadsService（live 類別，requests 全 mock）的三步另見 test_threads_publish.py。

全部離線：以 tests/fixtures/threads_mentions.json 的複本在 tmp_path 操作，
requests 被封鎖，任何網路呼叫都會讓測試失敗；AI 以 monkeypatch 取代
process_analysis_task_async（零點數）。每個測試結束時 tmp_path 下不得殘留 threads_poll.lock。
"""
import asyncio
import json
import logging
import os
import re
import shutil
import time
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
import requests

import app.workers.pandas_task_processor as proc
from app.config import settings
from app.services import threads_service as ts
from app.services import threads_state
from app.services.task_store import TaskStore
from app.services.threads_reply import (
    reply_cannot_read,
    reply_media_only,
    reply_too_short,
    threads_len,
)
from app.services.threads_service import (
    ThreadsAPIError,
    ThreadsApiError,
    ThreadsClient,
    ThreadsService,
    get_threads_client,
)
from app.services.threads_sim import FakeThreadsService
from app.workers import threads_bot

FIXTURE = Path(__file__).parent / "fixtures" / "threads_mentions.json"
EXAMPLE = Path(__file__).resolve().parent.parent / "scripts" / "threads_sim_mentions.example.json"


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    def _blocked(*args, **kwargs):
        raise AssertionError("network access is not allowed in sim tests")

    for name in ("get", "post", "request"):
        monkeypatch.setattr(requests, name, _blocked)
    monkeypatch.setattr(requests.Session, "request", _blocked)


@pytest.fixture(autouse=True)
def _no_real_container_sleep(monkeypatch):
    """wait_container 的等待一律要注入（client.container_sleep）；真的睡到就讓測試失敗。"""
    def _blocked(seconds):
        raise AssertionError(f"wait_container really slept for {seconds}s in a test")

    monkeypatch.setattr(ts, "_default_sleep", _blocked)


@pytest.fixture(autouse=True)
def _no_leftover_poll_lock(tmp_path):
    yield
    leftovers = [str(p) for p in tmp_path.rglob("threads_poll.lock")]
    assert leftovers == [], f"threads_poll.lock left behind: {leftovers}"
    assert not threads_bot._POLL_LOCK.locked()


@pytest.fixture
def fake(tmp_path):
    p = tmp_path / "threads_sim" / "mentions.json"
    p.parent.mkdir(parents=True)
    shutil.copy(FIXTURE, p)
    return FakeThreadsService(mentions_path=p)


def _read_lines(path):
    return [json.loads(x) for x in Path(path).read_text(encoding="utf-8").splitlines() if x.strip()]


def test_fake_implements_protocol(fake):
    assert isinstance(fake, ThreadsClient)
    assert fake.available is True
    assert fake.invalid_reason is None


def test_fake_profile_and_publishing_limit(fake):
    assert fake.get_profile() == {"id": "bot001", "username": "factcheck_tw_bot"}
    assert fake.get_publishing_limit()["reply_config"]["quota_total"] == 1000


def test_fake_get_mentions_since_filter(fake, monkeypatch):
    # m6 帶 reply_to 注入，不影響讀取
    all_ids = [m["id"] for m in fake.get_mentions(None)]
    assert all_ids == ["m1", "m2", "m3", "m4", "m5", "m6"]

    # ISO 字串 since：嚴格大於
    ids = [m["id"] for m in fake.get_mentions("2026-09-14T08:10:00+0000")]
    assert ids == ["m4", "m5", "m6"]

    # unix 秒數 since（spec 7.4 傳給 get_mentions 的形式）；2026-09-14T08:20:00Z = 1789374000
    ids = [m["id"] for m in fake.get_mentions(1789374000)]
    assert ids == ["m6"]
    assert fake.get_mentions(1789374000 + 3600) == []


def test_fake_get_post(fake):
    post = fake.get_post("p100")
    assert post["username"] == "tester_a"
    assert "健保卡" in post["text"]
    assert fake.get_post("p101")["media_type"] == "IMAGE"
    with pytest.raises(ThreadsApiError) as ei:
        fake.get_post("nope")
    assert ei.value.status == 404


def test_fake_error_injection_get_post_403(fake):
    with pytest.raises(ThreadsApiError) as ei:
        fake.get_post("p102")
    assert ei.value.status == 403


def test_fake_get_post_injection_is_per_post(fake):
    """mention 上的 get_post 注入以貼文為單位（文件化行為）；posts 項目上的注入亦生效。"""
    data = json.loads(fake.mentions_path.read_text(encoding="utf-8"))
    # 第二則 @ 回覆 p102（不帶注入）：p102 仍 403，因為 get_post 只拿得到貼文 id
    data["mentions"].append({"id": "m7", "username": "tester_f", "text": "@factcheck_tw_bot 查一下",
                             "replied_to": {"id": "p102"}, "timestamp": "2026-09-14T08:30:00+0000"})
    # 貼文層級注入：p106 本身帶 _sim_error
    data["posts"]["p106"]["_sim_error"] = {"on": "get_post", "http": 500}
    fake.mentions_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ThreadsApiError) as ei:
        fake.get_post("p102")
    assert ei.value.status == 403
    with pytest.raises(ThreadsApiError) as ei:
        fake.get_post("p106")
    assert ei.value.status == 500
    # 其他貼文不受影響，回傳的貼文不含注入欄位
    assert "_sim_error" not in fake.get_post("p100")


def test_fake_error_injection_reply_to_429(fake):
    with pytest.raises(ThreadsApiError) as ei:
        fake.reply_to("m6", "text")
    assert ei.value.status == 429
    assert not fake.replies_path.exists()


def test_fake_error_injection_get_mentions(fake):
    data = json.loads(fake.mentions_path.read_text(encoding="utf-8"))
    data["mentions"][-1]["_sim_error"] = {"on": "get_mentions", "http": 401}
    fake.mentions_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ThreadsApiError) as ei:
        fake.get_mentions(None)
    assert ei.value.status == 401
    # 帶注入的 mention 被 since 過濾掉時不觸發
    assert [m["id"] for m in fake.get_mentions("2026-09-14T08:25:00+0000")] == []


def test_fake_reply_to_appends_line_and_increments_id(fake):
    r1 = fake.reply_to("m1", "回覆一", result_id="task-1")
    r2 = fake.reply_to("m4", "回覆二")
    assert (r1, r2) == ("sim_reply_1", "sim_reply_2")

    lines = _read_lines(fake.replies_path)
    assert len(lines) == 2
    assert fake.replies_path == fake.mentions_path.parent / "replies.jsonl"
    first = lines[0]
    assert set(first) == {"ts", "mention_id", "reply_id", "result_id", "text"}
    assert first["mention_id"] == "m1"
    assert first["reply_id"] == "sim_reply_1"
    assert first["result_id"] == "task-1"
    assert first["text"] == "回覆一"

    # 新實例沿用檔案行數，id 繼續遞增
    again = FakeThreadsService(mentions_path=fake.mentions_path)
    assert again.reply_to("m1", "回覆三") == "sim_reply_3"
    assert len(_read_lines(fake.replies_path)) == 3


def test_fake_publish_text_separate_file(fake):
    """publish_text 寫 posts.jsonl，不混進 replies.jsonl、不影響 sim_reply 編號。"""
    assert fake.publish_text("每日摘要") == "sim_post_1"
    assert fake.posts_path == fake.mentions_path.parent / "posts.jsonl"
    assert not fake.replies_path.exists()
    assert fake.reply_to("m1", "回覆一") == "sim_reply_1"
    assert fake.publish_text("每日摘要二") == "sim_post_2"
    assert fake.reply_to("m4", "回覆二") == "sim_reply_2"
    replies = _read_lines(fake.replies_path)
    assert [r["reply_id"] for r in replies] == ["sim_reply_1", "sim_reply_2"]
    assert all(set(r) == {"ts", "mention_id", "reply_id", "result_id", "text"} for r in replies)
    posts = _read_lines(fake.posts_path)
    assert [p["post_id"] for p in posts] == ["sim_post_1", "sim_post_2"]


def test_fake_missing_file_is_empty(tmp_path):
    f = FakeThreadsService(mentions_path=tmp_path / "missing.json")
    assert f.available is True
    assert f.get_mentions(None) == []
    assert f.get_profile() == {}


def test_fake_example_file_matches_fixture_subset():
    example = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert example["bot"]["username"] == "factcheck_tw_bot"
    ex_ids = [m["id"] for m in example["mentions"]]
    assert ex_ids == ["m1", "m2", "m3"]
    fx_by_id = {m["id"]: m for m in fixture["mentions"]}
    for m in example["mentions"]:
        assert fx_by_id[m["id"]] == m
    for pid, post in example["posts"].items():
        assert fixture["posts"][pid] == post


def test_fake_factory_by_mode(monkeypatch, tmp_path):
    monkeypatch.setattr(ts, "TOKEN_PATH", tmp_path / "no_token.json")
    monkeypatch.setattr(settings, "ENABLE_THREADS_BOT", False)

    monkeypatch.setattr(settings, "THREADS_MODE", "off")
    assert get_threads_client() is None

    monkeypatch.setattr(settings, "THREADS_MODE", "sim")
    assert isinstance(get_threads_client(), FakeThreadsService)

    monkeypatch.setattr(settings, "THREADS_MODE", "live")
    live = get_threads_client()
    assert isinstance(live, ThreadsService)
    assert isinstance(live, ThreadsClient)


def test_fake_error_classes_compatible():
    e = ThreadsAPIError("boom", status_code=401, body="x")
    assert isinstance(e, ThreadsApiError)
    assert e.status == 401 and e.status_code == 401 and e.body == "x"
    e2 = ThreadsApiError(429, {"error": {}})
    assert e2.status_code == 429


# ══════════════════════════════════════════════════════════════════
# T-08：handle_mention／resolve_target（spec §7.5）
# ══════════════════════════════════════════════════════════════════
BASE = "https://factcheck-demo.vercel.app"
RED, YELLOW = "\U0001F534", "\U0001F7E1"
TIER1_URL = "https://www.mygopen.com/2026/09/nhi-card-rumor.html"
P100_TEXT = "健保卡即日起停用！請點 https://nhi-verify.xyz 重新驗證，逾期停卡"

AI_SCAM = {
    "is_risk": True, "risk_type": "SCAM", "category": "Phishing", "confidence_score": 0.93,
    "summary": "假冒健保署的釣魚簡訊，點連結會被騙取個資", "explanation": "健保署不會以簡訊要求重新驗證。",
    "sources": [{"title": "MyGoPen：健保卡停用是假的", "url": TIER1_URL}],
}
AI_FALLBACK = {
    "is_risk": False, "risk_type": "SAFE", "category": "Irrelevant", "confidence_score": 0.0,
    "summary": "AI 分析暫時無法使用（額度用盡）", "explanation": "AI 服務暫時無法使用", "sources": [],
}


class SimulatedCrash(BaseException):
    """模擬行程在處理中途被砍（不被 except Exception 吞掉）。"""


class FakeAI:
    """取代 process_analysis_task_async：記錄呼叫、以真的 _build_result 組結果並完成任務。"""

    def __init__(self, store):
        self.store = store
        self.calls = []
        self.analysis = AI_SCAM
        self.cache_layer = "hash"
        self.crash_on_call = None

    async def __call__(self, task_id, input_data, input_type):
        self.calls.append({"task_id": task_id, "input_data": input_data, "input_type": input_type})
        if self.crash_on_call == len(self.calls):
            raise SimulatedCrash(f"crash while analysing call #{len(self.calls)}")
        result = proc._build_result(
            dict(self.analysis), cached=self.cache_layer is not None,
            cache_layer=self.cache_layer, result_id=task_id,
        )
        proc._complete(self.store, task_id, result)
        return result


class SpyThreadsService(FakeThreadsService):
    """記錄每次 get_mentions 收到的 since（驗證游標與 120 秒重疊）。"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.since_calls = []

    def get_mentions(self, since=None, after_cursor=None):
        self.since_calls.append(since)
        return super().get_mentions(since, after_cursor)


@pytest.fixture
def bot(tmp_path, monkeypatch):
    data = tmp_path / "data"
    mentions = data / "threads_sim" / "mentions.json"
    mentions.parent.mkdir(parents=True)
    shutil.copy(FIXTURE, mentions)
    monkeypatch.setattr(settings, "THREADS_MODE", "sim")
    monkeypatch.setattr(settings, "PUBLIC_BASE_URL", BASE + "/")
    monkeypatch.setattr(settings, "BOT_HANDLE", "factcheck_tw_bot")
    monkeypatch.setattr(settings, "THREADS_MAX_REPLIES_PER_POLL", 50)
    monkeypatch.setattr(settings, "THREADS_MAX_REPLIES_PER_DAY", 50)
    store = TaskStore(data_dir=str(data))
    ai = FakeAI(store)
    monkeypatch.setattr(proc, "process_analysis_task_async", ai)
    return SimpleNamespace(
        data=data, mentions_path=mentions, client=SpyThreadsService(mentions_path=mentions),
        ai=ai, store=store,
    )


def _poll(bot, client=None):
    return asyncio.run(threads_bot.run_threads_poll(client=client or bot.client, data_dir=bot.data))


def _set_mentions(bot, mentions, posts=None):
    data = json.loads(bot.mentions_path.read_text(encoding="utf-8"))
    by_id = {m["id"]: m for m in data["mentions"]}
    data["mentions"] = [by_id[m] if isinstance(m, str) else m for m in mentions]
    data["posts"].update(posts or {})
    bot.mentions_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def _mention(mid, replied_to=None, text="@factcheck_tw_bot 這真的嗎", ts="2026-09-14T09:00:00+0000", **kw):
    m = {"id": mid, "username": kw.pop("username", "tester_x"), "text": text, "media_type": "TEXT_POST",
         "timestamp": ts, "permalink": f"https://www.threads.com/@tester_x/post/{mid}", **kw}
    if replied_to:
        m["replied_to"] = {"id": replied_to}
    return m


def _sim_replies(bot):
    path = bot.client.replies_path
    return _read_lines(path) if path.exists() else []


def _records(bot):
    return threads_state.read_reply_records(None, bot.data)[::-1]   # 時間順


def _state(bot):
    return threads_state.load_state(bot.data)


def test_bot_text_mention_reply_has_result_link_and_state(bot):
    _set_mentions(bot, ["m1"])
    out = _poll(bot)
    assert out["started"] is True
    assert (out["checked"], out["replied"], out["skipped"], out["errors"]) == (1, 1, 0, 0)

    # 送進 AI 的是原貼文 p100，不是 mention 的「@bot 這真的嗎」
    assert len(bot.ai.calls) == 1
    call = bot.ai.calls[0]
    assert call["input_data"] == P100_TEXT and call["input_type"] == "text"
    task_id = call["task_id"]

    [line] = _sim_replies(bot)
    reply = line["text"]
    lines = reply.split("\n")
    assert lines[0] == RED + " 詐騙警告"
    assert f"完整判讀：{BASE}/r/{task_id}" in lines
    assert f"查核來源：{TIER1_URL}" in lines
    assert "/r/" in reply and threads_len(reply) <= 400
    assert line["mention_id"] == "m1" and line["reply_id"] == "sim_reply_1"
    assert line["result_id"] == task_id

    [rec] = _records(bot)
    assert rec["mention_id"] == "m1" and rec["mode"] == "sim" and rec["result_id"] == task_id
    assert rec["frame_type"] == "red" and rec["risk_type"] == "SCAM"
    assert rec["reply_id"] == "sim_reply_1" and rec["reply_text"] == reply
    # 記錄描述「被查核的原貼文」（/bot 頁的原貼文摘要與外連）
    assert rec["username"] == "tester_a"
    assert rec["permalink"] == "https://www.threads.com/@tester_a/post/p100"
    assert rec["source_text_preview"] == P100_TEXT

    task = bot.store.get_task(task_id)
    assert task["origin"] == "threads_sim" and task["task_type"] == "threads_mention"
    assert task["threads_mention_id"] == "m1" and task["threads_reply_id"] == "sim_reply_1"
    assert json.loads(task["platform_post"]) == {
        "platform": "threads", "post_id": "p100",
        "permalink": "https://www.threads.com/@tester_a/post/p100", "username": "tester_a",
    }

    st = _state(bot)
    assert st["replied_ids"] == ["m1"]
    assert st["daily"]["replies"] == 1
    assert st["last_stats"] == {"checked": 1, "replied": 1, "skipped": 0, "errors": 0}
    assert st["last_poll_at"] and st["last_error"] is None


def test_bot_image_post_gets_media_only_reply(bot):
    _set_mentions(bot, ["m2"])
    out = _poll(bot)
    assert out["replied"] == 1
    assert bot.ai.calls == []
    [line] = _sim_replies(bot)
    assert line["text"] == reply_media_only() and line["mention_id"] == "m2"
    [rec] = _records(bot)
    assert rec["frame_type"] == "yellow" and rec["result_id"] is None and rec["risk_type"] is None
    assert rec["username"] == "tester_c"
    st = _state(bot)
    assert st["replied_ids"] == ["m2"]
    assert st["daily"]["replies"] == 0          # 固定文案不經 AI，不計入每日判定回覆數


def test_bot_unreadable_403_replies_cannot_read_and_never_sends_request_to_ai(bot):
    _set_mentions(bot, ["m3"])
    out = _poll(bot)
    assert out["replied"] == 1
    assert bot.ai.calls == []                 # 絕不把「@bot 幫我查」送進 AI
    [line] = _sim_replies(bot)
    assert line["text"] == reply_cannot_read()
    assert _state(bot)["replied_ids"] == ["m3"]
    [rec] = _records(bot)
    assert rec["username"] is None and rec["permalink"] is None and rec["source_text_preview"] is None


def test_bot_too_short_mention_replies_too_short(bot):
    _set_mentions(bot, ["m4"])
    out = _poll(bot)
    assert out["replied"] == 1 and bot.ai.calls == []
    [line] = _sim_replies(bot)
    assert line["text"] == reply_too_short()
    assert _state(bot)["replied_ids"] == ["m4"]


def test_bot_self_post_by_author_is_skipped_and_marked(bot):
    _set_mentions(bot, ["m5"])       # m5 回覆 p105，p105 作者是機器人
    out = _poll(bot)
    assert (out["replied"], out["skipped"]) == (0, 1)
    assert bot.ai.calls == [] and _sim_replies(bot) == [] and _records(bot) == []
    assert _state(bot)["replied_ids"] == ["m5"]


def test_bot_self_reply_id_from_local_records_skipped_without_api_call(bot, monkeypatch):
    _set_mentions(bot, ["m1"])
    _poll(bot)                                   # 機器人回覆 m1 → sim_reply_1 寫進 jsonl
    assert [r["reply_id"] for r in _records(bot)] == ["sim_reply_1"]

    # 有人回覆機器人的判定貼文（sim_reply_1）再 @ 它
    _set_mentions(bot, ["m1", _mention("m9", replied_to="sim_reply_1", ts="2026-09-14T08:30:00+0000")])

    def no_get_post(media_id):
        raise AssertionError(f"get_post must not be called for own reply {media_id}")

    monkeypatch.setattr(bot.client, "get_post", no_get_post)
    out = _poll(bot)
    assert (out["replied"], out["skipped"]) == (0, 1)
    assert len(bot.ai.calls) == 1                # 沒有再跑 AI
    assert len(_sim_replies(bot)) == 1
    assert _state(bot)["replied_ids"] == ["m1", "m9"]


def test_bot_ai_fallback_no_reply_no_mark_then_backfilled(bot):
    # m1（文字）→ AI 不可用；m7（文字）本輪不再送 AI；m2（圖片）照常回固定文案
    _set_mentions(bot, [
        "m1", _mention("m7", replied_to="p106", ts="2026-09-14T08:01:00+0000"), "m2",
    ])
    bot.ai.analysis = AI_FALLBACK
    out = _poll(bot)
    assert (out["checked"], out["replied"], out["skipped"], out["errors"]) == (3, 1, 2, 0)
    assert len(bot.ai.calls) == 1
    assert [x["mention_id"] for x in _sim_replies(bot)] == ["m2"]
    assert all(r["mention_id"] != "m1" for r in _records(bot))
    st = _state(bot)
    assert st["replied_ids"] == ["m2"]
    assert st["daily"]["replies"] == 0
    assert st["last_error"] == "ai_unavailable"

    # AI 恢復：下輪補回 m1、m7，m2 不重複
    bot.ai.analysis = AI_SCAM
    out = _poll(bot)
    assert (out["replied"], out["errors"]) == (2, 0)
    ids = [x["mention_id"] for x in _sim_replies(bot)]
    assert sorted(ids) == ["m1", "m2", "m7"]
    assert _state(bot)["last_error"] is None


def test_bot_crash_on_second_mention_keeps_first_in_state(bot):
    _set_mentions(bot, ["m1", _mention("m7", replied_to="p106", ts="2026-09-14T08:01:00+0000")])
    bot.ai.crash_on_call = 2
    with pytest.raises(SimulatedCrash):
        _poll(bot)
    # crash 也要釋放兩層鎖，否則下一輪會被擋 15 分鐘
    assert not threads_bot.lock_path(bot.data).exists()
    assert not threads_bot._POLL_LOCK.locked()

    # 第 1 則在 crash 前已原子寫入 state 與紀錄
    st = _state(bot)
    assert st["replied_ids"] == ["m1"]
    assert [x["mention_id"] for x in _sim_replies(bot)] == ["m1"]
    assert [r["mention_id"] for r in _records(bot)] == ["m1"]

    # 重啟後再跑：m1 不重複回覆、m7 補上
    bot.ai.crash_on_call = None
    out = _poll(bot)
    assert out["replied"] == 1
    counts = Counter(x["mention_id"] for x in _sim_replies(bot))
    assert counts == {"m1": 1, "m7": 1}


def test_bot_crash_after_reply_before_bookkeeping_does_not_double_reply(bot, monkeypatch):
    """reply_to 成功後、寫 jsonl 前被砍：state 必須已先寫入，重跑不可再回一次。"""
    _set_mentions(bot, ["m1"])
    real_append = threads_state.append_reply_record

    def killed(*_args, **_kwargs):
        raise SimulatedCrash("killed after reply_to, before threads_replies.jsonl")

    monkeypatch.setattr(threads_state, "append_reply_record", killed)
    with pytest.raises(SimulatedCrash):
        _poll(bot)
    assert [x["mention_id"] for x in _sim_replies(bot)] == ["m1"]    # 回覆已送出
    assert _state(bot)["replied_ids"] == ["m1"]                      # 且已先記住

    monkeypatch.setattr(threads_state, "append_reply_record", real_append)
    out = _poll(bot)
    assert out["replied"] == 0
    assert [x["mention_id"] for x in _sim_replies(bot)] == ["m1"]


def test_bot_reply_to_error_is_not_marked_nor_recorded(bot):
    _set_mentions(bot, ["m6"])           # m6：reply_to 注入 HTTP 429
    out = _poll(bot)
    assert (out["replied"], out["errors"]) == (0, 1)
    assert len(bot.ai.calls) == 1
    assert _sim_replies(bot) == [] and _records(bot) == []
    st = _state(bot)
    assert st["replied_ids"] == [] and st["daily"]["replies"] == 0
    assert bot.store.get_task(bot.ai.calls[0]["task_id"])["threads_reply_id"] is None


def test_bot_get_post_5xx_is_not_marked_and_retried_next_poll(bot):
    text = "網傳吃香蕉配優格會中毒，腸胃不好的人千萬不要一起吃"
    _set_mentions(bot, [_mention("m11", replied_to="p300")], posts={
        "p300": {"id": "p300", "username": "tester_a", "media_type": "TEXT_POST", "text": text,
                 "permalink": "https://www.threads.com/@tester_a/post/p300",
                 "_sim_error": {"on": "get_post", "http": 503}},
    })
    out = _poll(bot)
    assert (out["replied"], out["skipped"], out["errors"]) == (0, 0, 1)
    assert bot.ai.calls == [] and _sim_replies(bot) == [] and _records(bot) == []
    assert _state(bot)["replied_ids"] == []

    # 暫時性錯誤排除後，下輪補回（不是回「讀不到」）
    data = json.loads(bot.mentions_path.read_text(encoding="utf-8"))
    del data["posts"]["p300"]["_sim_error"]
    bot.mentions_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    out = _poll(bot)
    assert out["replied"] == 1
    assert [c["input_data"] for c in bot.ai.calls] == [text]
    [line] = _sim_replies(bot)
    assert line["mention_id"] == "m11" and line["text"].startswith(RED)


def test_bot_url_only_post_goes_through_url_input(bot):
    url = "https://nhi-verify.xyz/login?id=1"
    _set_mentions(bot, [_mention("m10", replied_to="p200")], posts={
        "p200": {"id": "p200", "username": "tester_a", "media_type": "TEXT_POST",
                 "text": f"看這個 {url}。", "permalink": "https://www.threads.com/@tester_a/post/p200"},
    })
    out = _poll(bot)
    assert out["replied"] == 1
    [call] = bot.ai.calls
    assert call["input_type"] == "url" and call["input_data"] == url
    assert bot.store.get_task(call["task_id"])["input_type"] == "url"


def test_bot_full_fixture_one_poll(bot):
    out = _poll(bot)
    # m1 判定、m2 圖片、m3 讀不到、m4 太短 → 回覆；m5 自我 → 略過；m6 reply_to 429 → 錯誤
    assert (out["checked"], out["replied"], out["skipped"], out["errors"]) == (6, 4, 1, 1)
    texts = {x["mention_id"]: x["text"] for x in _sim_replies(bot)}
    assert set(texts) == {"m1", "m2", "m3", "m4"}
    assert texts["m2"] == reply_media_only()
    assert texts["m3"] == reply_cannot_read()
    assert texts["m4"] == reply_too_short()
    assert texts["m1"].startswith(RED)
    assert [c["input_data"] for c in bot.ai.calls] == [
        P100_TEXT, "轉發此訊息給十個群組，就能領取超商禮券一千元，今天截止",
    ]
    assert sorted(_state(bot)["replied_ids"]) == ["m1", "m2", "m3", "m4", "m5"]


def test_bot_logs_one_structured_line_per_mention_cp950_safe(bot, caplog):
    _set_mentions(bot, ["m1", "m2"])
    with caplog.at_level(logging.INFO, logger="threads_bot"):
        _poll(bot)
    recs = [r for r in caplog.records if r.name == "threads_bot"]
    assert recs
    lines = [json.loads(r.getMessage()[len("mention "):]) for r in recs if r.getMessage().startswith("mention ")]
    assert [x["mention_id"] for x in lines] == ["m1", "m2"]
    m1 = lines[0]
    assert set(m1) >= {"mention_id", "kind", "result_id", "cache_layer", "elapsed_ms"}
    assert m1["kind"] == "text" and m1["cache_layer"] == "hash"
    assert m1["result_id"] == bot.ai.calls[0]["task_id"]
    assert isinstance(m1["elapsed_ms"], int) and m1["elapsed_ms"] >= 0
    assert lines[1]["kind"] == "media_only" and lines[1]["result_id"] is None
    # 所有 threads_bot 日誌在 cp950 主控台都印得出來（emoji 已跳脫），回覆文字以 repr 記錄
    for r in recs:
        r.getMessage().encode("cp950")
    assert any("\\U0001f534" in r.getMessage() for r in recs)


def test_strip_mentions_keeps_text_and_emails():
    assert threads_bot.strip_mentions("@factcheck_tw_bot 這真的嗎") == "這真的嗎"
    assert threads_bot.strip_mentions("@factcheck_tw_bot這真的嗎") == "這真的嗎"
    assert threads_bot.strip_mentions("網傳 @factcheck_tw_bot 健保卡\n停用") == "網傳 健保卡\n停用"
    assert threads_bot.strip_mentions("寄信到 abc@gmail.com 查詢") == "寄信到 abc@gmail.com 查詢"
    assert threads_bot.strip_mentions(None) == ""


class StubClient:
    def __init__(self, post=None, error=None):
        self.post, self.error, self.calls = post, error, []

    def get_post(self, media_id):
        self.calls.append(media_id)
        if self.error is not None:
            raise self.error
        return dict(self.post, id=media_id)


def _post(text, media_type="TEXT_POST", username="tester_a"):
    return {"username": username, "text": text, "media_type": media_type,
            "permalink": "https://www.threads.com/@tester_a/post/p1"}


LONG = "網傳吃香蕉配優格會中毒，腸胃不好的人千萬不要一起吃"


@pytest.mark.parametrize("client, mention, expected", [
    (StubClient(error=ThreadsApiError(404)), {"replied_to": {"id": "p1"}}, ("unreadable", None, "text")),
    (StubClient(error=ThreadsApiError(403)), {"replied_to": {"id": "p1"}}, ("unreadable", None, "text")),
    (StubClient(error=ThreadsApiError(401)), {"replied_to": {"id": "p1"}}, ("unreadable", None, "text")),
    # T-13（2026-09-19，spec §7.5 已與 §7.10／FN-4 統一）：未列入的 4xx 不再回「讀不到」，改標 failed、不回覆
    (StubClient(error=ThreadsApiError(400)), {"replied_to": "p1"}, ("failed", None, "text")),
    (StubClient(error=ThreadsApiError(409)), {"replied_to": {"id": "p1"}}, ("failed", None, "text")),
    (StubClient(error=ThreadsApiError(422)), {"replied_to": {"id": "p1"}}, ("failed", None, "text")),
    (StubClient(error=ThreadsApiError(499)), {"replied_to": {"id": "p1"}}, ("failed", None, "text")),
    (StubClient(error=ThreadsApiError(429)), {"replied_to": {"id": "p1"}}, ("transient", None, "text")),
    (StubClient(error=ThreadsApiError(500)), {"replied_to": {"id": "p1"}}, ("transient", None, "text")),
    (StubClient(error=ThreadsApiError(503)), {"replied_to": {"id": "p1"}}, ("transient", None, "text")),
    (StubClient(error=ThreadsApiError(None)), {"replied_to": {"id": "p1"}}, ("transient", None, "text")),
    (StubClient(error=RuntimeError("boom")), {"replied_to": {"id": "p1"}}, ("transient", None, "text")),
    (StubClient(_post("", "IMAGE")), {"replied_to": {"id": "p1"}}, ("media_only", None, "text")),
    (StubClient(_post("@factcheck_tw_bot 看", "VIDEO")), {"replied_to": {"id": "p1"}}, ("media_only", None, "text")),
    (StubClient(_post(LONG, "CAROUSEL_ALBUM")), {"replied_to": {"id": "p1"}}, ("text", LONG, "text")),
    # 短文字貼文：不論 media_type 是 TEXT／TEXT_POST 都是太短，不是圖片
    (StubClient(_post("好扯", "TEXT")), {"replied_to": {"id": "p1"}}, ("too_short", None, "text")),
    (StubClient(_post("好扯", "TEXT_POST")), {"replied_to": {"id": "p1"}}, ("too_short", None, "text")),
    (StubClient(_post(LONG, "TEXT", username="FactCheck_TW_Bot")), {"replied_to": {"id": "p1"}},
     ("self", None, "text")),
    (StubClient(_post("https://nhi-verify.xyz/a?b=1")), {"replied_to": {"id": "p1"}},
     ("text", "https://nhi-verify.xyz/a?b=1", "url")),
    (StubClient(_post("HTTPS://Nhi-Verify.xyz/a 快看")), {"replied_to": {"id": "p1"}},
     ("text", "https://Nhi-Verify.xyz/a", "url")),
    (StubClient(_post(P100_TEXT)), {"replied_to": {"id": "p1"}}, ("text", P100_TEXT, "text")),
    (StubClient(), {"text": "@factcheck_tw_bot " + LONG}, ("text", LONG, "text")),
    (StubClient(), {"text": "@factcheck_tw_bot 幫我查"}, ("too_short", None, "text")),
], ids=[
    "404", "403", "401", "400_scalar_replied_to", "409", "422", "499", "429", "500", "503", "no_status",
    "exception",
    "image", "video_short", "carousel_long", "short_TEXT", "short_TEXT_POST", "bot_author",
    "url_only", "url_short_text", "text_with_url", "standalone_long", "standalone_short",
])
def test_resolve_target_table(client, mention, expected, monkeypatch):
    monkeypatch.setattr(settings, "BOT_HANDLE", "factcheck_tw_bot")
    m = dict({"id": "m1", "username": "tester_b"}, **mention)
    kind, text, input_type, target = asyncio.run(
        threads_bot.resolve_target(client, m, own_ids=set())
    )
    assert (kind, text, input_type) == expected
    if "replied_to" in mention:
        assert client.calls == ["p1"] and target["id"] == "p1"
    else:
        assert client.calls == [] and target["username"] == "tester_b"
    if kind in ("failed", "transient"):
        # 分流依據：HTTP 狀態碼隨 target 帶回（429 → backoff；拿不到狀態碼 → None）
        assert target["error_status"] == getattr(client.error, "status", None)
    else:
        assert "error_status" not in target


def test_threads_bot_has_no_print_calls():
    source = Path(threads_bot.__file__).read_text(encoding="utf-8")
    assert re.search(r"print\(", source) is None


# ══════════════════════════════════════════════════════════════════
# T-09：run_threads_poll 互斥鎖、since 游標、本地上限（spec §7.4）
# ══════════════════════════════════════════════════════════════════
def _epoch(iso):
    return int(datetime.fromisoformat(iso).replace(tzinfo=timezone.utc).timestamp())


TS_M1 = _epoch("2026-09-14T08:00:00")
TS_M4 = _epoch("2026-09-14T08:15:00")
TS_M6 = _epoch("2026-09-14T08:25:00")
RUMOR_A = "轉發此訊息給十個群組，就能領取超商禮券一千元，今天截止"
RUMOR_B = "網傳吃香蕉配優格會中毒，腸胃不好的人千萬不要一起吃"


def _write_state(bot, **fields):
    st = threads_state.load_state(bot.data)
    st.update(fields)
    threads_state.save_state(st, bot.data)


def _expire_backoff(bot):
    """模擬 backoff 時間已過（只改 backoff_until；backoff_n／transient_n 等其他欄位不動）。"""
    _write_state(bot, backoff_until=(datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat())


def _text_mentions(*ids_and_times):
    """獨立 @ 貼文（無 replied_to），文字夠長 → 都走 AI。"""
    return [_mention(mid, text=f"@factcheck_tw_bot {RUMOR_B} #{mid}", ts=ts) for mid, ts in ids_and_times]


def _expired_token_file(tmp_path):
    now = datetime.now(timezone.utc)
    p = tmp_path / "threads_token.json"
    p.write_text(json.dumps({
        "access_token": "EXPIRED_TOKEN", "user_id": "bot-user",
        "obtained_at": (now - timedelta(days=61)).isoformat(),
        "expires_at": (now - timedelta(hours=1)).isoformat(),
        "authorized_at": (now - timedelta(days=61)).isoformat(),
    }), encoding="utf-8")
    return p


@pytest.mark.parametrize("via", ["factory", "injected"])
def test_poll_expired_token_reports_token_invalid_without_network(tmp_path, monkeypatch, via):
    data = tmp_path / "data"
    token = _expired_token_file(tmp_path)
    monkeypatch.setattr(settings, "THREADS_MODE", "live")
    monkeypatch.setattr(ts, "TOKEN_PATH", token)
    client = None if via == "factory" else ThreadsService(token_path=token)

    out = asyncio.run(threads_bot.run_threads_poll(client=client, data_dir=data))
    assert out == {"started": False, "reason": "token_invalid"}
    st = threads_state.load_state(data)
    assert st["last_error"] == "token_invalid"
    assert st["last_poll_at"] is None and st["replied_ids"] == []


def test_poll_mode_off_does_not_start(bot, monkeypatch):
    monkeypatch.setattr(settings, "THREADS_MODE", "off")
    out = _poll(bot)
    assert out == {"started": False, "reason": "threads_disabled"}
    assert bot.client.since_calls == [] and bot.ai.calls == []
    assert not threads_state.state_path(bot.data).exists()


def test_poll_unavailable_client_does_not_start(bot, monkeypatch):
    monkeypatch.setattr(settings, "THREADS_MODE", "live")
    monkeypatch.setattr(settings, "THREADS_ACCESS_TOKEN", "")
    monkeypatch.setattr(ts, "TOKEN_PATH", bot.data / "no_token.json")
    out = asyncio.run(threads_bot.run_threads_poll(data_dir=bot.data))
    assert out == {"started": False, "reason": "client_unavailable"}
    assert _state(bot)["last_error"] is None


def test_poll_backoff_skips_without_api_call(bot):
    _set_mentions(bot, ["m1"])
    future = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()
    _write_state(bot, backoff_until=future)
    out = _poll(bot)
    assert out["started"] is False and out["skipped"] == "backoff"
    assert bot.client.since_calls == [] and bot.ai.calls == []

    _write_state(bot, backoff_until=(datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat())
    assert _poll(bot)["replied"] == 1


def test_poll_same_fixture_twice_second_run_replies_nothing(bot):
    first = _poll(bot)
    assert first["replied"] == 4
    lines_after_first = len(_sim_replies(bot))

    # T-13：m6 的 reply_to 429 讓第一輪設了 backoff_until，緊接著的 poll 會整輪略過（也不會重複回覆）；
    # 「第二次 poll」要等 backoff 到期才真的跑，這裡直接把它改成已到期
    skipped = _poll(bot)
    assert skipped["started"] is False and skipped["skipped"] == "backoff"
    assert len(_sim_replies(bot)) == lines_after_first
    _expire_backoff(bot)

    second = _poll(bot)
    assert second["started"] is True and second["replied"] == 0
    assert len(_sim_replies(bot)) == lines_after_first
    counts = Counter(x["mention_id"] for x in _sim_replies(bot))
    assert all(n == 1 for n in counts.values())
    # 只有 reply_to 失敗的 m6 被重試（仍失敗、仍不標記）
    assert second["errors"] == 1 and "m6" not in _state(bot)["replied_ids"]


def test_poll_since_floor_then_advances_with_120s_overlap(bot):
    _set_mentions(bot, ["m1", "m2", "m4"])          # 全部可處理完：文字、圖片、太短
    assert _poll(bot)["replied"] == 3
    assert bot.client.since_calls == [threads_bot.SINCE_FLOOR]
    assert _state(bot)["last_since"] == TS_M4          # = max(timestamp)

    new_ts = "2026-09-14T08:40:00+0000"
    _set_mentions(bot, ["m1", "m2", "m4", _mention("m20", text=f"@factcheck_tw_bot {RUMOR_B}", ts=new_ts)])
    out = _poll(bot)
    assert bot.client.since_calls[-1] == TS_M4 - 120   # 下一輪帶 120 秒重疊
    assert out["replied"] == 1 and out["checked"] == 1  # 重疊區內的 m4 已回覆，直接略過
    assert [x["mention_id"] for x in _sim_replies(bot)][-1] == "m20"
    assert _state(bot)["last_since"] == _epoch("2026-09-14T08:40:00")


def test_poll_no_mentions_sets_last_since_to_now(bot):
    _set_mentions(bot, [])
    before = int(time.time())
    out = _poll(bot)
    after = int(time.time())
    assert out["started"] is True and out["checked"] == 0
    st = _state(bot)
    assert before <= st["last_since"] <= after
    assert st["last_poll_at"] and st["last_stats"] == {"checked": 0, "replied": 0, "skipped": 0, "errors": 0}


def test_poll_cursor_holds_before_mentions_left_for_next_poll(bot):
    """AI 不可用的 m1 在 since 視窗外（> 120 秒）也不能被跳過。"""
    _set_mentions(bot, ["m1", "m4"])        # m1 08:00 走 AI；m4 08:15 太短
    bot.ai.analysis = AI_FALLBACK
    out = _poll(bot)
    assert (out["replied"], out["skipped"]) == (1, 1)
    assert _state(bot)["last_since"] == TS_M1 - 1   # 不是 max = 08:15

    bot.ai.analysis = AI_SCAM
    out = _poll(bot)
    assert bot.client.since_calls[-1] == TS_M1 - 1 - 120
    assert out["replied"] == 1
    assert Counter(x["mention_id"] for x in _sim_replies(bot)) == {"m4": 1, "m1": 1}
    assert _state(bot)["last_since"] == TS_M4


def test_poll_cursor_never_moves_backwards_when_only_overlap_mentions(bot):
    _set_mentions(bot, ["m1"])
    _write_state(bot, last_since=TS_M1 + 60, replied_ids=["m1"])   # m1 在 120 秒重疊區內、已回覆
    out = _poll(bot)
    assert bot.client.since_calls == [TS_M1 + 60 - 120]
    assert out["checked"] == 0
    assert _state(bot)["last_since"] == TS_M1 + 60


def test_poll_cursor_stays_when_pending_mention_has_no_timestamp(bot):
    class NoTimestampClient(SpyThreadsService):
        def get_mentions(self, since=None, after_cursor=None):
            self.since_calls.append(since)
            return [_mention("nt1", text=f"@factcheck_tw_bot {RUMOR_A}", ts=None)]

    _write_state(bot, last_since=TS_M1)
    bot.ai.analysis = AI_FALLBACK
    out = _poll(bot, client=NoTimestampClient(mentions_path=bot.mentions_path))
    assert out["skipped"] == 1
    assert _state(bot)["last_since"] == TS_M1        # 無法定位的待處理 mention → 游標不動


def test_poll_reply_error_holds_cursor(bot):
    out = _poll(bot)                         # 整份 fixture：m6（最晚）reply_to 429
    assert out["errors"] == 1
    assert _state(bot)["last_since"] == TS_M6 - 1


def test_poll_max_replies_per_poll_1_replies_only_one(bot, monkeypatch):
    monkeypatch.setattr(settings, "THREADS_MAX_REPLIES_PER_POLL", 1)
    _set_mentions(bot, _text_mentions(
        ("t1", "2026-09-14T09:00:00+0000"), ("t2", "2026-09-14T09:01:00+0000"),
        ("t3", "2026-09-14T09:02:00+0000"),
    ))
    replied_per_poll = []
    for _ in range(4):
        out = _poll(bot)
        replied_per_poll.append(out["replied"])
    assert replied_per_poll == [1, 1, 1, 0]            # 超過上限的留到下一輪，不會漏掉
    assert [x["mention_id"] for x in _sim_replies(bot)] == ["t1", "t2", "t3"]
    assert len(bot.ai.calls) == 3


def test_poll_cap_stop_is_reported(bot, monkeypatch):
    monkeypatch.setattr(settings, "THREADS_MAX_REPLIES_PER_POLL", 1)
    _set_mentions(bot, _text_mentions(("t1", "2026-09-14T09:00:00+0000"), ("t2", "2026-09-14T09:01:00+0000")))
    out = _poll(bot)
    assert out["stopped"] == "per_poll_cap" and len(bot.ai.calls) == 1
    assert _state(bot)["last_since"] == _epoch("2026-09-14T09:01:00") - 1


def test_poll_cap_counts_analyzed_replies_not_fixed_texts(bot, monkeypatch):
    """上限計的是「經 AI 的判定回覆」（spec §7.5 只在判定路徑累加）：
    demo 週 PER_POLL=2 時範例檔 m1（文字）＋m2（圖片）＋m3（讀不到）一輪就該處理完。"""
    monkeypatch.setattr(settings, "THREADS_MAX_REPLIES_PER_POLL", 2)
    _set_mentions(bot, ["m1", "m2", "m3"])
    first = _poll(bot)
    assert (first["replied"], first["stopped"]) == (3, None)
    assert _poll(bot)["replied"] == 0


def test_poll_daily_cap_stops(bot, monkeypatch):
    _set_mentions(bot, ["m1"])
    monkeypatch.setattr(settings, "THREADS_MAX_REPLIES_PER_DAY", 50)
    _write_state(bot, daily={"date": threads_state.taipei_today(), "replies": 50})
    out = _poll(bot)
    assert (out["replied"], out["stopped"]) == (0, "daily_cap")
    assert bot.ai.calls == []
    assert _state(bot)["last_since"] == TS_M1 - 1

    # 當日上限在輪中達到也要停
    monkeypatch.setattr(settings, "THREADS_MAX_REPLIES_PER_DAY", 1)
    _write_state(bot, daily={"date": threads_state.taipei_today(), "replies": 0})
    _set_mentions(bot, _text_mentions(("t1", "2026-09-14T09:00:00+0000"), ("t2", "2026-09-14T09:01:00+0000")))
    out = _poll(bot)
    assert (out["replied"], out["stopped"]) == (1, "daily_cap")
    assert _state(bot)["daily"]["replies"] == 1


def test_poll_skips_mentions_authored_by_bot(bot):
    _set_mentions(bot, [_mention("mb", text=f"@factcheck_tw_bot {RUMOR_A}", username="FactCheck_TW_Bot")])
    out = _poll(bot)
    assert (out["checked"], out["replied"], out["skipped"]) == (1, 0, 1)
    assert bot.ai.calls == [] and _sim_replies(bot) == []
    st = _state(bot)
    assert st["replied_ids"] == []
    assert st["last_since"] == _epoch("2026-09-14T09:00:00")   # 自己的貼文不擋游標


def test_poll_concurrent_call_raises_poll_in_progress(bot, monkeypatch):
    _set_mentions(bot, ["m1"])
    real_ai = bot.ai

    async def scenario():
        entered, gate = asyncio.Event(), asyncio.Event()

        async def slow_ai(task_id, text, input_type):
            entered.set()
            await gate.wait()
            return await real_ai(task_id, text, input_type)

        monkeypatch.setattr(proc, "process_analysis_task_async", slow_ai)
        first = asyncio.create_task(threads_bot.run_threads_poll(client=bot.client, data_dir=bot.data))
        await entered.wait()
        assert threads_bot._POLL_LOCK.locked()             # 同行程鎖
        assert threads_bot.lock_path(bot.data).exists()   # 跨行程鎖
        assert threads_bot.poll_in_progress(bot.data)
        with pytest.raises(threads_bot.PollInProgress):
            await threads_bot.run_threads_poll(client=bot.client, data_dir=bot.data)
        gate.set()
        return await first

    out = asyncio.run(scenario())
    assert out["replied"] == 1 and len(real_ai.calls) == 1
    assert not threads_bot.lock_path(bot.data).exists()
    assert not threads_bot.poll_in_progress(bot.data)
    assert _poll(bot)["started"] is True             # 鎖已釋放，下一輪照跑


def test_poll_lock_file_held_by_other_process(bot):
    _set_mentions(bot, ["m1"])
    lock = threads_bot.lock_path(bot.data)
    other = {"pid": 999999, "token": "other-process", "created_at": time.time()}
    lock.write_text(json.dumps(other), encoding="utf-8")

    assert threads_bot.poll_in_progress(bot.data)
    with pytest.raises(threads_bot.PollInProgress):
        _poll(bot)
    assert json.loads(lock.read_text(encoding="utf-8"))["token"] == "other-process"   # 不刪別人的鎖
    assert bot.ai.calls == [] and _sim_replies(bot) == []

    # 超過 15 分鐘 → 視為殘留，強制接手
    other["created_at"] = time.time() - threads_bot.LOCK_STALE_SECONDS - 60
    lock.write_text(json.dumps(other), encoding="utf-8")
    assert not threads_bot.poll_in_progress(bot.data)
    assert _poll(bot)["replied"] == 1
    assert not lock.exists()


def test_poll_does_not_delete_lock_taken_over_by_another_poller(bot, monkeypatch):
    """本輪跑超過 15 分鐘被別的行程接手：結束時不可刪掉對方的鎖。"""
    _set_mentions(bot, ["m1"])
    lock = threads_bot.lock_path(bot.data)
    real_ai = bot.ai

    async def taken_over_ai(task_id, text, input_type):
        lock.write_text(json.dumps({"pid": 4242, "token": "new-owner", "created_at": time.time()}),
                        encoding="utf-8")
        return await real_ai(task_id, text, input_type)

    monkeypatch.setattr(proc, "process_analysis_task_async", taken_over_ai)
    assert _poll(bot)["replied"] == 1
    assert json.loads(lock.read_text(encoding="utf-8"))["token"] == "new-owner"
    lock.unlink()


def test_poll_cancelled_mid_poll_releases_lock(bot, monkeypatch):
    _set_mentions(bot, ["m1"])

    async def scenario():
        entered = asyncio.Event()

        async def hang(task_id, text, input_type):
            entered.set()
            await asyncio.sleep(3600)

        monkeypatch.setattr(proc, "process_analysis_task_async", hang)
        task = asyncio.create_task(threads_bot.run_threads_poll(client=bot.client, data_dir=bot.data))
        await entered.wait()
        assert threads_bot.lock_path(bot.data).exists()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(scenario())
    assert not threads_bot.lock_path(bot.data).exists()
    assert _state(bot)["replied_ids"] == [] and _sim_replies(bot) == []


def test_poll_duplicate_mention_in_one_fetch_is_processed_once(bot):
    dup = json.loads(FIXTURE.read_text(encoding="utf-8"))["mentions"][5]   # m6：reply_to 429
    _set_mentions(bot, ["m6", dict(dup)])
    out = _poll(bot)
    assert (out["checked"], out["errors"]) == (1, 1)
    assert len(bot.ai.calls) == 1


def test_poll_lock_file_unreadable_uses_mtime(bot):
    _set_mentions(bot, ["m1"])
    lock = threads_bot.lock_path(bot.data)
    lock.write_text("", encoding="utf-8")                 # 另一行程剛建檔、尚未寫入
    with pytest.raises(threads_bot.PollInProgress):
        _poll(bot)
    old = time.time() - threads_bot.LOCK_STALE_SECONDS - 60
    os.utime(lock, (old, old))
    assert _poll(bot)["replied"] == 1
    assert not lock.exists()


def test_poll_mentions_error_keeps_cursor_and_sets_last_error(bot):
    _set_mentions(bot, ["m1"])
    assert _poll(bot)["replied"] == 1
    since_before = _state(bot)["last_since"]

    data = json.loads(bot.mentions_path.read_text(encoding="utf-8"))
    data["mentions"].append(_mention("m30", text=f"@factcheck_tw_bot {RUMOR_A}", ts="2026-09-14T09:00:00+0000",
                                     _sim_error={"on": "get_mentions", "http": 401}))
    bot.mentions_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    out = _poll(bot)
    assert (out["started"], out["errors"], out["replied"]) == (True, 1, 0)
    st = _state(bot)
    assert st["last_error"] == "token_invalid" and st["last_since"] == since_before
    assert st["last_stats"]["errors"] == 1


# ══════════════════════════════════════════════════════════════════
# T-13：HTTP 狀態碼分流與 backoff（spec §7.10；FN-4「429 → backoff_until」「未知 4xx → 標 failed 不回覆」）
# ══════════════════════════════════════════════════════════════════
LINK_LIMIT_BODY = {"error": {"message": "Too many links", "error_user_title": "THREADS_API__LINK_LIMIT_EXCEEDED"}}


def _edit_mentions(bot, fn):
    data = json.loads(bot.mentions_path.read_text(encoding="utf-8"))
    fn(data)
    bot.mentions_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def _inject(bot, mention_id, **fields):
    """在 mentions.json 的某則 mention 上設定（值為 None 則移除）_sim_error／_sim_container。"""
    def fn(data):
        [m] = [x for x in data["mentions"] if x["id"] == mention_id]
        for key, value in fields.items():
            if value is None:
                m.pop(key, None)
            else:
                m[key] = value

    _edit_mentions(bot, fn)


def _post_of(pid, text=RUMOR_B, **extra):
    return {"id": pid, "username": "tester_a", "media_type": "TEXT_POST", "text": text,
            "permalink": f"https://www.threads.com/@tester_a/post/{pid}", **extra}


def _backoff_minutes_left(bot):
    until = threads_state.parse_until(_state(bot)["backoff_until"])
    assert until is not None, "backoff_until is not set"
    return (until - datetime.now(timezone.utc)).total_seconds() / 60.0


def _assert_backoff(bot, minutes):
    left = _backoff_minutes_left(bot)
    assert minutes - 0.5 <= left <= minutes, f"expected ~{minutes} min of backoff, got {left:.2f}"


@pytest.fixture
def poll5(monkeypatch):
    monkeypatch.setattr(settings, "THREADS_POLL_MINUTES", 5)   # 不依賴本機 .env 的輪詢間隔


@pytest.mark.parametrize("status, expected", [
    (429, "rate_limited"), (401, "token_invalid"),
    (400, "client_error"), (403, "client_error"), (404, "client_error"), (418, "client_error"), (499, "client_error"),
    (500, "transient"), (503, "transient"), (None, "transient"), (200, "transient"), (True, "transient"),
    ("429", "transient"),
])
def test_classify_status_table(status, expected):
    assert threads_bot.classify_status(status) == expected
    assert threads_bot.classify_api_error(ThreadsApiError(status)) == expected
    assert threads_bot.classify_api_error(RuntimeError("no status attribute")) == "transient"


def test_backoff_429_on_reply_sets_backoff_until_and_stops_round(bot, poll5):
    """FN-4：HTTP 429 → backoff_until 設定。429 之後本輪中止，其餘 mention 留待 backoff 之後。"""
    _set_mentions(bot, ["m6", *_text_mentions(("t2", "2026-09-14T09:00:00+0000"))])   # m6：reply_to 429
    out = _poll(bot)
    assert (out["started"], out["checked"], out["replied"], out["errors"]) == (True, 1, 0, 1)
    assert out["stopped"] == "rate_limited"
    assert len(bot.ai.calls) == 1                       # 只有 m6；t2 沒被送進 AI
    assert _sim_replies(bot) == [] and _records(bot) == []
    st = _state(bot)
    assert st["replied_ids"] == [] and st["failed"] == {} and st["pending_publish"] == {}
    assert st["last_error"] == "rate_limited" and st["backoff_n"] == 1
    assert st["last_since"] == TS_M6 - 1                # 游標停在 m6 之前，backoff 後補回
    _assert_backoff(bot, 5)                             # min(60, 5 × 2^0)
    assert threads_state.parse_until(st["backoff_until"]).tzinfo is not None   # UTC ISO（status API 的 iso 字串）


def test_backoff_poll_is_skipped_while_backing_off_without_touching_anything(bot, poll5):
    _set_mentions(bot, ["m6"])
    _poll(bot)
    st = _state(bot)
    since_calls = list(bot.client.since_calls)
    raw_before = threads_state.state_path(bot.data).read_bytes()

    skipped = _poll(bot)
    assert skipped == {
        "started": False, "skipped": "backoff",
        "backoff_until": st["backoff_until"], "last_error": "rate_limited",
    }
    assert bot.client.since_calls == since_calls and len(bot.ai.calls) == 1     # 不打 API、不跑 AI
    assert threads_state.state_path(bot.data).read_bytes() == raw_before       # 也不寫 state
    # 等鎖的空檔才被別的行程設了 backoff：拿到鎖後重讀 state 仍會略過
    inner = asyncio.run(threads_bot._poll_once(bot.client, "sim", bot.data))
    assert inner["started"] is False and inner["skipped"] == "backoff"
    assert bot.client.since_calls == since_calls

    _expire_backoff(bot)
    assert _poll(bot)["started"] is True
    assert len(bot.client.since_calls) == len(since_calls) + 1


def test_backoff_429_on_get_mentions_keeps_cursor(bot, poll5):
    _set_mentions(bot, [_mention("m40", text=f"@factcheck_tw_bot {RUMOR_A}",
                                 _sim_error={"on": "get_mentions", "http": 429})])
    _write_state(bot, last_since=TS_M1)
    out = _poll(bot)
    assert (out["started"], out["checked"], out["errors"], out["stopped"]) == (True, 0, 1, "rate_limited")
    st = _state(bot)
    assert st["last_error"] == "rate_limited" and st["backoff_n"] == 1 and st["last_since"] == TS_M1
    assert st["last_stats"] == {"checked": 0, "replied": 0, "skipped": 0, "errors": 1}
    _assert_backoff(bot, 5)
    assert bot.ai.calls == []


def test_backoff_429_on_get_post_does_not_mark_or_reply_and_is_backfilled(bot, poll5):
    _set_mentions(bot, ["m2", _mention("m41", replied_to="p410")], posts={
        "p410": _post_of("p410", _sim_error={"on": "get_post", "http": 429}),
    })
    out = _poll(bot)
    # m2（圖片）照常回固定文案；m41 讀原貼文 429 → 不回覆、不標記、本輪中止
    assert (out["checked"], out["replied"], out["errors"], out["stopped"]) == (2, 1, 1, "rate_limited")
    assert [x["mention_id"] for x in _sim_replies(bot)] == ["m2"] and bot.ai.calls == []
    st = _state(bot)
    assert st["replied_ids"] == ["m2"] and st["failed"] == {}
    _assert_backoff(bot, 5)

    _edit_mentions(bot, lambda data: data["posts"]["p410"].pop("_sim_error"))
    _expire_backoff(bot)
    out = _poll(bot)
    assert (out["replied"], out["errors"], out["stopped"]) == (1, 0, None)
    assert Counter(x["mention_id"] for x in _sim_replies(bot)) == {"m2": 1, "m41": 1}


@pytest.mark.parametrize("poll_minutes, expected", [
    (5, [5, 10, 20, 40, 60, 60, 60]),
    (1, [1, 2, 4, 8, 16, 32, 60, 60]),
])
def test_backoff_doubles_on_consecutive_429_and_caps_at_60_minutes(bot, monkeypatch, poll_minutes, expected):
    """backoff_until = now + min(60, poll_interval × 2^n) 分鐘，n 隨連續 429 次數遞增。"""
    monkeypatch.setattr(settings, "THREADS_POLL_MINUTES", poll_minutes)
    # 太短的 mention → 固定文案回覆（不經 AI、不寫任務檔，迴圈跑得快），回覆時被 429
    _set_mentions(bot, [_mention("m60", text="@factcheck_tw_bot 查", _sim_error={"on": "reply_to", "http": 429})])
    for n, minutes in enumerate(expected, 1):
        out = _poll(bot)
        assert out["started"] is True and out["stopped"] == "rate_limited"
        assert _state(bot)["backoff_n"] == n
        _assert_backoff(bot, minutes)
        _expire_backoff(bot)
    assert _sim_replies(bot) == [] and _state(bot)["replied_ids"] == []


def test_backoff_resets_after_a_successful_round(bot, poll5):
    _set_mentions(bot, ["m6"])
    _poll(bot)
    _expire_backoff(bot)
    _poll(bot)
    assert _state(bot)["backoff_n"] == 2
    _assert_backoff(bot, 10)

    _inject(bot, "m6", _sim_error=None)          # 限流解除
    _expire_backoff(bot)
    out = _poll(bot)
    assert (out["replied"], out["errors"], out["stopped"]) == (1, 0, None)
    st = _state(bot)
    assert st["backoff_n"] == 0 and st["backoff_until"] is None and st["last_error"] is None
    assert st["replied_ids"] == ["m6"]

    # 歸零後再遇 429：從 poll_interval × 2^0 重新算起，不是接著 20 分鐘
    _set_mentions(bot, ["m6", _mention("m50", text=f"@factcheck_tw_bot {RUMOR_A}", ts="2026-09-14T09:30:00+0000",
                                       _sim_error={"on": "reply_to", "http": 429})])
    assert _poll(bot)["stopped"] == "rate_limited"
    assert _state(bot)["backoff_n"] == 1
    _assert_backoff(bot, 5)
    assert Counter(x["mention_id"] for x in _sim_replies(bot)) == {"m6": 1}     # 沒有重複回覆


def test_backoff_n_is_kept_when_the_next_round_fails_for_another_reason(bot, poll5):
    """「成功後歸零」：中間那輪 mentions 讀取 5xx 不算成功，連續次數不歸零。"""
    _set_mentions(bot, ["m6"])
    _poll(bot)
    _expire_backoff(bot)
    _inject(bot, "m6", _sim_error={"on": "get_mentions", "http": 502})
    out = _poll(bot)
    assert out["errors"] == 1 and out["stopped"] is None
    st = _state(bot)
    assert st["backoff_n"] == 1 and st["backoff_until"] is None and st["last_error"] == "mentions_failed"


def test_backoff_401_on_get_mentions_is_token_invalid_for_60_minutes(bot, poll5):
    _set_mentions(bot, [_mention("m42", text=f"@factcheck_tw_bot {RUMOR_A}",
                                 _sim_error={"on": "get_mentions", "http": 401})])
    out = _poll(bot)
    assert (out["started"], out["errors"], out["stopped"]) == (True, 1, "token_invalid")
    st = _state(bot)
    assert st["last_error"] == "token_invalid" and st["backoff_n"] == 0
    _assert_backoff(bot, 60)
    assert _poll(bot)["skipped"] == "backoff" and bot.ai.calls == []


def test_backoff_401_on_reply_keeps_the_mention_for_after_reauth(bot, poll5):
    _set_mentions(bot, [_mention("m43", text=f"@factcheck_tw_bot {RUMOR_A}",
                                 _sim_error={"on": "reply_to", "http": 401})])
    out = _poll(bot)
    assert (out["replied"], out["errors"], out["stopped"]) == (0, 1, "token_invalid")
    st = _state(bot)
    assert st["replied_ids"] == [] and st["failed"] == {}       # token 的問題不算在這則 mention 頭上
    assert st["last_error"] == "token_invalid"
    _assert_backoff(bot, 60)

    _inject(bot, "m43", _sim_error=None)
    _expire_backoff(bot)
    assert _poll(bot)["replied"] == 1


def test_backoff_403_on_get_mentions_is_permission_denied_without_backoff(bot, poll5):
    _set_mentions(bot, [_mention("m44", text=f"@factcheck_tw_bot {RUMOR_A}",
                                 _sim_error={"on": "get_mentions", "http": 403})])
    out = _poll(bot)
    assert (out["started"], out["errors"], out["stopped"]) == (True, 1, None)
    st = _state(bot)
    assert st["last_error"] == "permission_denied" and st["backoff_until"] is None and st["transient_n"] == 0
    assert _poll(bot)["started"] is True          # 沒有 backoff：下一輪照常再試


@pytest.mark.parametrize("status", [400, 409, 422])
def test_unknown_4xx_on_get_post_marks_failed_without_reply(bot, poll5, status):
    """FN-4：未知 4xx → 標 failed、不回覆（不是回「讀不到」），之後也不再重試。"""
    _set_mentions(bot, ["m4", _mention("m45", replied_to="p450")], posts={
        "p450": _post_of("p450", _sim_error={"on": "get_post", "http": status}),
    })
    out = _poll(bot)
    assert (out["checked"], out["replied"], out["skipped"], out["errors"]) == (2, 1, 0, 1)
    assert out["stopped"] is None                                   # 單則的問題不中止整輪
    assert [x["mention_id"] for x in _sim_replies(bot)] == ["m4"]   # m45 沒有任何回覆（也沒有 reply_cannot_read）
    assert all(x["text"] != reply_cannot_read() for x in _sim_replies(bot))
    assert bot.ai.calls == [] and [r["mention_id"] for r in _records(bot)] == ["m4"]
    st = _state(bot)
    assert st["replied_ids"] == ["m4"]                              # failed 不進 replied_ids
    entry = st["failed"]["m45"]
    assert (entry["final"], entry["count"], entry["status"], entry["stage"]) == (True, 1, status, "get_post")
    assert entry["reason"] == f"http_{status}" and entry["at"]
    assert st["last_error"] == "mention_failed" and st["backoff_until"] is None
    assert st["last_since"] == _epoch("2026-09-14T09:00:00")        # 標 failed 的不擋游標

    get_post_calls = []
    real_get_post = bot.client.get_post
    bot.client.get_post = lambda media_id: get_post_calls.append(media_id) or real_get_post(media_id)
    out = _poll(bot)                                                 # m45 仍在 since 重疊區內，但不再處理
    assert (out["checked"], out["replied"], out["errors"]) == (0, 0, 0)
    assert get_post_calls == [] and len(_sim_replies(bot)) == 1
    st = _state(bot)
    assert st["failed"]["m45"] == entry and st["last_error"] is None


def test_unknown_4xx_on_reply_marks_failed_without_reply_or_record(bot, poll5):
    _set_mentions(bot, [_mention("m46", text=f"@factcheck_tw_bot {RUMOR_A}",
                                 _sim_error={"on": "reply_to", "http": 400})])
    out = _poll(bot)
    assert (out["checked"], out["replied"], out["errors"], out["stopped"]) == (1, 0, 1, None)
    assert len(bot.ai.calls) == 1
    assert _sim_replies(bot) == [] and _records(bot) == []            # jsonl 無新行
    st = _state(bot)
    assert st["replied_ids"] == [] and st["daily"]["replies"] == 0 and st["pending_publish"] == {}
    entry = st["failed"]["m46"]
    assert (entry["final"], entry["status"], entry["stage"]) == (True, 400, "create_container")
    assert bot.store.get_task(bot.ai.calls[0]["task_id"])["threads_reply_id"] is None

    out = _poll(bot)                                                   # 不重試：不再跑 AI、不再送
    assert (out["checked"], out["errors"]) == (0, 0)
    assert len(bot.ai.calls) == 1 and _sim_replies(bot) == []


def test_unknown_4xx_on_publish_marks_failed_and_clears_pending(bot, poll5):
    _set_mentions(bot, [_mention("m47", text=f"@factcheck_tw_bot {RUMOR_A}",
                                 _sim_error={"on": "publish", "http": 400})])
    out = _poll(bot)
    assert (out["replied"], out["errors"]) == (0, 1)
    st = _state(bot)
    assert st["pending_publish"] == {} and st["replied_ids"] == []
    assert (st["failed"]["m47"]["final"], st["failed"]["m47"]["stage"]) == (True, "publish")
    assert _sim_replies(bot) == [] and _poll(bot)["checked"] == 0


def test_unknown_4xx_failed_entry_tolerates_legacy_integer_counts(bot, poll5):
    """state.failed 舊格式是整數次數：≥2 視為終態、1 仍會重試。"""
    _set_mentions(bot, ["m1", "m4"])
    _write_state(bot, failed={"m1": 2, "m4": 1})
    out = _poll(bot)
    assert (out["checked"], out["replied"]) == (1, 1)
    assert [x["mention_id"] for x in _sim_replies(bot)] == ["m4"] and bot.ai.calls == []
    assert _state(bot)["failed"] == {"m1": 2}             # m4 成功後清掉失敗計數


def test_unreadable_404_on_get_post_still_replies_cannot_read(bot, poll5):
    """403／404／401 仍是「讀不到」→ reply_cannot_read（7 項既有子準則之一，不受 T-13 影響）。"""
    _set_mentions(bot, [_mention("m48", replied_to="no_such_post")])
    out = _poll(bot)
    assert (out["replied"], out["errors"]) == (1, 0)
    [line] = _sim_replies(bot)
    assert line["text"] == reply_cannot_read()
    st = _state(bot)
    assert st["replied_ids"] == ["m48"] and st["failed"] == {}


def test_link_limit_resends_once_without_source_line(bot, poll5):
    _set_mentions(bot, [_mention("m49", text=f"@factcheck_tw_bot {RUMOR_A}", _sim_error={
        "on": "reply_to", "http": 400, "body": LINK_LIMIT_BODY, "if_text_contains": "查核來源：",
    })])
    out = _poll(bot)
    assert (out["replied"], out["errors"]) == (1, 0)
    [line] = _sim_replies(bot)
    text = line["text"]
    assert "查核來源" not in text and TIER1_URL not in text
    assert f"完整判讀：{BASE}/r/{bot.ai.calls[0]['task_id']}" in text.split("\n")
    assert text.split("\n")[0] == RED + " 詐騙警告" and text.endswith("AI 自動判讀，請自行查證。")
    [rec] = _records(bot)
    assert rec["reply_text"] == text and rec["reply_id"] == "sim_reply_1"   # 紀錄的是實際送出的版本
    st = _state(bot)
    assert st["replied_ids"] == ["m49"] and st["failed"] == {} and st["daily"]["replies"] == 1
    assert len(bot.ai.calls) == 1


def test_link_limit_still_rejected_after_resend_marks_failed(bot, poll5):
    _set_mentions(bot, [_mention("m51", text=f"@factcheck_tw_bot {RUMOR_A}", _sim_error={
        "on": "reply_to", "http": 400, "body": LINK_LIMIT_BODY,
    })])
    sent = []
    real_create = bot.client.create_reply_container

    def spy_create(media_id, text, result_id=None):
        sent.append(text)
        return real_create(media_id, text, result_id=result_id)

    bot.client.create_reply_container = spy_create
    out = _poll(bot)
    assert (out["replied"], out["errors"]) == (0, 1)
    assert len(sent) == 2 and "查核來源：" in sent[0] and "查核來源" not in sent[1]   # 只重送一次
    st = _state(bot)
    assert st["failed"]["m51"]["final"] is True and st["replied_ids"] == [] and _sim_replies(bot) == []


def test_transient_three_consecutive_rounds_back_off_15_minutes(bot, poll5):
    _set_mentions(bot, [_mention("m52", replied_to="p520")], posts={
        "p520": _post_of("p520", _sim_error={"on": "get_post", "http": 503}),
    })
    for n in (1, 2):
        out = _poll(bot)
        assert (out["errors"], out["stopped"]) == (1, None)
        st = _state(bot)
        assert st["transient_n"] == n and st["backoff_until"] is None and st["last_error"] == "transient_error"
    out = _poll(bot)
    assert out["errors"] == 1
    st = _state(bot)
    assert st["transient_n"] == 3 and st["backoff_n"] == 0 and st["replied_ids"] == [] and st["failed"] == {}
    _assert_backoff(bot, 15)
    assert _poll(bot)["skipped"] == "backoff"

    _edit_mentions(bot, lambda data: data["posts"]["p520"].pop("_sim_error"))
    _expire_backoff(bot)
    out = _poll(bot)
    assert (out["replied"], out["errors"]) == (1, 0)
    st = _state(bot)
    assert st["transient_n"] == 0 and st["backoff_until"] is None and st["last_error"] is None


def test_transient_mentions_5xx_counts_and_a_clean_round_resets_the_streak(bot, poll5):
    _set_mentions(bot, [_mention("m53", text=f"@factcheck_tw_bot {RUMOR_A}",
                                 _sim_error={"on": "get_mentions", "http": 500})])
    for n in (1, 2):
        _poll(bot)
        st = _state(bot)
        assert st["transient_n"] == n and st["last_error"] == "mentions_failed" and st["backoff_until"] is None
    _inject(bot, "m53", _sim_error=None)
    assert _poll(bot)["replied"] == 1
    assert _state(bot)["transient_n"] == 0
    # 連續次數已歸零：再一次 5xx 不會直接觸發 15 分鐘 backoff
    _set_mentions(bot, ["m53", _mention("m54", text=f"@factcheck_tw_bot {RUMOR_B}", ts="2026-09-14T09:30:00+0000",
                                        _sim_error={"on": "get_mentions", "http": 500})])
    _poll(bot)
    st = _state(bot)
    assert st["transient_n"] == 1 and st["backoff_until"] is None


# ══════════════════════════════════════════════════════════════════
# T-12：兩段式發佈＋FINISHED 狀態檢查＋pending_publish（spec §7.6；
#        FN-4「container FINISHED 才 publish、ERROR 重試一次」）
# ══════════════════════════════════════════════════════════════════
class ContainerSpy(SpyThreadsService):
    """記錄兩段式發佈三步的呼叫順序；等待改為注入的 container_sleep（只記錄、不真的睡）。"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.calls = []
        self.sleeps = []
        self.container_sleep = self.sleeps.append

    def create_reply_container(self, media_id, text, result_id=None):
        self.calls.append(("create", str(media_id)))
        return super().create_reply_container(media_id, text, result_id=result_id)

    def get_container_status(self, container_id):
        out = super().get_container_status(container_id)
        self.calls.append(("status", container_id, out["status"]))
        return out

    def publish_container(self, container_id):
        self.calls.append(("publish", container_id))
        return super().publish_container(container_id)

    def names(self):
        return [c[0] for c in self.calls]

    def count(self, name):
        return self.names().count(name)


class CrashAfterCreate(ContainerSpy):
    """第一次 wait_container 前行程被砍（container 已建好、pending_publish 已寫入）。"""

    crash = True

    def wait_container(self, container_id, *args, **kwargs):
        if self.crash:
            self.crash = False
            raise SimulatedCrash("killed after container creation, before publish")
        return super().wait_container(container_id, *args, **kwargs)


@pytest.fixture
def cbot(bot, poll5):
    bot.client = ContainerSpy(mentions_path=bot.mentions_path)
    return bot


def _edit_container(bot, container_id, **fields):
    path = bot.client.containers_path
    data = json.loads(path.read_text(encoding="utf-8"))
    data["containers"][container_id].update(fields)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def test_container_publishes_only_after_finished(cbot):
    _set_mentions(cbot, ["m1"])
    _inject(cbot, "m1", _sim_container={"statuses": ["IN_PROGRESS", "IN_PROGRESS", "FINISHED"]})
    out = _poll(cbot)
    assert (out["replied"], out["errors"]) == (1, 0)
    assert cbot.client.calls == [
        ("create", "m1"),
        ("status", "sim_container_1", "IN_PROGRESS"),
        ("status", "sim_container_1", "IN_PROGRESS"),
        ("status", "sim_container_1", "FINISHED"),
        ("publish", "sim_container_1"),                   # FINISHED 之後才 publish
    ]
    assert cbot.client.sleeps == [5.0, 5.0]               # 每 5 秒查一次；等待是注入的，沒有真的睡
    [line] = _sim_replies(cbot)
    assert line["mention_id"] == "m1" and line["reply_id"] == "sim_reply_1"
    st = _state(cbot)
    assert st["replied_ids"] == ["m1"] and st["pending_publish"] == {} and st["failed"] == {}


def test_container_finished_on_first_check_adds_no_wait(cbot):
    """sim 預設第一次就 FINISHED：兩段式發佈不增加回覆延遲（PF-3a）。"""
    _set_mentions(cbot, ["m1", "m2"])
    assert _poll(cbot)["replied"] == 2
    assert cbot.client.names() == ["create", "status", "publish"] * 2
    assert cbot.client.sleeps == []


def test_container_pending_publish_is_written_before_publish(cbot):
    seen = {}
    real_publish = cbot.client.publish_container

    def probing_publish(container_id):
        seen["pending"] = threads_state.load_state(cbot.data)["pending_publish"]   # 讀磁碟上的 state
        return real_publish(container_id)

    cbot.client.publish_container = probing_publish
    _set_mentions(cbot, ["m1"])
    assert _poll(cbot)["replied"] == 1
    entry = seen["pending"]["m1"]
    assert entry["container_id"] == "sim_container_1" and entry["mode"] == "sim" and entry["created_at"]
    assert entry["result_id"] == cbot.ai.calls[0]["task_id"] and entry["analyzed"] is True
    assert entry["reply_text"] == _sim_replies(cbot)[0]["text"]
    assert _state(cbot)["pending_publish"] == {}          # publish 成功後刪鍵


@pytest.mark.parametrize("status, last_error", [("ERROR", "container_error"), ("EXPIRED", "container_expired")])
def test_container_error_is_never_published_retried_once_then_given_up(cbot, status, last_error):
    """FN-4：ERROR 不 publish；下輪重試一次（重建 container）；第二次仍失敗 → 放棄，且不標成已回覆。"""
    _set_mentions(cbot, ["m1"])
    _inject(cbot, "m1", _sim_container={"statuses": [status], "error_message": "sim: media processing failed"})
    out = _poll(cbot)
    assert (out["checked"], out["replied"], out["errors"], out["stopped"]) == (1, 0, 1, None)
    assert cbot.client.names() == ["create", "status"]                  # 沒有 publish
    st = _state(cbot)
    assert st["replied_ids"] == [] and st["pending_publish"] == {}
    assert (st["failed"]["m1"]["count"], st["failed"]["m1"]["final"]) == (1, False)
    assert st["failed"]["m1"]["reason"] == last_error and st["last_error"] == last_error
    assert st["backoff_until"] is None and st["last_since"] == TS_M1 - 1   # 留待下輪重試

    out = _poll(cbot)                                                    # 重試一次：重建 container，仍失敗
    assert (out["checked"], out["replied"], out["errors"]) == (1, 0, 1)
    assert cbot.client.names() == ["create", "status", "create", "status"]
    st = _state(cbot)
    assert (st["failed"]["m1"]["count"], st["failed"]["m1"]["final"]) == (2, True)
    assert st["replied_ids"] == [] and st["daily"]["replies"] == 0       # 放棄 ≠ 已回覆
    assert _sim_replies(cbot) == [] and _records(cbot) == []
    assert st["last_since"] == TS_M1                                     # 放棄後不再擋游標

    out = _poll(cbot)                                                    # 之後不再重試、不再重跑 AI
    assert (out["checked"], out["errors"]) == (0, 0)
    assert cbot.client.count("create") == 2 and len(cbot.ai.calls) == 2
    assert all(cbot.store.get_task(c["task_id"])["threads_reply_id"] is None for c in cbot.ai.calls)


def test_container_error_then_retry_succeeds_replies_exactly_once(cbot):
    _set_mentions(cbot, ["m1"])
    _inject(cbot, "m1", _sim_container=["ERROR"])                        # 陣列寫法
    assert _poll(cbot)["errors"] == 1
    _inject(cbot, "m1", _sim_container=None)
    out = _poll(cbot)
    assert (out["replied"], out["errors"]) == (1, 0)
    assert cbot.client.names() == ["create", "status", "create", "status", "publish"]
    assert cbot.client.calls[-1] == ("publish", "sim_container_2")
    assert Counter(x["mention_id"] for x in _sim_replies(cbot)) == {"m1": 1}
    st = _state(cbot)
    assert st["replied_ids"] == ["m1"] and st["failed"] == {} and st["daily"]["replies"] == 1
    assert st["last_error"] is None
    assert _poll(cbot)["replied"] == 0


def test_container_retry_round_with_ai_unavailable_neither_replies_nor_gives_up(cbot):
    """fallback 規則不變：重試那一輪若 AI 不可用 → 不回覆、不標記，也不算一次 container 失敗。"""
    _set_mentions(cbot, ["m1"])
    _inject(cbot, "m1", _sim_container=["ERROR"])
    assert _poll(cbot)["errors"] == 1
    _inject(cbot, "m1", _sim_container=None)

    cbot.ai.analysis = AI_FALLBACK
    out = _poll(cbot)
    assert (out["replied"], out["skipped"], out["errors"]) == (0, 1, 0)
    assert cbot.client.count("create") == 1                      # AI 不可用：連 container 都不建
    st = _state(cbot)
    assert st["replied_ids"] == [] and st["pending_publish"] == {} and st["last_error"] == "ai_unavailable"
    assert (st["failed"]["m1"]["count"], st["failed"]["m1"]["final"]) == (1, False)

    cbot.ai.analysis = AI_SCAM
    out = _poll(cbot)
    assert (out["replied"], out["errors"]) == (1, 0)
    assert Counter(x["mention_id"] for x in _sim_replies(cbot)) == {"m1": 1}
    assert _state(cbot)["failed"] == {} and _state(cbot)["last_error"] is None


def test_container_in_progress_wait_is_bounded_then_same_container_is_resumed(cbot):
    _set_mentions(cbot, ["m1"])
    _inject(cbot, "m1", _sim_container={"statuses": ["IN_PROGRESS"]})
    out = _poll(cbot)
    assert (out["replied"], out["errors"]) == (0, 1)
    assert cbot.client.count("status") == 13 and cbot.client.count("publish") == 0   # 60 // 5 + 1 次
    assert cbot.client.sleeps == [5.0] * 12 and sum(cbot.client.sleeps) == 60.0       # 最多等 60 秒
    st = _state(cbot)
    assert st["pending_publish"]["m1"]["container_id"] == "sim_container_1"          # TIMEOUT：保留，下輪先查同一個
    assert (st["failed"]["m1"]["count"], st["failed"]["m1"]["final"]) == (1, False)
    assert st["last_error"] == "container_timeout" and st["replied_ids"] == []

    _edit_container(cbot, "sim_container_1", statuses=["FINISHED"])      # 這個 container 後來處理完了
    out = _poll(cbot)
    assert (out["checked"], out["replied"], out["errors"]) == (1, 1, 0)
    assert cbot.client.count("create") == 1 and len(cbot.ai.calls) == 1  # 不重建 container、不重跑 AI
    assert cbot.client.calls[-2:] == [("status", "sim_container_1", "FINISHED"), ("publish", "sim_container_1")]
    [line] = _sim_replies(cbot)
    task_id = cbot.ai.calls[0]["task_id"]
    assert line["mention_id"] == "m1" and line["result_id"] == task_id
    [rec] = _records(cbot)
    assert rec["reply_id"] == "sim_reply_1" and rec["reply_text"] == line["text"] and rec["result_id"] == task_id
    assert rec["frame_type"] == "red" and rec["risk_type"] == "SCAM" and rec["username"] == "tester_a"
    assert rec["source_text_preview"] == P100_TEXT
    assert cbot.store.get_task(task_id)["threads_reply_id"] == "sim_reply_1"
    st = _state(cbot)
    assert st["replied_ids"] == ["m1"] and st["pending_publish"] == {} and st["failed"] == {}
    assert st["daily"]["replies"] == 1


def test_container_timeout_twice_gives_up_without_rebuilding(cbot):
    _set_mentions(cbot, ["m1"])
    _inject(cbot, "m1", _sim_container={"statuses": ["IN_PROGRESS"]})
    assert _poll(cbot)["errors"] == 1
    out = _poll(cbot)                                                     # 下輪先查同一個 container：仍未完成
    assert (out["checked"], out["replied"], out["errors"]) == (1, 0, 1)
    assert cbot.client.count("create") == 1 and cbot.client.count("status") == 26
    st = _state(cbot)
    assert st["failed"]["m1"]["final"] is True and st["pending_publish"] == {} and st["replied_ids"] == []
    assert _poll(cbot)["checked"] == 0 and len(cbot.ai.calls) == 1 and _sim_replies(cbot) == []


def test_container_publish_failure_next_poll_publishes_same_container_once(cbot):
    """publish 暫時失敗 → pending 保留 → 下輪用同一個 container 補發；整個情境 container 只建 1 次。"""
    _set_mentions(cbot, ["m1"])
    _inject(cbot, "m1", _sim_error={"on": "publish", "http": 500})
    out = _poll(cbot)
    assert (out["replied"], out["errors"]) == (0, 1)
    st = _state(cbot)
    assert st["pending_publish"]["m1"]["container_id"] == "sim_container_1"
    assert st["replied_ids"] == [] and st["failed"] == {}                 # 暫時性錯誤不算 container 失敗
    assert st["transient_n"] == 1 and st["last_error"] == "transient_error" and _sim_replies(cbot) == []

    _inject(cbot, "m1", _sim_error=None)
    out = _poll(cbot)
    assert (out["checked"], out["replied"], out["errors"]) == (1, 1, 0)
    assert [c for c in cbot.client.calls if c[0] == "create"] == [("create", "m1")]
    assert [c for c in cbot.client.calls if c[0] == "publish"] == [("publish", "sim_container_1")] * 2
    assert Counter(x["mention_id"] for x in _sim_replies(cbot)) == {"m1": 1} and len(cbot.ai.calls) == 1
    st = _state(cbot)
    assert st["replied_ids"] == ["m1"] and st["pending_publish"] == {} and st["transient_n"] == 0
    assert _poll(cbot)["replied"] == 0                                   # 重複回覆率 0


@pytest.mark.parametrize("on, http, stopped, last_error, minutes", [
    ("publish", 429, "rate_limited", "rate_limited", 5),
    ("publish", 401, "token_invalid", "token_invalid", 60),
    ("container_status", 429, "rate_limited", "rate_limited", 5),
    ("container_status", 503, None, "transient_error", None),
])
def test_container_api_errors_after_creation_keep_pending_for_the_same_container(cbot, on, http, stopped, last_error, minutes):
    """container 建好之後的 429／401／5xx：不標記、pending 保留；backoff 過後對同一個 container 補發。"""
    _set_mentions(cbot, ["m1", "m2"])
    _inject(cbot, "m1", _sim_error={"on": on, "http": http})
    out = _poll(cbot)
    assert (out["replied"], out["errors"], out["stopped"]) == ((0, 1, stopped) if stopped else (1, 1, None))
    st = _state(cbot)
    assert st["pending_publish"]["m1"]["container_id"] == "sim_container_1"
    assert "m1" not in st["replied_ids"] and st["failed"] == {} and st["last_error"] == last_error
    if minutes:
        _assert_backoff(cbot, minutes)               # 429／401 → 本輪中止，m2 留待 backoff 之後
        assert "m2" not in st["replied_ids"]
    else:
        assert st["backoff_until"] is None and st["transient_n"] == 1

    _inject(cbot, "m1", _sim_error=None)
    _expire_backoff(cbot)
    out = _poll(cbot)
    assert out["errors"] == 0 and out["stopped"] is None
    assert [c for c in cbot.client.calls if c[0] == "create" and c[1] == "m1"] == [("create", "m1")]
    assert Counter(x["mention_id"] for x in _sim_replies(cbot)) == {"m1": 1, "m2": 1}
    assert len(cbot.ai.calls) == 1
    st = _state(cbot)
    assert sorted(st["replied_ids"]) == ["m1", "m2"] and st["pending_publish"] == {} and st["backoff_until"] is None


def test_container_unknown_4xx_on_status_counts_as_a_publish_failure(cbot):
    """查 container 狀態回未列入的 4xx（container 已被清掉）：視同 EXPIRED——刪 pending、計一次失敗、下輪重建。"""
    _set_mentions(cbot, ["m1"])
    _inject(cbot, "m1", _sim_error={"on": "container_status", "http": 404})
    out = _poll(cbot)
    assert (out["replied"], out["errors"]) == (0, 1)
    st = _state(cbot)
    assert st["pending_publish"] == {} and st["replied_ids"] == []
    assert (st["failed"]["m1"]["count"], st["failed"]["m1"]["final"]) == (1, False)
    assert st["failed"]["m1"]["reason"] == "container_unreadable" and cbot.client.count("publish") == 0

    _inject(cbot, "m1", _sim_error=None)
    assert _poll(cbot)["replied"] == 1
    assert cbot.client.count("create") == 2 and Counter(x["mention_id"] for x in _sim_replies(cbot)) == {"m1": 1}


def test_container_crash_before_publish_resumes_same_container(bot, poll5):
    bot.client = CrashAfterCreate(mentions_path=bot.mentions_path)
    _set_mentions(bot, ["m1"])
    with pytest.raises(SimulatedCrash):
        _poll(bot)
    st = _state(bot)
    assert st["pending_publish"]["m1"]["container_id"] == "sim_container_1" and st["replied_ids"] == []
    assert _sim_replies(bot) == []

    out = _poll(bot)
    assert (out["checked"], out["replied"]) == (1, 1)
    assert bot.client.count("create") == 1 and len(bot.ai.calls) == 1
    assert Counter(x["mention_id"] for x in _sim_replies(bot)) == {"m1": 1}
    assert _state(bot)["pending_publish"] == {}


def test_container_already_published_is_marked_not_published_again(cbot, monkeypatch):
    """publish 成功後、寫 state 前被砍：下輪查到 PUBLISHED 只補標記，絕不再發一次。"""
    _set_mentions(cbot, ["m1"])
    real_mark = threads_bot.PollContext.mark

    async def killed(self, *args, **kwargs):
        raise SimulatedCrash("killed right after publish_container returned")

    monkeypatch.setattr(threads_bot.PollContext, "mark", killed)
    with pytest.raises(SimulatedCrash):
        _poll(cbot)
    assert [x["mention_id"] for x in _sim_replies(cbot)] == ["m1"]       # 回覆已送出
    st = _state(cbot)
    assert st["replied_ids"] == [] and "m1" in st["pending_publish"]     # 但還沒記住

    monkeypatch.setattr(threads_bot.PollContext, "mark", real_mark)
    out = _poll(cbot)
    assert (out["checked"], out["replied"], out["errors"]) == (1, 1, 0)
    assert cbot.client.count("publish") == 1 and cbot.client.count("create") == 1
    assert cbot.client.calls[-1] == ("status", "sim_container_1", "PUBLISHED")
    assert len(_sim_replies(cbot)) == 1 and len(cbot.ai.calls) == 1
    st = _state(cbot)
    assert st["replied_ids"] == ["m1"] and st["pending_publish"] == {} and st["daily"]["replies"] == 1
    assert _poll(cbot)["replied"] == 0


def test_container_expired_pending_returns_to_normal_flow_in_the_same_round(bot, poll5):
    bot.client = CrashAfterCreate(mentions_path=bot.mentions_path)
    _set_mentions(bot, ["m1"])
    with pytest.raises(SimulatedCrash):
        _poll(bot)
    _edit_container(bot, "sim_container_1", statuses=["EXPIRED"])        # 隔了一天才重啟：container 已過期

    out = _poll(bot)
    # 補發失敗計 1 次錯誤並刪鍵 → 同一輪走正常流程重建 container；checked 不重複計
    assert (out["checked"], out["replied"], out["skipped"], out["errors"]) == (1, 1, 0, 1)
    assert bot.client.count("create") == 2 and bot.client.count("publish") == 1
    assert bot.client.calls[-1] == ("publish", "sim_container_2")
    assert Counter(x["mention_id"] for x in _sim_replies(bot)) == {"m1": 1}
    st = _state(bot)
    assert st["replied_ids"] == ["m1"] and st["pending_publish"] == {} and st["failed"] == {}


def test_container_pending_of_other_mode_and_malformed_entries(cbot):
    live_entry = {"container_id": "17900000000000999", "mode": "live", "reply_text": "x", "analyzed": True}
    _write_state(cbot, pending_publish={"17900000000000001": live_entry, "m2": {"creation_id": "legacy-shape"}})
    _set_mentions(cbot, ["m2"])
    out = _poll(cbot)
    assert (out["checked"], out["replied"], out["errors"]) == (1, 1, 0)
    assert all(c[1] != "17900000000000999" for c in cbot.client.calls)   # live 的 container 不在 sim 補發
    st = _state(cbot)
    assert st["pending_publish"] == {"17900000000000001": live_entry}     # 留給 live 模式；壞格式的那筆已清掉
    assert st["replied_ids"] == ["m2"] and st["failed"] == {}


def test_container_resumed_analyzed_reply_respects_daily_cap(cbot, monkeypatch):
    _set_mentions(cbot, ["m1"])
    _inject(cbot, "m1", _sim_error={"on": "publish", "http": 503})
    assert _poll(cbot)["errors"] == 1
    _inject(cbot, "m1", _sim_error=None)
    monkeypatch.setattr(settings, "THREADS_MAX_REPLIES_PER_DAY", 1)
    _write_state(cbot, daily={"date": threads_state.taipei_today(), "replies": 1})
    out = _poll(cbot)
    assert (out["checked"], out["replied"], out["stopped"]) == (0, 0, "daily_cap")
    assert cbot.client.count("publish") == 1                 # 上限已滿：這輪連補發都不送
    assert "m1" in _state(cbot)["pending_publish"] and _sim_replies(cbot) == []

    _write_state(cbot, daily={"date": threads_state.taipei_today(), "replies": 0})   # 隔天歸零後補發
    out = _poll(cbot)
    assert (out["checked"], out["replied"], out["stopped"]) == (1, 1, None)
    assert cbot.client.count("create") == 1 and len(_sim_replies(cbot)) == 1
    assert _state(cbot)["daily"]["replies"] == 1             # 補發的判定回覆同樣計入每日回覆數


class LegacyReplyOnlyClient:
    """只有 reply_to()、沒有三個 container 操作的舊式客戶端（run_threads_poll 仍要能用）。"""

    available = True

    def __init__(self, inner, error=None):
        self._inner, self._error, self.reply_calls = inner, error, []

    def get_mentions(self, since=None, after_cursor=None):
        return self._inner.get_mentions(since, after_cursor)

    def get_post(self, media_id):
        return self._inner.get_post(media_id)

    def reply_to(self, media_id, text):
        self.reply_calls.append(media_id)
        if self._error is not None:
            raise self._error
        return self._inner.reply_to(media_id, text)


def test_container_legacy_client_without_container_api_still_replies(bot, poll5):
    _set_mentions(bot, ["m1"])
    legacy = LegacyReplyOnlyClient(bot.client)
    out = _poll(bot, client=legacy)
    assert (out["replied"], out["errors"]) == (1, 0) and legacy.reply_calls == ["m1"]
    st = _state(bot)
    assert st["replied_ids"] == ["m1"] and st["pending_publish"] == {}
    [rec] = _records(bot)
    assert rec["reply_id"] == "sim_reply_1" and rec["result_id"] == bot.ai.calls[0]["task_id"]


@pytest.mark.parametrize("status, stopped, failed_final", [
    (429, "rate_limited", False), (400, None, True), (503, None, False),
])
def test_container_legacy_client_errors_use_the_same_triage(bot, poll5, status, stopped, failed_final):
    _set_mentions(bot, ["m1"])
    legacy = LegacyReplyOnlyClient(bot.client, error=ThreadsApiError(status, {"error": {"message": "x"}}))
    out = _poll(bot, client=legacy)
    assert (out["replied"], out["errors"], out["stopped"]) == (0, 1, stopped)
    st = _state(bot)
    assert st["replied_ids"] == [] and ("m1" in st["failed"]) is failed_final
    assert (st["backoff_until"] is not None) is (status == 429)


# ── FakeThreadsService 的 container 模擬（sim 才能離線覆蓋 §7.6／§7.10）──────────────
def test_fake_container_lifecycle_and_persistence_across_instances(fake):
    cid = fake.create_reply_container("m1", "回覆一", result_id="task-1")
    assert cid == "sim_container_1" and fake.containers_path == fake.mentions_path.parent / "containers.json"
    assert not fake.replies_path.exists()                     # 建 container 不等於發佈

    again = FakeThreadsService(mentions_path=fake.mentions_path)   # sim 每輪重建客戶端：container 要落檔
    assert again.get_container_status(cid) == {"id": cid, "status": "FINISHED"}
    assert again.wait_container(cid) == "FINISHED"
    assert again.publish_container(cid) == "sim_reply_1"
    [line] = _read_lines(fake.replies_path)
    assert set(line) == {"ts", "mention_id", "reply_id", "result_id", "text"}
    assert (line["mention_id"], line["result_id"], line["text"]) == ("m1", "task-1", "回覆一")

    assert fake.get_container_status(cid)["status"] == "PUBLISHED"
    with pytest.raises(ThreadsApiError) as ei:
        fake.publish_container(cid)                           # 已發佈的不能再發
    assert ei.value.status == 400 and len(_read_lines(fake.replies_path)) == 1
    assert fake.create_reply_container("m4", "回覆二") == "sim_container_2"


def test_fake_container_cache_sees_external_edits_and_deletion(fake):
    """containers.json 有行程內快取（mtime＋大小驗證）：別的實例、手動改檔、刪檔都要立刻反映。"""
    cid = fake.create_reply_container("m1", "x")
    assert fake.get_container_status(cid)["status"] == "FINISHED"          # 此時快取已是熱的

    data = json.loads(fake.containers_path.read_text(encoding="utf-8"))
    data["containers"][cid]["statuses"] = ["EXPIRED"]
    data["containers"][cid]["checks"] = 0
    fake.containers_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")   # 手動改檔
    assert fake.get_container_status(cid)["status"] == "EXPIRED"

    other = FakeThreadsService(mentions_path=fake.mentions_path)             # 另一個實例寫入
    cid2 = other.create_reply_container("m2", "y")
    assert fake.get_container_status(cid2)["status"] == "FINISHED"

    fake.containers_path.unlink()                                            # --reset 式的刪檔
    with pytest.raises(ThreadsApiError) as ei:
        fake.get_container_status(cid)
    assert ei.value.status == 404
    assert fake.create_reply_container("m1", "z") == "sim_container_1"       # 編號從頭開始


def test_fake_container_publish_requires_finished_status(fake):
    data = json.loads(fake.mentions_path.read_text(encoding="utf-8"))
    data["mentions"][0]["_sim_container"] = {"statuses": ["IN_PROGRESS", "ERROR"], "error_message": "boom"}
    fake.mentions_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    cid = fake.create_reply_container("m1", "text")
    with pytest.raises(ThreadsApiError) as ei:
        fake.publish_container(cid)                           # 還沒查過狀態
    assert ei.value.status == 400
    assert fake.get_container_status(cid) == {"id": cid, "status": "IN_PROGRESS"}
    with pytest.raises(ThreadsApiError):
        fake.publish_container(cid)                           # IN_PROGRESS 也不行
    assert fake.get_container_status(cid) == {"id": cid, "status": "ERROR", "error_message": "boom"}
    assert fake.get_container_status(cid)["status"] == "ERROR"    # 序列用完停在最後一格
    assert not fake.replies_path.exists()
    with pytest.raises(ThreadsApiError) as ei:
        fake.get_container_status("sim_container_404")
    assert ei.value.status == 404


def test_fake_container_wait_uses_injected_sleep_and_reply_to_returns_none_unless_finished(fake):
    data = json.loads(fake.mentions_path.read_text(encoding="utf-8"))
    data["mentions"][0]["_sim_container"] = ["IN_PROGRESS", "FINISHED"]
    data["mentions"][3]["_sim_container"] = ["ERROR"]
    fake.mentions_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    sleeps = []
    fake.container_sleep = sleeps.append
    assert fake.reply_to("m1", "等一下就好") == "sim_reply_1" and sleeps == [5.0]
    assert fake.reply_to("m4", "不會發出去") is None                      # ERROR：不 publish
    assert [x["mention_id"] for x in _read_lines(fake.replies_path)] == ["m1"]
    cid = fake.create_reply_container("m2", "自訂等待")
    assert fake.wait_container(cid, interval=1, timeout=3, sleep=sleeps.append) == "FINISHED"


def test_fake_container_error_injection_points_and_text_condition(fake):
    data = json.loads(fake.mentions_path.read_text(encoding="utf-8"))
    by_id = {m["id"]: m for m in data["mentions"]}
    by_id["m1"]["_sim_error"] = {"on": "container_status", "http": 503}
    by_id["m2"]["_sim_error"] = {"on": "publish", "http": 500}
    by_id["m4"]["_sim_error"] = {"on": "create_container", "http": 400, "body": LINK_LIMIT_BODY,
                                 "if_text_contains": "查核來源："}
    fake.mentions_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    c1 = fake.create_reply_container("m1", "x")
    with pytest.raises(ThreadsApiError) as ei:
        fake.get_container_status(c1)
    assert ei.value.status == 503

    c2 = fake.create_reply_container("m2", "y")
    assert fake.wait_container(c2) == "FINISHED"
    with pytest.raises(ThreadsApiError) as ei:
        fake.publish_container(c2)
    assert ei.value.status == 500 and not fake.replies_path.exists()

    with pytest.raises(ThreadsApiError) as ei:
        fake.create_reply_container("m4", "判定\n查核來源：https://example.org/a")
    assert ei.value.status == 400 and ts.is_link_limit_error(ei.value)
    assert fake.create_reply_container("m4", "判定（沒有來源行）").startswith("sim_container_")
