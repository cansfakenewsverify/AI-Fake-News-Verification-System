"""T-05：ThreadsClient Protocol 與 FakeThreadsService（sim 模式）自身測試。

全部離線：以 tests/fixtures/threads_mentions.json 的複本在 tmp_path 操作，
requests 被封鎖，任何網路呼叫都會讓測試失敗。
"""
import json
import shutil
from pathlib import Path

import pytest
import requests

from app.config import settings
from app.services import threads_service as ts
from app.services.threads_service import (
    ThreadsAPIError,
    ThreadsApiError,
    ThreadsClient,
    ThreadsService,
    get_threads_client,
)
from app.services.threads_sim import FakeThreadsService

FIXTURE = Path(__file__).parent / "fixtures" / "threads_mentions.json"
EXAMPLE = Path(__file__).resolve().parent.parent / "scripts" / "threads_sim_mentions.example.json"


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    def _blocked(*args, **kwargs):
        raise AssertionError("network access is not allowed in sim tests")

    for name in ("get", "post", "request"):
        monkeypatch.setattr(requests, name, _blocked)
    monkeypatch.setattr(requests.Session, "request", _blocked)


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
