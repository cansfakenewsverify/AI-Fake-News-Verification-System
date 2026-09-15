"""Parquet 安全讀寫：寫入中讀取不會讀到半截檔、並發更新不互蓋（2026-09 demo 錄影時的 500 回歸測試）。"""
import threading

import pandas as pd
import pytest

from app.services.task_store import TaskStore
from app.utils import parquet_io
from app.utils.parquet_io import atomic_write_parquet, read_parquet_retry


def test_atomic_write_leaves_no_temp_files(tmp_path):
    path = tmp_path / "x.parquet"
    atomic_write_parquet(pd.DataFrame({"a": [1, 2]}), path)
    atomic_write_parquet(pd.DataFrame({"a": [3]}), path)
    assert read_parquet_retry(path)["a"].tolist() == [3]
    assert [p.name for p in tmp_path.iterdir()] == ["x.parquet"]


def test_read_retries_until_file_is_valid(tmp_path, monkeypatch):
    path = tmp_path / "x.parquet"
    atomic_write_parquet(pd.DataFrame({"a": [1]}), path)
    real = pd.read_parquet
    calls = {"n": 0}

    def flaky(p, *a, **k):
        calls["n"] += 1
        if calls["n"] < 3:
            raise OSError("file is being replaced")
        return real(p, *a, **k)

    monkeypatch.setattr(parquet_io.pd, "read_parquet", flaky)
    monkeypatch.setattr(parquet_io, "_RETRY_DELAYS", (0.0, 0.0, 0.0))
    assert read_parquet_retry(path)["a"].tolist() == [1]
    assert calls["n"] == 3


def test_read_gives_up_and_raises(tmp_path, monkeypatch):
    path = tmp_path / "x.parquet"
    atomic_write_parquet(pd.DataFrame({"a": [1]}), path)

    def broken(p, *a, **k):
        raise OSError("still broken")

    monkeypatch.setattr(parquet_io.pd, "read_parquet", broken)
    monkeypatch.setattr(parquet_io, "_RETRY_DELAYS", (0.0,))
    with pytest.raises(OSError):
        read_parquet_retry(path)


def test_replace_retries_on_permission_error(tmp_path, monkeypatch):
    path = tmp_path / "x.parquet"
    atomic_write_parquet(pd.DataFrame({"a": [1]}), path)
    real_replace = parquet_io.os.replace
    calls = {"n": 0}

    def busy(src, dst):
        calls["n"] += 1
        if calls["n"] == 1:
            raise PermissionError("target open by a reader")
        return real_replace(src, dst)

    monkeypatch.setattr(parquet_io.os, "replace", busy)
    monkeypatch.setattr(parquet_io, "_RETRY_DELAYS", (0.0, 0.0))
    atomic_write_parquet(pd.DataFrame({"a": [9]}), path)
    assert read_parquet_retry(path)["a"].tolist() == [9]
    assert [p.name for p in tmp_path.iterdir()] == ["x.parquet"]


def test_concurrent_task_updates_do_not_lose_writes_or_break_reads(tmp_path):
    store = TaskStore(data_dir=str(tmp_path))
    ids = [store.create_task("analyze_text", f"訊息 {i}") for i in range(8)]
    errors = []

    def writer(task_id):
        try:
            for step in range(5):
                store.update_task(task_id, status="processing" if step < 4 else "completed")
        except Exception as exc:  # pragma: no cover - 失敗時由斷言報出
            errors.append(exc)

    def reader():
        try:
            for _ in range(40):
                for task_id in ids:
                    store.get_task(task_id)
        except Exception as exc:  # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=writer, args=(i,)) for i in ids] + [threading.Thread(target=reader)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    assert all(store.get_task(i)["status"] == "completed" for i in ids)
