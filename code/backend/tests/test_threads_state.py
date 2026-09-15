"""T-07：Threads state 原子寫入與 threads_replies.jsonl 紀錄（離線、零點數）。"""
import json
from datetime import datetime, timezone

import pytest

from app.services import threads_state as ts


def test_missing_file_returns_defaults(tmp_path):
    state = ts.load_state(tmp_path)
    for key in ("replied_ids", "last_since", "last_poll_at", "last_stats", "last_error",
                "daily", "backoff_until", "backoff_n", "pending_publish", "failed"):
        assert key in state
    assert state["replied_ids"] == []
    assert state["last_since"] == 0
    assert state["pending_publish"] == {} and state["failed"] == {}
    assert state["daily"]["replies"] == 0


def test_legacy_format_fills_defaults(tmp_path):
    (tmp_path / "threads_state.json").write_text(
        json.dumps({"replied_ids": ["a", "b"]}), encoding="utf-8")
    state = ts.load_state(tmp_path)
    assert state["replied_ids"] == ["a", "b"]
    assert state["backoff_n"] == 0
    assert state["last_error"] is None
    assert state["daily"]["date"] == ts.taipei_today()


def test_corrupt_file_returns_defaults(tmp_path):
    (tmp_path / "threads_state.json").write_text("{not json", encoding="utf-8")
    assert ts.load_state(tmp_path)["replied_ids"] == []


def test_save_roundtrip_and_trims_replied_ids(tmp_path):
    state = ts.load_state(tmp_path)
    state["replied_ids"] = [str(i) for i in range(2500)]
    state["last_since"] = 123
    state["pending_publish"] = {"m1": {"creation_id": "c1"}}
    ts.save_state(state, tmp_path)
    again = ts.load_state(tmp_path)
    assert len(again["replied_ids"]) == ts.REPLIED_IDS_MAX
    assert again["replied_ids"][0] == "500" and again["replied_ids"][-1] == "2499"
    assert again["last_since"] == 123
    assert again["pending_publish"] == {"m1": {"creation_id": "c1"}}
    # 沒有殘留 temp 檔
    assert [p.name for p in tmp_path.iterdir()] == ["threads_state.json"]


def test_crash_before_replace_keeps_original(tmp_path, monkeypatch):
    ts.save_state({"replied_ids": ["keep"]}, tmp_path)
    original = (tmp_path / "threads_state.json").read_text(encoding="utf-8")

    def boom(*_args, **_kwargs):
        raise RuntimeError("simulated crash before os.replace")

    monkeypatch.setattr(ts.os, "replace", boom)
    state = ts.load_state(tmp_path)
    state["replied_ids"].append("new")
    with pytest.raises(RuntimeError):
        ts.save_state(state, tmp_path)

    assert (tmp_path / "threads_state.json").read_text(encoding="utf-8") == original
    assert [p.name for p in tmp_path.iterdir()] == ["threads_state.json"]
    monkeypatch.undo()
    assert ts.load_state(tmp_path)["replied_ids"] == ["keep"]


def test_daily_resets_across_taipei_midnight(tmp_path):
    # 2026-09-20 15:30 UTC = 23:30 台北
    before = datetime(2026, 9, 20, 15, 30, tzinfo=timezone.utc)
    # 2026-09-20 16:30 UTC = 隔天 00:30 台北
    after = datetime(2026, 9, 20, 16, 30, tzinfo=timezone.utc)

    state = ts.load_state(tmp_path, now=before)
    assert state["daily"] == {"date": "2026-09-20", "replies": 0}
    state["daily"]["replies"] = 7
    ts.save_state(state, tmp_path, now=before)
    assert ts.load_state(tmp_path, now=before)["daily"] == {"date": "2026-09-20", "replies": 7}

    rolled = ts.load_state(tmp_path, now=after)
    assert rolled["daily"] == {"date": "2026-09-21", "replies": 0}

    # save_state 也會跨日重置
    stale = ts.load_state(tmp_path, now=before)
    ts.save_state(stale, tmp_path, now=after)
    raw = json.loads((tmp_path / "threads_state.json").read_text(encoding="utf-8"))
    assert raw["daily"] == {"date": "2026-09-21", "replies": 0}


def _rec(i, **extra):
    base = {"mention_id": f"m{i}", "mode": "sim", "result_id": f"r{i}",
            "frame_type": "red", "risk_type": "SCAM", "username": "tester",
            "source_text_preview": "中獎通知請點連結", "reply_text": f"判定 {i}",
            "reply_id": f"reply{i}", "permalink": f"https://threads.net/p/{i}"}
    base.update(extra)
    return base


def test_jsonl_reverse_order_and_bad_lines(tmp_path):
    ts.append_reply_record(_rec(1), tmp_path)
    with (tmp_path / "threads_replies.jsonl").open("a", encoding="utf-8") as fh:
        fh.write("{broken json\n\n[1,2]\n")
    ts.append_reply_record(_rec(2), tmp_path)
    ts.append_reply_record(_rec(3), tmp_path)

    records = ts.read_reply_records(10, tmp_path)
    assert [r["mention_id"] for r in records] == ["m3", "m2", "m1"]
    assert [r["mention_id"] for r in ts.read_reply_records(2, tmp_path)] == ["m3", "m2"]
    assert set(records[0].keys()) == set(ts.REPLY_RECORD_FIELDS)
    assert records[0]["replied_at"]

    # 中文不被 escape
    raw = (tmp_path / "threads_replies.jsonl").read_text(encoding="utf-8")
    assert "中獎通知" in raw


def test_read_records_missing_file(tmp_path):
    assert ts.read_reply_records(10, tmp_path) == []
    assert ts.own_reply_ids(tmp_path) == set()


def test_own_reply_ids(tmp_path):
    ts.append_reply_record(_rec(1), tmp_path)
    ts.append_reply_record(_rec(2, reply_id=None), tmp_path)
    ts.append_reply_record(_rec(3), tmp_path)
    assert ts.own_reply_ids(tmp_path) == {"reply1", "reply3"}
