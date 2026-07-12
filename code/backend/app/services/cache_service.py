"""
Cache utilities.

The SQLite+Pandas pipeline only needs content fingerprinting here;
the actual cache layers live in PandasStore (URL / hash / vector).
"""
import hashlib


class CacheService:

    @staticmethod
    def generate_hash(content: str) -> str:
        """SHA-256 fingerprint of the content."""
        return hashlib.sha256(content.encode("utf-8")).hexdigest()
