"""
覆寫與回饋儲存（Pandas/Parquet 版）
"""
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any
import uuid

import pandas as pd


class AuditStore:
    """
    儲存管理者覆寫紀錄與使用者回饋（Parquet）。
    - data/admin_overrides.parquet
    - data/user_feedback.parquet
    """

    def __init__(self, data_dir: str = "data") -> None:
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.overrides_path = self.data_dir / "admin_overrides.parquet"
        self.feedback_path = self.data_dir / "user_feedback.parquet"

    def _load_overrides(self) -> pd.DataFrame:
        if self.overrides_path.exists():
            return pd.read_parquet(self.overrides_path)
        return pd.DataFrame(
            columns=[
                "id",
                "task_id",
                "new_risk_type",
                "new_category",
                "new_confidence_score",
                "admin_id",
                "reason",
                "created_at",
            ]
        )

    def _save_overrides(self, df: pd.DataFrame) -> None:
        df.to_parquet(self.overrides_path, index=False)

    def _load_feedback(self) -> pd.DataFrame:
        if self.feedback_path.exists():
            return pd.read_parquet(self.feedback_path)
        return pd.DataFrame(
            columns=[
                "id",
                "task_id",
                "user_id",
                "rating",
                "comment",
                "created_at",
            ]
        )

    def _save_feedback(self, df: pd.DataFrame) -> None:
        df.to_parquet(self.feedback_path, index=False)

    def append_override(
        self,
        task_id: str,
        admin_id: str,
        reason: str,
        new_risk_type: Optional[str] = None,
        new_category: Optional[str] = None,
        new_confidence_score: Optional[float] = None,
    ) -> Dict[str, Any]:
        df = self._load_overrides()
        record = {
            "id": str(uuid.uuid4()),
            "task_id": task_id,
            "new_risk_type": new_risk_type,
            "new_category": new_category,
            "new_confidence_score": new_confidence_score,
            "admin_id": admin_id,
            "reason": reason,
            "created_at": datetime.utcnow(),
        }
        df = pd.concat([df, pd.DataFrame([record])], ignore_index=True)
        self._save_overrides(df)
        record["created_at"] = record["created_at"].isoformat()
        return record

    def append_feedback(
        self,
        task_id: str,
        rating: str,
        comment: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        df = self._load_feedback()
        record = {
            "id": str(uuid.uuid4()),
            "task_id": task_id,
            "user_id": user_id,
            "rating": rating,
            "comment": comment,
            "created_at": datetime.utcnow(),
        }
        df = pd.concat([df, pd.DataFrame([record])], ignore_index=True)
        self._save_feedback(df)
        record["created_at"] = record["created_at"].isoformat()
        return record

