"""
Pandas 資料儲存層 - 使用 Parquet 檔案儲存
"""
import pandas as pd
import numpy as np
from pathlib import Path
from typing import Dict, Any, Optional, List
import uuid
from datetime import datetime


class PandasStore:
    """使用 Pandas + Parquet 檔案儲存假訊息知識庫"""

    def __init__(self, data_dir: str = "data"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.knowledge_base_path = self.data_dir / "knowledge_base.parquet"

    def _load_knowledge_base(self) -> pd.DataFrame:
        if self.knowledge_base_path.exists():
            df = pd.read_parquet(self.knowledge_base_path)
            # 補上新增欄位（舊資料相容）
            if "source_url" not in df.columns:
                df["source_url"] = None
            return df

        return pd.DataFrame(columns=[
            "id", "data_type", "source_url", "raw_content",
            "data_hash", "content_vector",
            "is_risk", "risk_type", "category", "confidence_score",
            "summary", "explanation", "sources", "ai_analysis",
            "created_at", "last_accessed_at", "hit_count",
        ])

    def _save_knowledge_base(self, df: pd.DataFrame) -> None:
        df.to_parquet(self.knowledge_base_path, index=False)

    # ──────────────────────────────────────────
    # Layer 0: URL 快取（相同網址直接命中）
    # ──────────────────────────────────────────
    def find_by_url(self, url: str) -> Optional[Dict[str, Any]]:
        """以來源 URL 查找快取，命中時更新 hit_count。"""
        df = self._load_knowledge_base()
        if df.empty or "source_url" not in df.columns:
            return None

        match = df[df["source_url"] == url]
        if match.empty:
            return None

        idx = match.index[0]
        df.loc[idx, "last_accessed_at"] = datetime.now()
        df.loc[idx, "hit_count"] = df.loc[idx, "hit_count"] + 1
        self._save_knowledge_base(df)
        return match.iloc[0].to_dict()

    # ──────────────────────────────────────────
    # Layer 1: Hash 快取（完全重複攔截）
    # ──────────────────────────────────────────
    def find_by_hash(self, content_hash: str) -> Optional[Dict[str, Any]]:
        """根據 SHA-256 Hash 查找快取。"""
        df = self._load_knowledge_base()
        if df.empty:
            return None

        match = df[df["data_hash"] == content_hash]
        if match.empty:
            return None

        idx = match.index[0]
        df.loc[idx, "last_accessed_at"] = datetime.now()
        df.loc[idx, "hit_count"] = df.loc[idx, "hit_count"] + 1
        self._save_knowledge_base(df)
        return match.iloc[0].to_dict()

    # ──────────────────────────────────────────
    # Layer 2: 向量相似度快取（語義重複攔截）
    # ──────────────────────────────────────────
    def find_similar_by_vector(
        self,
        query_vector: List[float],
        threshold: Optional[float] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        以 cosine similarity 找出語義最相近的快取記錄（numpy 矩陣化，一次算完全部）。
        只有超過 threshold 才算命中。threshold 預設讀取 settings.SIMILARITY_THRESHOLD。
        """
        if threshold is None:
            from app.config import settings
            threshold = settings.SIMILARITY_THRESHOLD
        df = self._load_knowledge_base()
        if df.empty or "content_vector" not in df.columns:
            return None

        df_vec = df[df["content_vector"].notna()]
        if df_vec.empty:
            return None

        q = np.asarray(query_vector, dtype=np.float32)
        q_norm = np.linalg.norm(q)
        if q.size == 0 or q_norm == 0:
            return None

        # 只收維度與查詢向量一致的列（防舊資料混入不同維度的向量）
        indices, rows = [], []
        for idx, v in df_vec["content_vector"].items():
            try:
                a = np.asarray(v, dtype=np.float32)
            except Exception:
                continue
            if a.shape == q.shape:
                indices.append(idx)
                rows.append(a)
        if not rows:
            return None

        matrix = np.stack(rows)                      # (N, dim)
        norms = np.linalg.norm(matrix, axis=1)       # (N,)
        scores = np.full(len(rows), -1.0, dtype=np.float32)
        valid = norms > 0
        scores[valid] = (matrix[valid] @ q) / (norms[valid] * q_norm)

        best = int(np.argmax(scores))
        if float(scores[best]) >= threshold:
            best_idx = indices[best]
            df.loc[best_idx, "last_accessed_at"] = datetime.now()
            df.loc[best_idx, "hit_count"] = df.loc[best_idx, "hit_count"] + 1
            self._save_knowledge_base(df)
            return df.loc[best_idx].to_dict()

        return None

    # ──────────────────────────────────────────
    # 寫入快取
    # ──────────────────────────────────────────
    def save_record(
        self,
        data_type: str,
        raw_content: str,
        content_hash: str,
        content_vector: Optional[List[float]] = None,
        ai_result: Optional[Dict[str, Any]] = None,
        source_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        df = self._load_knowledge_base()

        record = {
            "id": str(uuid.uuid4()),
            "data_type": data_type,
            "source_url": source_url,
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
            "hit_count": 1,
        }

        new_row = pd.DataFrame([record])
        if df.empty:
            df = new_row
        else:
            common_cols = df.columns.intersection(new_row.columns)
            df = pd.concat([df[common_cols], new_row[common_cols]], ignore_index=True)

        self._save_knowledge_base(df)
        return record

    def get_all_records(self) -> pd.DataFrame:
        return self._load_knowledge_base()
