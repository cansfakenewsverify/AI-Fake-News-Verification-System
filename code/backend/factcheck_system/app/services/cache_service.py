"""
三層快取服務（Layer 1: Hash, Layer 2: Vector, Layer 3: AI）
"""
import hashlib
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import text
from sqlalchemy.sql import func
from app.models.scam_knowledge_base import ScamKnowledgeBase
from app.config import settings


class CacheService:
    """快取服務類別"""
    
    @staticmethod
    def generate_hash(content: str) -> str:
        """
        Layer 1: 產生 SHA-256 指紋
        
        Args:
            content: 原始內容
            
        Returns:
            SHA-256 雜湊值
        """
        return hashlib.sha256(content.encode('utf-8')).hexdigest()
    
    @staticmethod
    def check_hash_cache(db: Session, content_hash: str) -> Optional[ScamKnowledgeBase]:
        """
        Layer 1: 檢查 Hash 快取（完全重複攔截）
        
        Args:
            db: 資料庫 Session
            content_hash: 內容雜湊值
            
        Returns:
            如果找到完全相同的記錄，返回該記錄；否則返回 None
        """
        record = db.query(ScamKnowledgeBase).filter(
            ScamKnowledgeBase.data_hash == content_hash
        ).first()
        
        if record:
            # 更新存取時間和計數
            record.last_accessed_at = func.now()
            record.hit_count += 1
            db.commit()
        
        return record
    
    @staticmethod
    def check_vector_cache(
        db: Session,
        content_vector: list,
        threshold: float = None
    ) -> Optional[ScamKnowledgeBase]:
        """
        Layer 2: 檢查向量快取（變種攻擊攔截）
        
        Args:
            db: 資料庫 Session
            content_vector: 內容向量（768 維）
            threshold: 相似度門檻（預設使用設定值）
            
        Returns:
            如果找到相似度超過門檻的記錄，返回該記錄；否則返回 None
        """
        if threshold is None:
            threshold = settings.SIMILARITY_THRESHOLD
        
        # 使用 pgvector 的 cosine similarity 查詢
        query = text("""
            SELECT id, 
                   1 - (content_vector <=> :vector::vector) as similarity
            FROM scam_knowledge_base
            WHERE content_vector IS NOT NULL
            AND 1 - (content_vector <=> :vector::vector) >= :threshold
            ORDER BY content_vector <=> :vector::vector
            LIMIT 1
        """)
        
        result = db.execute(
            query,
            {
                "vector": str(content_vector),
                "threshold": threshold
            }
        ).first()
        
        if result:
            record_id = result[0]
            record = db.query(ScamKnowledgeBase).filter(
                ScamKnowledgeBase.id == record_id
            ).first()
            
            if record:
                # 更新存取時間和計數
                record.last_accessed_at = func.now()
                record.hit_count += 1
                db.commit()
            
            return record
        
        return None
    
    @staticmethod
    def save_to_cache(
        db: Session,
        data_type: str,
        raw_content: str,
        content_hash: str,
        content_vector: Optional[list] = None,
        ai_result: Optional[Dict[str, Any]] = None
    ) -> ScamKnowledgeBase:
        """
        將分析結果存入快取
        
        Args:
            db: 資料庫 Session
            data_type: 資料類型（URL, TEXT, IMAGE, VIDEO）
            raw_content: 原始內容
            content_hash: 內容雜湊值
            content_vector: 內容向量（可選）
            ai_result: AI 分析結果（可選）
            
        Returns:
            建立的記錄物件
        """
        record = ScamKnowledgeBase(
            data_type=data_type,
            raw_content=raw_content,
            data_hash=content_hash,
            content_vector=content_vector,
            is_risk=ai_result.get("is_risk", False) if ai_result else False,
            risk_type=ai_result.get("risk_type") if ai_result else None,
            category=ai_result.get("category") if ai_result else None,
            confidence_score=ai_result.get("confidence_score") if ai_result else None,
            ai_analysis=ai_result
        )
        
        db.add(record)
        db.commit()
        db.refresh(record)
        
        return record

