"""
FactCheckRecord - SQLAlchemy model for trending news analysis results.
"""
import uuid
from datetime import datetime
from sqlalchemy import Column, String, Text, Float, Boolean, DateTime, Integer
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
    # spec 6.3 new columns (D-01). Old DBs get them via init_sql_db() idempotent ALTER.
    platform = Column(String(20), nullable=True)       # rss | cofacts | threads
    post_id = Column(String(64), nullable=True)        # Threads media id
    label_source = Column(String(10), nullable=True)   # ai | rule | gold | admin
    result_id = Column(String(36), nullable=True)      # not backfilled (news analysis creates no task)
    verified = Column(Boolean, nullable=True)
    source_tier = Column(Integer, nullable=True)

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
            "platform": self.platform,
            "post_id": self.post_id,
            "label_source": self.label_source,
            "result_id": self.result_id,
            "verified": self.verified,
            "source_tier": self.source_tier,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
