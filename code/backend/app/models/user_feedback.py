"""
使用者回饋模型
"""
from sqlalchemy import Column, String, Text, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid
from app.database import Base


class UserFeedback(Base):
    """
    使用者回饋表

    用於記錄一般使用者對 AI 判定結果的意見與說明。
    """

    __tablename__ = "user_feedback"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # 關聯目標：目前綁定到任務結果
    task_id = Column(UUID(as_uuid=True), nullable=False, index=True)

    # 使用者識別（可選，用於後台分析）
    user_id = Column(String(100), nullable=True)

    # 回饋等級（agree / disagree / uncertain 等）
    rating = Column(String(20), nullable=False)

    # 補充說明
    comment = Column(Text, nullable=True)

    created_at = Column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<UserFeedback(id={self.id}, task_id={self.task_id}, rating={self.rating})>"

