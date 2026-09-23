"""
Parquet 安全讀寫（單機、多執行緒）

問題（2026-09 錄 demo 時實測）：處理器寫 tasks.parquet 的同時，結果頁輪詢讀同一檔，
讀到寫一半的檔案 → pyarrow 解析失敗 → GET /api/result 回 500。

- atomic_write_parquet：先寫同目錄暫存檔，再 os.replace 換上（讀者只會看到舊檔或新檔）。
  Windows 上若目標檔正被讀取，replace 會 PermissionError → 短暫重試。
- read_parquet_retry：讀取失敗（檔案正被替換）時短暫重試。
- path_lock：同一檔案的「讀 → 改 → 寫」在同一行程內序列化，避免兩個執行緒互蓋更新。
- concat_rows：附加新列時對齊全為空值的欄位型別（pandas 2.x 的 concat FutureWarning，DEF-07）。
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

# 總等待約 5 秒：Windows 上防毒或另一個讀者短暫持有檔案時，os.replace／讀取都可能暫時 PermissionError
_RETRY_DELAYS = (0.02, 0.05, 0.1, 0.2, 0.3, 0.4, 0.5, 0.5, 0.6, 0.7, 0.8, 0.8)


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


def _cast_all_na(frame: pd.DataFrame, col: str, dtype) -> None:
    # 布林與整數欄放不下 NaN（NaN 轉布林會變 True），交給 pandas 決定
    if pd.api.types.is_bool_dtype(dtype) or pd.api.types.is_integer_dtype(dtype):
        return
    try:
        frame[col] = frame[col].astype(dtype)
    except (TypeError, ValueError):
        pass


def concat_rows(existing: pd.DataFrame, new_rows: pd.DataFrame) -> pd.DataFrame:
    """
    附加新列。pandas 2.x 在 concat 決定欄位型別時會略過「全為空值」的欄位，這個行為已棄用
    （每次寫入都印 FutureWarning，DEF-07），未來版本會改變結果型別。這裡先把一邊全為空值的欄位
    轉成另一邊的型別再 concat：結果型別與現行行為相同，升級 pandas 後也不會改變。
    會就地轉換兩個輸入中全為空值的欄位（呼叫端傳入的都是剛讀出或剛建立的暫時 DataFrame）。
    """
    if existing.empty:
        return new_rows.reset_index(drop=True)
    for col in existing.columns.intersection(new_rows.columns):
        left_na, right_na = existing[col].isna().all(), new_rows[col].isna().all()
        if left_na and not right_na:
            _cast_all_na(existing, col, new_rows[col].dtype)
        elif right_na and not left_na:
            _cast_all_na(new_rows, col, existing[col].dtype)
    return pd.concat([existing, new_rows], ignore_index=True)
