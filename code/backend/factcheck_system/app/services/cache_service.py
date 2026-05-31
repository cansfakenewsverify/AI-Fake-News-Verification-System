"""
Cache utilities.

The active SQLite+Pandas path only uses generate_hash().
The PostgreSQL methods below are kept for future pgvector upgrade
and lazy-import their dependencies.
"""
import hashlib
from typing import Optional, Dict, Any


class CacheService:

    @staticmethod
    def generate_hash(content: str) -> str:
        """SHA-256 fingerprint of the content."""
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    # ── PostgreSQL methods (require pgvector) - lazy imported ────────
    @staticmethod
    def check_hash_cache(db, content_hash: str):
        from app.models.scam_knowledge_base import ScamKnowledgeBase
        from sqlalchemy.sql import func

        record = db.query(ScamKnowledgeBase).filter(
            ScamKnowledgeBase.data_hash == content_hash
        ).first()
        if record:
            record.last_accessed_at = func.now()
            record.hit_count += 1
            db.commit()
        return record

    @staticmethod
    def check_vector_cache(db, content_vector: list, threshold: float = 0.95):
        from app.models.scam_knowledge_base import ScamKnowledgeBase
        from sqlalchemy import text
        from sqlalchemy.sql import func

        query = text("""
            SELECT id, 1 - (content_vector <=> :vector::vector) as similarity
            FROM scam_knowledge_base
            WHERE content_vector IS NOT NULL
            AND 1 - (content_vector <=> :vector::vector) >= :threshold
            ORDER BY content_vector <=> :vector::vector
            LIMIT 1
        """)
        result = db.execute(query, {"vector": str(content_vector), "threshold": threshold}).first()
        if result:
            record = db.query(ScamKnowledgeBase).filter(
                ScamKnowledgeBase.id == result[0]
            ).first()
            if record:
                record.last_accessed_at = func.now()
                record.hit_count += 1
                db.commit()
            return record
        return None

    @staticmethod
    def save_to_cache(
        db,
        data_type: str,
        raw_content: str,
        content_hash: str,
        content_vector: Optional[list] = None,
        ai_result: Optional[Dict[str, Any]] = None,
    ):
        from app.models.scam_knowledge_base import ScamKnowledgeBase

        record = ScamKnowledgeBase(
            data_type=data_type,
            raw_content=raw_content,
            data_hash=content_hash,
            content_vector=content_vector,
            is_risk=ai_result.get("is_risk", False) if ai_result else False,
            risk_type=ai_result.get("risk_type") if ai_result else None,
            category=ai_result.get("category") if ai_result else None,
            confidence_score=ai_result.get("confidence_score") if ai_result else None,
            ai_analysis=ai_result,
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        return record
