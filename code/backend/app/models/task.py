"""
任務模型（追蹤非同步任務狀態）
"""
from sqlalchemy import Column, String, Text, TIMESTAMP, Enum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid
import enum
from app.database import Base


class TaskStatus(enum.Enum):
    """任務狀態枚舉"""
    PENDING = "pending"  # 待處理
    PROCESSING = "processing"  # 處理中
    COMPLETED = "completed"  # 已完成
    FAILED = "failed"  # 失敗


class Task(Base):
    """
    任務追蹤表格
    
    用於追蹤非同步任務的執行狀態
    """
    __tablename__ = "tasks"
    
    # 主鍵
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # 任務資訊
    task_type = Column(String(50), nullable=False)  # analyze_url, analyze_text, analyze_image
    input_data = Column(Text, nullable=False)  # 原始輸入（URL 或文字）
    
    # 狀態追蹤
    status = Column(
        Enum(TaskStatus),
        default=TaskStatus.PENDING,
        nullable=False
    )
    result_data = Column(Text, nullable=True)  # 結果 JSON 字串
    error_message = Column(Text, nullable=True)  # 錯誤訊息
    
    # 時間戳記
    created_at = Column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        nullable=False
    )
    updated_at = Column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )
    completed_at = Column(TIMESTAMP(timezone=True), nullable=True)
    
    def __repr__(self):
        return f"<Task(id={self.id}, status={self.status}, type={self.task_type})>"

