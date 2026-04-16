"""
向量服務 - 處理向量化與相似度搜尋
"""
from typing import List, Dict, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.models.scam_knowledge_base import ScamKnowledgeBase
from app.services.ai_service import AIService
from app.config import settings


class VectorService:
    """向量服務類別"""
    
    def __init__(self):
        self.ai_service = AIService()
    
    def vectorize_content(self, content: str) -> List[float]:
        """
        將內容向量化
        
        Args:
            content: 要向量化的內容
            
        Returns:
            768 維向量
        """
        return self.ai_service.generate_embedding(content)
    
    def find_similar_news(
        self,
        db: Session,
        query_vector: List[float],
        top_n: int = 5,
        threshold: float = None
    ) -> List[Dict]:
        """
        找出語義相似的新聞（用於時間軸生成）
        
        Args:
            db: 資料庫 Session
            query_vector: 查詢向量
            top_n: 返回前 N 筆
            threshold: 相似度門檻（可選）
            
        Returns:
            相似新聞列表（包含標題、時間、相似度分數）
        """
        if threshold is None:
            threshold = 0.7  # 時間軸搜尋使用較寬鬆的門檻
        
        # 使用 pgvector 的 cosine similarity 查詢
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
        
        results = db.execute(
            query,
            {
                "vector": str(query_vector),
                "threshold": threshold,
                "top_n": top_n
            }
        ).fetchall()
        
        similar_news = []
        for row in results:
            similar_news.append({
                'id': str(row[0]),
                'content': row[1],
                'date': row[2].isoformat() if row[2] else None,
                'summary': row[3],
                'similarity': float(row[4])
            })
        
        return similar_news
    
    def build_timeline(
        self,
        db: Session,
        query_vector: List[float],
        top_n: int = 10
    ) -> List[Dict]:
        """
        建立事件時間軸
        
        Args:
            db: 資料庫 Session
            query_vector: 查詢向量
            top_n: 時間軸新聞數量
            
        Returns:
            按時間排序的新聞列表
        """
        similar_news = self.find_similar_news(db, query_vector, top_n=top_n)
        
        # 按時間排序
        similar_news.sort(key=lambda x: x['date'] if x['date'] else '', reverse=False)
        
        return similar_news

