"""
任務儲存（Pandas/Parquet 版）
"""
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime
import uuid

import pandas as pd


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
        """載入任務 DataFrame"""
        if self.tasks_path.exists():
            return pd.read_parquet(self.tasks_path)

        return pd.DataFrame(
            columns=[
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
        )

    def _save_tasks(self, df: pd.DataFrame) -> None:
        """儲存任務 DataFrame"""
        df.to_parquet(self.tasks_path, index=False)

    def create_task(self, task_type: str, input_data: str) -> str:
        """
        建立新任務，狀態預設為 pending。
        """
        df = self._load_tasks()

        task_id = str(uuid.uuid4())
        now = datetime.utcnow()

        record = {
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

        new_row = pd.DataFrame([record])

        if df.empty:
            df = new_row
        else:
            common_cols = df.columns.intersection(new_row.columns)
            df = pd.concat([df[common_cols], new_row[common_cols]], ignore_index=True)

        self._save_tasks(df)
        return task_id

    def update_task(self, task_id: str, **fields: Any) -> None:
        """
        更新任務欄位（例如 status、result_data、error_message）。
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
            df.loc[mask, key] = value

        self._save_tasks(df)

    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """
        取得單一任務紀錄。
        """
        df = self._load_tasks()
        if df.empty:
            return None

        match = df[df["id"] == task_id]
        if match.empty:
            return None

        record = match.iloc[0].to_dict()

        
        for key in ["created_at", "updated_at", "completed_at"]:
            value = record.get(key)
            if isinstance(value, datetime):
                record[key] = value.isoformat()

        return record

