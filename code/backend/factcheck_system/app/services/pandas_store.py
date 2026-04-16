"""
Pandas 資料儲存層 - 取代 PostgreSQL，使用 Parquet 檔案儲存
"""
import pandas as pd
from pathlib import Path
from typing import Dict, Any, Optional, List
import uuid
from datetime import datetime
import hashlib


class PandasStore:
    """使用 Pandas + Parquet 檔案儲存假訊息知識庫"""
    
    def __init__(self, data_dir: str = "data"):
        """
        初始化儲存層
        
        Args:
            data_dir: 資料目錄路徑
        """
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.knowledge_base_path = self.data_dir / "knowledge_base.parquet"
        self.tasks_path = self.data_dir / "tasks.parquet"
    
    def _load_knowledge_base(self) -> pd.DataFrame:
        """載入知識庫 DataFrame"""
        if self.knowledge_base_path.exists():
            return pd.read_parquet(self.knowledge_base_path)
        
        # 建立空的 DataFrame（對應原本的 Schema）
        return pd.DataFrame(columns=[
            "id",
            "data_type",
            "raw_content",
            "data_hash",
            "content_vector",
            "is_risk",
            "risk_type",
            "category",
            "confidence_score",
            "summary",
            "explanation",
            "sources",
            "ai_analysis",
            "created_at",
            "last_accessed_at",
            "hit_count"
        ])
    
    def _save_knowledge_base(self, df: pd.DataFrame) -> None:
        """儲存知識庫 DataFrame"""
        df.to_parquet(self.knowledge_base_path, index=False)
    
    def find_by_hash(self, content_hash: str) -> Optional[Dict[str, Any]]:
        """
        Layer 1: 根據 Hash 查找（完全重複攔截）
        
        Args:
            content_hash: SHA-256 雜湊值
            
        Returns:
            如果找到，返回記錄字典；否則返回 None
        """
        df = self._load_knowledge_base()
        
        if df.empty:
            return None
        
        match = df[df["data_hash"] == content_hash]
        
        if not match.empty:
            record = match.iloc[0].to_dict()
            # 更新存取時間和計數
            df.loc[df["data_hash"] == content_hash, "last_accessed_at"] = datetime.now()
            df.loc[df["data_hash"] == content_hash, "hit_count"] = df.loc[df["data_hash"] == content_hash, "hit_count"] + 1
            self._save_knowledge_base(df)
            return record
        
        return None
    
    def find_similar_by_vector(
        self,
        query_vector: List[float],
        threshold: float = 0.95,
        top_n: int = 1
    ) -> Optional[Dict[str, Any]]:
        """
        Layer 2: 根據向量相似度查找（變種攔截）
        
        注意：簡化版，實際應該使用向量資料庫（如 pgvector）
        這裡先用簡單的歐幾里得距離作為示範
        
        Args:
            query_vector: 查詢向量
            threshold: 相似度門檻
            top_n: 返回前 N 筆
            
        Returns:
            如果找到相似記錄，返回最相似的一筆；否則返回 None
        """
        df = self._load_knowledge_base()
        
        if df.empty or "content_vector" not in df.columns:
            return None
        
        # 過濾出有向量的記錄
        df_with_vector = df[df["content_vector"].notna()]
        
        if df_with_vector.empty:
            return None
        
        # 簡化版：計算歐幾里得距離（實際應該用 cosine similarity）
        # 這裡先跳過，因為需要將向量從字串/列表轉換
        # 為了示範，我們先返回 None（表示沒有找到相似記錄）
        # 實際專案中，應該使用專門的向量資料庫
        
        return None
    
    def save_record(
        self,
        data_type: str,
        raw_content: str,
        content_hash: str,
        content_vector: Optional[List[float]] = None,
        ai_result: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        儲存分析結果
        
        Args:
            data_type: 資料類型（URL, TEXT, IMAGE, VIDEO）
            raw_content: 原始內容
            content_hash: 內容雜湊值
            content_vector: 內容向量（可選）
            ai_result: AI 分析結果（可選）
            
        Returns:
            儲存的記錄字典
        """
        df = self._load_knowledge_base()
        
        record = {
            "id": str(uuid.uuid4()),
            "data_type": data_type,
            "raw_content": raw_content,
            "data_hash": content_hash,
            "content_vector": content_vector if content_vector else None,
            "is_risk": ai_result.get("is_risk", False) if ai_result else False,
            "risk_type": ai_result.get("risk_type") if ai_result else None,
            "category": ai_result.get("category") if ai_result else None,
            "confidence_score": ai_result.get("confidence_score") if ai_result else None,
            "summary": ai_result.get("summary", "") if ai_result else "",
            "explanation": ai_result.get("explanation", "") if ai_result else "",
            "sources": ai_result.get("sources", []) if ai_result else [],
            "ai_analysis": ai_result,
            "created_at": datetime.now(),
            "last_accessed_at": datetime.now(),
            "hit_count": 1
        }
        
        # 新增記錄到 DataFrame
        new_row = pd.DataFrame([record])
        # 確保欄位一致，避免 FutureWarning
        if df.empty:
            df = new_row
        else:
            # 只保留兩邊都有的欄位
            common_cols = df.columns.intersection(new_row.columns)
            df = pd.concat([df[common_cols], new_row[common_cols]], ignore_index=True)
        
        # 儲存
        self._save_knowledge_base(df)
        
        return record
    
    def get_all_records(self) -> pd.DataFrame:
        """取得所有記錄"""
        return self._load_knowledge_base()

