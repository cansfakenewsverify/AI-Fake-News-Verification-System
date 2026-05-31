"""
Vector service - embedding generation and similarity search.

Note: PostgreSQL-specific dependencies (sqlalchemy text, pgvector model) are
lazy-imported inside methods so this module loads cleanly with just SQLite + Pandas.
"""
from typing import List, Dict, Any
from app.services.ai_service import AIService
from app.config import settings


class VectorService:
    """Vectorization + similarity search."""

    def __init__(self):
        self.ai_service = AIService()

    def vectorize_content(self, content: str) -> List[float]:
        """Convert text into 768-dim embedding vector."""
        return self.ai_service.generate_embedding(content)

    # ── PostgreSQL methods (lazy-imported) ───────────────────────
    def find_similar_news(
        self,
        db: Any,
        query_vector: List[float],
        top_n: int = 5,
        threshold: float = None,
    ) -> List[Dict]:
        """PostgreSQL+pgvector cosine search. Only used in pgvector path."""
        from sqlalchemy import text

        if threshold is None:
            threshold = 0.7

        query = text("""
            SELECT
                id,
                raw_content,
                created_at,
                ai_analysis->>'summary' as summary,
                1 - (content_vector <=> :vector::vector) as similarity
            FROM scam_knowledge_base
            WHERE content_vector IS NOT NULL
            AND 1 - (content_vector <=> :vector::vector) >= :threshold
            ORDER BY content_vector <=> :vector::vector
            LIMIT :top_n
        """)

        results = db.execute(query, {
            "vector": str(query_vector),
            "threshold": threshold,
            "top_n": top_n,
        }).fetchall()

        return [{
            "id": str(row[0]),
            "content": row[1],
            "date": row[2].isoformat() if row[2] else None,
            "summary": row[3],
            "similarity": float(row[4]),
        } for row in results]

    def build_timeline(self, db: Any, query_vector: List[float], top_n: int = 10) -> List[Dict]:
        """PostgreSQL+pgvector timeline. Only used in pgvector path."""
        similar_news = self.find_similar_news(db, query_vector, top_n=top_n)
        similar_news.sort(key=lambda x: x["date"] if x["date"] else "", reverse=False)
        return similar_news
