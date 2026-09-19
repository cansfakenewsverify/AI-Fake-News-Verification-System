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


# ══════════════════════════════════════════════════════════════════
# T-13：backoff 純函式（spec §7.10）與 failed 的上限
# ══════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("poll_minutes, n, expected", [
    (5, 0, 5), (5, 1, 10), (5, 2, 20), (5, 3, 40), (5, 4, 60), (5, 5, 60), (5, 500, 60),   # min(60, 5 × 2^n)
    (1, 0, 1), (1, 5, 32), (1, 6, 60),
    (30, 0, 30), (30, 1, 60), (90, 0, 60),
    (5, None, 5), (5, -3, 5), (5, "2", 20), (5, "x", 5),          # n 壞資料 → 當 0
    (0, 0, 1), (None, 2, 4), ("abc", 0, 1), (-5, 1, 2),           # 間隔壞資料 → 當 1 分鐘
])
def test_rate_limit_backoff_minutes_formula_and_cap(poll_minutes, n, expected):
    assert ts.rate_limit_backoff_minutes(poll_minutes, n) == float(expected)
    assert ts.rate_limit_backoff_minutes(poll_minutes, n) <= ts.BACKOFF_MAX_MINUTES == 60


def test_new_state_has_transient_counter(tmp_path):
    state = ts.load_state(tmp_path)
    assert state["transient_n"] == 0 and state["backoff_n"] == 0 and state["backoff_until"] is None


def test_set_backoff_writes_utc_iso_and_keeps_the_later_deadline():
    now = datetime(2026, 9, 19, 12, 0, tzinfo=timezone.utc)
    state = ts.default_state()
    assert ts.set_backoff(state, 15, now) == "2026-09-19T12:15:00+00:00" == state["backoff_until"]
    assert ts.backoff_remaining_seconds(state, now) == 15 * 60

    ts.set_backoff(state, 60, now)                       # 較晚的蓋過較早的
    assert state["backoff_until"] == "2026-09-19T13:00:00+00:00"
    ts.set_backoff(state, 5, now)                        # 較短的不會把仍有效的較長 backoff 縮短
    assert state["backoff_until"] == "2026-09-19T13:00:00+00:00"

    later = datetime(2026, 9, 19, 14, 0, tzinfo=timezone.utc)
    assert ts.backoff_remaining_seconds(state, later) == 0.0
    ts.set_backoff(state, 5, later)                      # 舊的已到期：以新的為準
    assert state["backoff_until"] == "2026-09-19T14:05:00+00:00"
    # naive datetime 視為 UTC
    assert ts.set_backoff(ts.default_state(), 1, datetime(2026, 9, 19, 12, 0)) == "2026-09-19T12:01:00+00:00"


@pytest.mark.parametrize("value, expected", [
    ("2026-09-19T12:00:00+00:00", datetime(2026, 9, 19, 12, 0, tzinfo=timezone.utc)),
    ("2026-09-19T12:00:00Z", datetime(2026, 9, 19, 12, 0, tzinfo=timezone.utc)),
    ("2026-09-19T12:00:00+0000", datetime(2026, 9, 19, 12, 0, tzinfo=timezone.utc)),
    ("2026-09-19T20:00:00+08:00", datetime(2026, 9, 19, 12, 0, tzinfo=timezone.utc)),
    ("2026-09-19T12:00:00", datetime(2026, 9, 19, 12, 0, tzinfo=timezone.utc)),
    (1789819200, datetime.fromtimestamp(1789819200, tz=timezone.utc)),
    ("1789819200.5", datetime.fromtimestamp(1789819200.5, tz=timezone.utc)),
    (None, None), ("", None), ("not a date", None), (True, None), ([], None), (1e30, None),
])
def test_parse_until_accepts_iso_and_epoch_and_never_raises(value, expected):
    assert ts.parse_until(value) == expected


def test_backoff_remaining_seconds_ignores_missing_or_broken_values():
    now = datetime(2026, 9, 19, 12, 0, tzinfo=timezone.utc)
    for value in (None, "", "garbage", "2026-09-19T11:59:59+00:00"):
        assert ts.backoff_remaining_seconds({"backoff_until": value}, now) == 0.0   # 壞資料不讓輪詢永久停擺
    assert ts.backoff_remaining_seconds({}, now) == 0.0
    assert ts.backoff_remaining_seconds({"backoff_until": "2026-09-19T12:00:30+00:00"}, now) == 30.0


def test_backoff_and_failed_survive_the_atomic_roundtrip(tmp_path):
    state = ts.load_state(tmp_path)
    until = ts.set_backoff(state, 10)
    state["backoff_n"], state["transient_n"] = 3, 2
    state["failed"] = {"m1": {"count": 2, "final": True, "reason": "container_error"}, "legacy": 1}
    state["pending_publish"] = {"m2": {"container_id": "c-1", "reply_text": "判定 🔴"}}
    ts.save_state(state, tmp_path)
    again = ts.load_state(tmp_path)
    assert (again["backoff_until"], again["backoff_n"], again["transient_n"]) == (until, 3, 2)
    assert again["failed"] == state["failed"] and again["pending_publish"] == state["pending_publish"]
    assert ts.backoff_remaining_seconds(again) > 9 * 60
    assert [p.name for p in tmp_path.iterdir()] == ["threads_state.json"]


def test_save_trims_failed_to_the_most_recent_entries(tmp_path):
    state = ts.load_state(tmp_path)
    state["failed"] = {f"m{i}": {"count": 1, "final": True} for i in range(ts.FAILED_MAX + 25)}
    ts.save_state(state, tmp_path)
    failed = ts.load_state(tmp_path)["failed"]
    assert len(failed) == ts.FAILED_MAX
    assert "m24" not in failed and "m25" in failed and f"m{ts.FAILED_MAX + 24}" in failed
