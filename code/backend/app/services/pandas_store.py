"""
Pandas 資料儲存層 - 使用 Parquet 檔案儲存
"""
import functools
import json
import pandas as pd
import numpy as np
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
import uuid
from datetime import datetime

from app.utils.parquet_io import atomic_write_parquet, path_lock, read_parquet_retry
from app.utils.source_tier import TIER_LABELS, tier_of


def _locked(method):
    """同一行程內，知識庫的「讀 → 改 → 寫」一次只跑一個（避免執行緒互蓋 hit_count／新列）。"""
    @functools.wraps(method)
    def wrapper(self, *args, **kwargs):
        with path_lock(self.knowledge_base_path):
            return method(self, *args, **kwargs)
    return wrapper

# label_source 值域 ai|rule|gold|admin；以下三者為確定性標記，寫入即 verified（FR-17 (b)）
DETERMINISTIC_LABEL_SOURCES = frozenset({"rule", "gold", "admin"})

# 舊 parquet 缺欄位時補的預設（spec §6.2；verified 保守補 False，不參與向量命中）
NEW_COLUMN_DEFAULTS: Dict[str, Any] = {
    "source_url": None,
    "label_source": "ai",
    "origin": "web",
    "last_result_id": None,
    "source_tier": None,
    "verified": False,
    "related_discussions": None,
}

KB_COLUMNS = [
    "id", "data_type", "source_url", "raw_content",
    "data_hash", "content_vector",
    "is_risk", "risk_type", "category", "confidence_score",
    "summary", "explanation", "sources", "ai_analysis",
    "created_at", "last_accessed_at", "hit_count",
    "label_source", "origin", "last_result_id",
    "source_tier", "verified", "related_discussions",
]


def _grade_sources_offline(sources: Any) -> List[Dict[str, Any]]:
    """每個來源補上 tier / tier_label（已帶 tier 者直接採用；否則離線計算，不發網路請求）。"""
    graded: List[Dict[str, Any]] = []
    for s in list(sources) if sources is not None else []:
        item = dict(s) if isinstance(s, dict) else {"title": "", "url": str(s or "")}
        tier = item.get("tier")
        try:
            tier = int(tier) if tier is not None else None
        except (TypeError, ValueError):
            tier = None
        if tier not in TIER_LABELS:
            tier = tier_of(item.get("url") or "", item.get("title") or "", offline=True)
        item["tier"] = tier
        item["tier_label"] = TIER_LABELS[tier]
        graded.append(item)
    return graded


def compute_write_gate(
    sources: Any,
    source_url: Optional[str],
    raw_content: str,
    label_source: str = "ai",
    verified: Optional[bool] = None,
) -> Tuple[List[Dict[str, Any]], Optional[int], bool]:
    """
    FR-17 寫入門檻（計算位置在 save_record 內部）。
    回傳 (帶 tier 的 sources, source_tier, verified)。
    source_tier：來源中最高等級 1/2；只有 Tier 3 或無來源 → None。
    """
    src_list = list(sources) if sources is not None else []
    if not src_list and source_url:
        backfill_title = (raw_content or "")[:40]
        if tier_of(source_url, backfill_title, offline=True) in (1, 2):
            src_list = [{"title": backfill_title, "url": source_url}]

    graded = _grade_sources_offline(src_list)
    best = min((s["tier"] for s in graded), default=None)
    source_tier = best if best in (1, 2) else None

    if verified is None:
        verified = (label_source in DETERMINISTIC_LABEL_SOURCES) or source_tier in (1, 2)
    return graded, source_tier, bool(verified)


class PandasStore:
    """使用 Pandas + Parquet 檔案儲存假訊息知識庫"""

    def __init__(self, data_dir: str = "data"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.knowledge_base_path = self.data_dir / "knowledge_base.parquet"

    def _load_knowledge_base(self) -> pd.DataFrame:
        if self.knowledge_base_path.exists():
            df = read_parquet_retry(self.knowledge_base_path)
            # 補上新增欄位（舊資料相容；這就是本次唯一的「遷移」）
            for col, default in NEW_COLUMN_DEFAULTS.items():
                if col not in df.columns:
                    df[col] = default
            df["verified"] = df["verified"].fillna(False).astype(bool)
            return df

        return pd.DataFrame(columns=KB_COLUMNS)

    def _save_knowledge_base(self, df: pd.DataFrame) -> None:
        atomic_write_parquet(df, self.knowledge_base_path)

    # ──────────────────────────────────────────
    # Layer 0: URL 快取（相同網址直接命中）
    # ──────────────────────────────────────────
    @_locked
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
    @_locked
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
    @_locked
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

        # FR-17：只有 verified 列參與向量命中（hash / url 層不過濾）
        verified_mask = (
            df["verified"].fillna(False).astype(bool) if "verified" in df.columns
            else pd.Series(False, index=df.index)
        )
        df_vec = df[df["content_vector"].notna() & verified_mask]
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
    @_locked
    def save_record(
        self,
        data_type: str,
        raw_content: str,
        content_hash: str,
        content_vector: Optional[List[float]] = None,
        ai_result: Optional[Dict[str, Any]] = None,
        source_url: Optional[str] = None,
        label_source: str = "ai",
        verified: Optional[bool] = None,
        origin: str = "web",
        last_result_id: Optional[str] = None,
        related_discussions: Any = None,
    ) -> Dict[str, Any]:
        df = self._load_knowledge_base()

        sources, source_tier, is_verified = compute_write_gate(
            ai_result.get("sources", []) if ai_result else [],
            source_url, raw_content, label_source=label_source, verified=verified,
        )
        # 快取命中讀的是 ai_analysis：同步寫入帶 tier 的來源（不改呼叫端的 dict）
        ai_analysis = {**ai_result, "sources": sources} if ai_result else ai_result
        if related_discussions is not None and not isinstance(related_discussions, str):
            related_discussions = json.dumps(related_discussions, ensure_ascii=False)

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
            "sources": sources,
            "ai_analysis": ai_analysis,
            "created_at": datetime.now(),
            "last_accessed_at": datetime.now(),
            "hit_count": 1,
            "label_source": label_source,
            "origin": origin,
            "last_result_id": last_result_id,
            "source_tier": source_tier,
            "verified": is_verified,
            "related_discussions": related_discussions,
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
