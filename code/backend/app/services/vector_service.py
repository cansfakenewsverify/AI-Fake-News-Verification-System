"""
Vector service - embedding generation for the Layer 2 semantic cache.
Similarity search itself lives in PandasStore.find_similar_by_vector.
"""
from typing import List

from app.services.ai_service import AIService


class VectorService:
    """Text -> embedding vector (dimension follows settings.VECTOR_DIMENSION, 1536)."""

    def __init__(self):
        self.ai_service = AIService()

    def vectorize_content(self, content: str) -> List[float]:
        """Convert text into an embedding vector. Empty list = vector layer disabled."""
        return self.ai_service.generate_embedding(content)
