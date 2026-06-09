"""
FactCheckRecord - SQLAlchemy model for trending news analysis results.
"""
import uuid
from datetime import datetime
from sqlalchemy import Column, String, Text, Float, Boolean, DateTime
from app.database_sql import Base


class FactCheckRecord(Base):
    __tablename__ = "fact_check_records"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    source_url = Column(String(500), nullable=True, index=True, unique=True)
    news_title = Column(String(300), nullable=True)
    content = Column(Text, nullable=True)
    ai_score = Column(Float, nullable=True)
    ai_summary = Column(Text, nullable=True)
    risk_type = Column(String(20), nullable=True)
    category = Column(String(50), nullable=True)
    is_trending = Column(Boolean, default=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "source_url": self.source_url,
            "news_title": self.news_title,
            "ai_score": self.ai_score,
            "ai_summary": self.ai_summary,
            "risk_type": self.risk_type,
            "category": self.category,
            "is_trending": self.is_trending,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
