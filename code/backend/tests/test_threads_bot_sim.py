"""Threads 機器人 sim 模式測試（FN-4）。

- T-05：ThreadsClient Protocol 與 FakeThreadsService 自身（test_fake_*）。
- T-08：單則 mention 處理 handle_mention／resolve_target（test_bot_*、test_resolve_*）。
- T-09：run_threads_poll 互斥鎖、since 游標、本地上限（test_poll_*）。

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
    (StubClient(error=ThreadsApiError(400)), {"replied_to": "p1"}, ("unreadable", None, "text")),
    (StubClient(error=ThreadsApiError(429)), {"replied_to": {"id": "p1"}}, ("transient", None, "text")),
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
    "404", "403", "401", "400_scalar_replied_to", "429", "503", "no_status", "exception",
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
