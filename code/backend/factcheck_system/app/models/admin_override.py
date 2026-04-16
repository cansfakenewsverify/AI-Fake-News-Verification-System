"""
管理者覆寫紀錄模型
"""
from sqlalchemy import Column, String, Text, Float, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid
from app.database import Base


class AdminOverride(Base):
    """
    管理者覆寫表

    用於記錄管理者對 AI 判定結果的手動覆寫行為（審計用途）。
    """

    __tablename__ = "admin_overrides"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # 關聯目標：目前以任務為主（必要時可再擴充到知識庫）
    task_id = Column(UUID(as_uuid=True), nullable=False, index=True)

    # 覆寫後的核心欄位
    new_risk_type = Column(String(20), nullable=True)  # SCAM, MISINFO, SAFE
    new_category = Column(String(50), nullable=True)
    new_confidence_score = Column(Float, nullable=True)

    # 管理者資訊與原因
    admin_id = Column(String(100), nullable=False)
    reason = Column(Text, nullable=False)

    # 時間戳記
    created_at = Column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<AdminOverride(id={self.id}, task_id={self.task_id}, admin_id={self.admin_id})>"

