"""
假訊息知識庫模型（對應 V4.1 Schema）
"""
from sqlalchemy import Column, String, Boolean, Float, Text, Integer, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
from pgvector.sqlalchemy import Vector
import uuid
from app.database import Base


class ScamKnowledgeBase(Base):
    """
    假訊息知識庫表格
    
    對應白皮書 V4.1 的資料庫 Schema
    """
    __tablename__ = "scam_knowledge_base"
    
    # 主鍵
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # [1] 原始資料區
    data_type = Column(String(10), nullable=False)  # URL, TEXT, IMAGE, VIDEO
    raw_content = Column(Text, nullable=False)  # 原始使用者輸入
    data_hash = Column(String(64), unique=True, nullable=False, index=True)  # SHA-256
    
    # [2] 向量與分析區
    content_vector = Column(Vector(768), nullable=True)  # Embedding 向量
    
    # [3] 風險評估區（核心對應欄位）
    is_risk = Column(Boolean, default=False, nullable=False)
    risk_type = Column(String(20), nullable=True)  # SCAM, MISINFO, SAFE
    category = Column(String(50), nullable=True)  # Investment, Health_Rumor 等
    confidence_score = Column(Float, nullable=True)  # 0.0-1.0
    
    # AI 分析結果（完整 JSON）
    ai_analysis = Column(JSONB, nullable=True)
    
    # [4] 生命週期管理
    created_at = Column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        nullable=False
    )
    last_accessed_at = Column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )
    hit_count = Column(Integer, default=1, nullable=False)
    
    def __repr__(self):
        return f"<ScamKnowledgeBase(id={self.id}, risk_type={self.risk_type}, category={self.category})>"

