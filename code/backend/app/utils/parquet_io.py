"""
Parquet 安全讀寫（單機、多執行緒）

問題（2026-09 錄 demo 時實測）：處理器寫 tasks.parquet 的同時，結果頁輪詢讀同一檔，
讀到寫一半的檔案 → pyarrow 解析失敗 → GET /api/result 回 500。

- atomic_write_parquet：先寫同目錄暫存檔，再 os.replace 換上（讀者只會看到舊檔或新檔）。
  Windows 上若目標檔正被讀取，replace 會 PermissionError → 短暫重試。
- read_parquet_retry：讀取失敗（檔案正被替換）時短暫重試。
- path_lock：同一檔案的「讀 → 改 → 寫」在同一行程內序列化，避免兩個執行緒互蓋更新。
"""
import os
import threading
import time
import uuid
from collections import defaultdict
from pathlib import Path

import pandas as pd

_LOCKS = defaultdict(threading.RLock)
_LOCKS_GUARD = threading.Lock()

_RETRY_DELAYS = (0.02, 0.05, 0.1, 0.2, 0.4, 0.8)


def path_lock(path: Path) -> threading.RLock:
    key = str(Path(path).resolve())
    with _LOCKS_GUARD:
        return _LOCKS[key]


def read_parquet_retry(path: Path) -> pd.DataFrame:
    last_exc = None
    for delay in (0.0,) + _RETRY_DELAYS:
        if delay:
            time.sleep(delay)
        try:
            return pd.read_parquet(path)
        except FileNotFoundError:
            raise
        except Exception as exc:  # 寫一半或正在替換：稍後重讀
            last_exc = exc
    raise last_exc


def atomic_write_parquet(df: pd.DataFrame, path: Path) -> None:
    path = Path(path)
    tmp = path.with_name(f"{path.name}.tmp-{os.getpid()}-{uuid.uuid4().hex[:8]}")
    df.to_parquet(tmp, index=False)
    try:
        last_exc = None
        for delay in (0.0,) + _RETRY_DELAYS:
            if delay:
                time.sleep(delay)
            try:
                os.replace(tmp, path)
                return
            except PermissionError as exc:  # Windows：目標檔正被讀取
                last_exc = exc
        raise last_exc
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass
