"""
任務儲存（Pandas/Parquet 版）

tasks.parquet 同時承載結果頁 /r/{id}（spec §6.1），因此：
- 上限 5,000 筆，修剪只砍 status in (completed, failed) 中最舊者，不砍 pending/processing。
- 舊檔（v1.0 前 9 欄）載入時缺欄位補預設，這就是唯一的「遷移」（不發網路請求、不重算）。
"""
import functools
import json
import math
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime
import uuid

import pandas as pd

from app.utils.parquet_io import atomic_write_parquet, path_lock, read_parquet_retry


def _locked(method):
    """同一行程內，tasks.parquet 的「讀 → 改 → 寫」一次只跑一個（輪詢寫入與處理器更新不互蓋）。"""
    @functools.wraps(method)
    def wrapper(self, *args, **kwargs):
        with path_lock(self.tasks_path):
            return method(self, *args, **kwargs)
    return wrapper

# 結果頁要能重新整理/分享，保留最近 N 筆；只修剪已結束的任務
_MAX_TASKS = 5000

_PRUNABLE_STATUSES = ("completed", "failed")

_BASE_COLUMNS = [
    "id",
    "task_type",
    "input_data",
    "status",
    "result_data",
    "error_message",
    "created_at",
    "updated_at",
    "completed_at",
]

# spec §6.1 新欄位 → 舊列預設值（input_type 另由 task_type 推得）
_NEW_COLUMN_DEFAULTS: Dict[str, Any] = {
    "input_type": None,
    "origin": "web",
    "threads_mention_id": None,
    "threads_reply_id": None,
    "platform_post": None,          # JSON str
    "ai_unavailable": False,
    "label_source": "ai",
    "kb_id": None,
    "verified": False,              # 舊列一律 False，不重算（OP-7 離線載入）
    "source_tier": None,
    "related_discussions": None,    # JSON str
}

_ALL_COLUMNS = _BASE_COLUMNS + list(_NEW_COLUMN_DEFAULTS.keys())

_JSON_COLUMNS = ("platform_post", "related_discussions")
_DATETIME_COLUMNS = ("created_at", "updated_at", "completed_at")
# 不可為空的欄位：既有列若為 NA 也補預設
_NON_NULL_DEFAULTS = ("origin", "ai_unavailable", "label_source", "verified")


def input_type_from_task_type(task_type: Any) -> str:
    """analyze_url -> url、analyze_image -> image、其餘 -> text"""
    if task_type == "analyze_url":
        return "url"
    if task_type == "analyze_image":
        return "image"
    return "text"


