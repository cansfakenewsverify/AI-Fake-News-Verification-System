"""B-14：tasks.parquet 新欄位、舊檔相容（OP-7）與修剪規則（離線、零點數）"""
import json
import warnings
from datetime import datetime, timedelta

import pandas as pd

from app.services import task_store as ts_mod
from app.services.task_store import TaskStore

OLD_COLUMNS = [
    "id", "task_type", "input_data", "status", "result_data",
    "error_message", "created_at", "updated_at", "completed_at",
]


def _write_old_parquet(path):
    now = datetime(2026, 7, 1, 12, 0, 0)
    rows = [
        {"id": "old-text", "task_type": "analyze_text", "input_data": "謠言",
         "status": "completed", "result_data": "{}", "error_message": None,
         "created_at": now, "updated_at": now, "completed_at": now},
        {"id": "old-url", "task_type": "analyze_url", "input_data": "https://example.com",
         "status": "failed", "result_data": None, "error_message": "boom",
         "created_at": now + timedelta(seconds=1), "updated_at": now, "completed_at": None},
        {"id": "old-image", "task_type": "analyze_image", "input_data": "img",
         "status": "pending", "result_data": None, "error_message": None,
         "created_at": now + timedelta(seconds=2), "updated_at": now, "completed_at": None},
        {"id": "old-threads", "task_type": "threads_mention", "input_data": "貼文",
         "status": "processing", "result_data": None, "error_message": None,
         "created_at": now + timedelta(seconds=3), "updated_at": now, "completed_at": None},
    ]
    pd.DataFrame(rows, columns=OLD_COLUMNS).to_parquet(path / "tasks.parquet", index=False)
    return len(rows)


def test_old_tasks_parquet_loads_with_defaults(tmp_path):
    n = _write_old_parquet(tmp_path)
    store = TaskStore(data_dir=str(tmp_path))

    df = store._load_tasks()
    assert len(df) == n
    for col in ts_mod._NEW_COLUMN_DEFAULTS:
        assert col in df.columns

    expected_input_type = {
        "old-text": "text", "old-url": "url", "old-image": "image", "old-threads": "text",
    }
    for tid, itype in expected_input_type.items():
        task = store.get_task(tid)
        assert task["input_type"] == itype
        assert task["origin"] == "web"
        assert task["threads_mention_id"] is None
        assert task["threads_reply_id"] is None
        assert task["platform_post"] is None
        assert task["ai_unavailable"] is False
        assert task["label_source"] == "ai"
        assert task["kb_id"] is None
        assert task["verified"] is False
        assert task["source_tier"] is None
        assert task["related_discussions"] is None

    # 舊資料原值不變
    assert store.get_task("old-url")["error_message"] == "boom"
    assert store.get_task("old-text")["status"] == "completed"

    # 寫一次再讀，舊列筆數與預設仍在
    store.update_task("old-text", verified=True, source_tier=1, kb_id="kb-1")
    assert len(store._load_tasks()) == n
    t = store.get_task("old-text")
    assert t["verified"] is True and t["source_tier"] == 1 and t["kb_id"] == "kb-1"
    assert store.get_task("old-url")["verified"] is False


def test_prune_keeps_pending(tmp_path, monkeypatch):
    monkeypatch.setattr(ts_mod, "_MAX_TASKS", 3)
    store = TaskStore(data_dir=str(tmp_path))

    p1 = store.create_task("analyze_text", "pending-1")          # 最舊，但 pending
    c1 = store.create_task("analyze_text", "completed-1")
    store.update_task(c1, status="completed")
    f1 = store.create_task("analyze_text", "failed-1")
    store.update_task(f1, status="failed")
    pr1 = store.create_task("analyze_text", "processing-1")
    store.update_task(pr1, status="processing")

    # 第 4 筆超過上限 3：刪最舊的已結束者 c1，pending p1 保留
    ids = set(store._load_tasks()["id"])
    assert len(ids) == 3
    assert p1 in ids and f1 in ids and pr1 in ids
    assert c1 not in ids

    p2 = store.create_task("analyze_text", "pending-2")
    ids = set(store._load_tasks()["id"])
    assert ids == {p1, pr1, p2}   # f1 被刪

    # 全部都是 pending/processing 時不硬砍（可暫時超過上限）
    p3 = store.create_task("analyze_text", "pending-3")
    ids = set(store._load_tasks()["id"])
    assert ids == {p1, pr1, p2, p3}


def test_max_tasks_is_5000():
    assert ts_mod._MAX_TASKS == 5000


def test_create_task_with_origin_threads(tmp_path):
    store = TaskStore(data_dir=str(tmp_path))
    web_id = store.create_task("analyze_url", "https://example.com")
    post = {"platform": "threads", "post_id": "123", "permalink": "https://www.threads.net/@a/post/x",
            "username": "a"}
    with warnings.catch_warnings():
        warnings.simplefilter("error", FutureWarning)
        tid = store.create_task(
            "threads_mention", "可疑貼文", origin="threads",
            threads_mention_id="m-1", platform_post=post, not_a_column="ignored",
        )
        store.update_task(
            tid, status="completed", threads_reply_id="r-1", ai_unavailable=True,
            label_source="ai", kb_id="kb-9", verified=True, source_tier=2,
            related_discussions=[{"url": "https://ptt.cc/x", "tier": 3}],
            completed_at=datetime.utcnow(),
        )

    task = store.get_task(tid)
    assert task["origin"] == "threads"
    assert task["input_type"] == "text"
    assert task["threads_mention_id"] == "m-1"
    assert task["threads_reply_id"] == "r-1"
    assert json.loads(task["platform_post"]) == post
    assert "not_a_column" not in task
    assert task["ai_unavailable"] is True
    assert task["verified"] is True
    assert task["source_tier"] == 2
    assert task["kb_id"] == "kb-9"
    assert json.loads(task["related_discussions"])[0]["tier"] == 3
    assert task["status"] == "completed"
    assert isinstance(task["completed_at"], str)

    web = store.get_task(web_id)
    assert web["origin"] == "web" and web["input_type"] == "url"
    assert web["verified"] is False and web["source_tier"] is None

    explicit = store.create_task("analyze_text", "x", input_type="image")
    assert store.get_task(explicit)["input_type"] == "image"