def _is_na(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    try:
        return bool(pd.isna(value)) if not isinstance(value, (list, dict, tuple)) else False
    except (TypeError, ValueError):
        return False


def _encode_value(key: str, value: Any) -> Any:
    """JSON 欄位若收到 dict/list 則序列化成字串"""
    if key in _JSON_COLUMNS and isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return value


class TaskStore:
    """
    使用 Pandas + Parquet 儲存非同步任務狀態與結果。

    檔案位置沿用 PandasStore 的 data 目錄結構：
    - data/tasks.parquet
    """

    def __init__(self, data_dir: str = "data") -> None:
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.tasks_path = self.data_dir / "tasks.parquet"

    def _load_tasks(self) -> pd.DataFrame:
        """載入任務 DataFrame，缺欄位補預設值"""
        if not self.tasks_path.exists():
            return pd.DataFrame(columns=_ALL_COLUMNS)

        df = read_parquet_retry(self.tasks_path)

        for col in _BASE_COLUMNS:
            if col not in df.columns:
                df[col] = None

        for col, default in _NEW_COLUMN_DEFAULTS.items():
            if col == "input_type":
                derived = df["task_type"].map(input_type_from_task_type)
                if col not in df.columns:
                    df[col] = derived
                else:
                    df[col] = df[col].astype(object).where(df[col].notna(), derived)
                continue
            if col not in df.columns:
                df[col] = pd.Series([default] * len(df), index=df.index, dtype=object)
            elif col in _NON_NULL_DEFAULTS and df[col].isna().any():
                df[col] = df[col].astype(object).where(df[col].notna(), default)

        return df

    def _save_tasks(self, df: pd.DataFrame) -> None:
        """儲存任務 DataFrame（先寫暫存檔再替換，讀者不會讀到寫一半的檔案）"""
        atomic_write_parquet(df, self.tasks_path)

    @staticmethod
    def _prune(df: pd.DataFrame) -> pd.DataFrame:
        """超過上限時只刪已結束（completed/failed）中最舊者；pending/processing 保留"""
        excess = len(df) - _MAX_TASKS
        if excess <= 0:
            return df
        # df 依建立順序排列（append-only），位置越前越舊
        prunable_idx = df.index[df["status"].isin(_PRUNABLE_STATUSES)]
        drop_idx = prunable_idx[:excess]
        return df.drop(index=drop_idx).reset_index(drop=True)

    @_locked
    def create_task(
        self,
        task_type: str,
        input_data: str,
        input_type: Optional[str] = None,
        origin: str = "web",
        **extra: Any,
    ) -> str:
        """
        建立新任務，狀態預設為 pending。

        extra 可帶 spec §6.1 新欄位（threads_mention_id、platform_post…）；未知鍵忽略。
        """
        df = self._load_tasks()

        task_id = str(uuid.uuid4())
        now = datetime.utcnow()

        record: Dict[str, Any] = {
            "id": task_id,
            "task_type": task_type,
            "input_data": input_data,
            "status": "pending",
            "result_data": None,
            "error_message": None,
            "created_at": now,
            "updated_at": now,
            "completed_at": None,
        }
        record.update(_NEW_COLUMN_DEFAULTS)
        record["input_type"] = input_type or input_type_from_task_type(task_type)
        record["origin"] = origin or "web"
        for key, value in extra.items():
            if key in _NEW_COLUMN_DEFAULTS and key not in ("input_type", "origin"):
                record[key] = _encode_value(key, value)

        new_row = pd.DataFrame([record], columns=_ALL_COLUMNS)

        if df.empty:
            df = new_row
        else:
            # Align columns and drop all-NA cols to avoid FutureWarning in pandas 2.x
            left = df.dropna(axis=1, how="all")
            right = new_row.dropna(axis=1, how="all")
            df = pd.concat([left, right], ignore_index=True)
            for col in df.columns.union(_ALL_COLUMNS):
                if col not in df.columns:
                    df[col] = None
            extra_cols = [c for c in df.columns if c not in _ALL_COLUMNS]
            df = df[_ALL_COLUMNS + extra_cols]

        df = self._prune(df)

        self._save_tasks(df)
        return task_id

    @_locked
    def update_task(self, task_id: str, **fields: Any) -> None:
        """
        更新任務欄位（status、result_data、error_message 與 spec §6.1 新欄位）。
        """
        df = self._load_tasks()
        if df.empty:
            return

        mask = df["id"] == task_id
        if not mask.any():
            return

        df.loc[mask, "updated_at"] = datetime.utcnow()

        for key, value in fields.items():
            if key not in df.columns:
                continue
            value = _encode_value(key, value)
            if key not in _DATETIME_COLUMNS and df[key].dtype != object:
                # 避免 bool/float 欄位塞入不同型別時的 dtype 警告
                df[key] = df[key].astype(object)
            df.loc[mask, key] = value

        self._save_tasks(df)

    def recent_kb_refs(self, since: datetime) -> List[Dict[str, Any]]:
        """
        熱門查證（app/services/hot_claims.py）的原始資料：since 之後建立（UTC、不帶時區，
        與 created_at 相同）、已完成、且對應到知識庫某一列的任務。每筆回
        {kb_id, created_at, origin}，依建立先後；不含使用者輸入。Postgres 版行為相同。
        """
        df = self._load_tasks()
        if df.empty:
            return []
        created = pd.to_datetime(df["created_at"], errors="coerce")
        kb_ids = df["kb_id"].astype(object).where(df["kb_id"].notna(), None)
        mask = (
            (df["status"] == "completed")
            & kb_ids.map(lambda v: bool(v) and str(v).strip() != "")
            & (created >= pd.Timestamp(since))
        )
        return [
            {
                "kb_id": str(kb_ids[idx]),
                "created_at": created[idx].to_pydatetime(),
                "origin": str(df.at[idx, "origin"] or "web"),
            }
            for idx in df.index[mask.fillna(False)]
        ]

    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """
        取得單一任務紀錄（NA 轉 None、numpy 型別轉 Python 型別）。
        """
        df = self._load_tasks()
        if df.empty:
            return None

        match = df[df["id"] == task_id]
        if match.empty:
            return None

        record = match.iloc[0].to_dict()

        for key, value in list(record.items()):
            if _is_na(value):
                record[key] = None
            elif hasattr(value, "item") and not isinstance(value, (str, bytes, datetime)):
                try:
                    record[key] = value.item()
                except (ValueError, AttributeError):
                    pass

        for key in _DATETIME_COLUMNS:
            value = record.get(key)
            if isinstance(value, datetime):
                record[key] = value.isoformat()

        for key in ("ai_unavailable", "verified"):
            record[key] = bool(record.get(key)) if record.get(key) is not None else False

        tier = record.get("source_tier")
        if tier is not None:
            try:
                record["source_tier"] = int(tier)
            except (TypeError, ValueError):
                record["source_tier"] = None

        return record
