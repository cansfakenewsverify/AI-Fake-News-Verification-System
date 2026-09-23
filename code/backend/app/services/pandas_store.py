"""
Pandas 資料儲存層 - 使用 Parquet 檔案儲存
"""
import functools
import json
import pandas as pd
import numpy as np
from pathlib import Path
from typing import Dict, Any, Iterable, Optional, List, Tuple
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
        label_sources: Optional[Iterable[str]] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        以 cosine similarity 找出語義最相近的快取記錄（numpy 矩陣化，一次算完全部）。
        只有超過 threshold 才算命中。threshold 預設讀取 settings.SIMILARITY_THRESHOLD。
        label_sources：只比對這些 label_source 的列（None = 不限）；快取取代用它只找確定性標記。
        """
        if threshold is None:
            from app.config import settings
            threshold = settings.SIMILARITY_THRESHOLD
        df = self._load_knowledge_base()
        scored = _verified_scores(df, query_vector, label_sources)
        if scored is None:
            return None
        indices, scores = scored

        best = int(np.argmax(scores))
        if float(scores[best]) >= threshold:
            best_idx = indices[best]
            df.loc[best_idx, "last_accessed_at"] = datetime.now()
            df.loc[best_idx, "hit_count"] = df.loc[best_idx, "hit_count"] + 1
            self._save_knowledge_base(df)
            return df.loc[best_idx].to_dict()

        return None

    def nearest_verified(
        self,
        query_vector: List[float],
        k: int = 5,
        label_sources: Optional[Iterable[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        最接近的 k 筆已證實列（證據信心用）：不設門檻、不更新 hit_count。每筆只帶 NEIGHBOR_COLUMNS 與
        similarity（cosine），由近到遠；相似度相同時先寫入者在前（與 Postgres 版的 seq 排序一致）。
        """
        df = self._load_knowledge_base()
        scored = _verified_scores(df, query_vector, label_sources)
        if scored is None:
            return []
        indices, scores = scored
        order = np.argsort(-scores, kind="stable")[:max(int(k), 0)]
        neighbours = []
        for i in order:
            row = df.loc[indices[i]]
            item = {col: row.get(col) for col in NEIGHBOR_COLUMNS}
            item["similarity"] = float(scores[i])
            neighbours.append(item)
        return neighbours

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
        record = build_kb_record(
            data_type=data_type, raw_content=raw_content, content_hash=content_hash,
            content_vector=content_vector, ai_result=ai_result, source_url=source_url,
            label_source=label_source, verified=verified, origin=origin,
            last_result_id=last_result_id, related_discussions=related_discussions,
        )
        self._append_records([record])
        return record

    @_locked
    def save_records(self, items: Iterable[Dict[str, Any]]) -> int:
        """
        批次寫入（scripts/ingest_factchecks.py 用）：items 每筆是 save_record 的關鍵字參數，可另帶 now
        （created_at）。一次讀寫 Parquet，不逐筆重寫整個檔案。回傳寫入筆數。
        """
        records = [build_kb_record(**item) for item in items]
        if records:
            self._append_records(records)
        return len(records)

    def _append_records(self, records: List[Dict[str, Any]]) -> None:
        df = self._load_knowledge_base()
        for record in records:
            rd = record.get("related_discussions")
            if rd is not None and not isinstance(rd, str):
                record["related_discussions"] = json.dumps(rd, ensure_ascii=False)
        new_rows = pd.DataFrame(records)
        if df.empty:
            df = new_rows
        else:
            common_cols = df.columns.intersection(new_rows.columns)
            df = pd.concat([df[common_cols], new_rows[common_cols]], ignore_index=True)
        self._save_knowledge_base(df)

    def get_all_records(self) -> pd.DataFrame:
        return self._load_knowledge_base()

    # ──────────────────────────────────────────
    # 知識庫頁查詢（/api/knowledge；只看 verified 列）。Postgres 版在資料庫裡篩選與分頁，行為相同
    # ──────────────────────────────────────────
    def verified_counts(self) -> Tuple[Dict[str, int], int]:
        """（已證實列依 risk_type 的筆數，缺值或空字串記 UNKNOWN；未證實列數）。"""
        df = self._load_knowledge_base()
        if df.empty:
            return {}, 0
        verified = df[df["verified"]]
        risk = verified["risk_type"].map(lambda v: v if isinstance(v, str) and v else "UNKNOWN")
        return {str(k): int(v) for k, v in risk.value_counts().items()}, int(len(df) - len(verified))

    def list_verified(
        self, q: str = "", risk_type: str = "", limit: int = 30, offset: int = 0,
    ) -> Tuple[int, pd.DataFrame]:
        """
        已證實列：q 以字面比對 raw_content／summary（不分大小寫；( [ * 等字元不當 regex），
        risk_type 不分大小寫篩選；created_at 新到舊、id 小到大排序後取 offset:offset+limit。
        回傳（篩選後、分頁前的筆數, 該頁 DataFrame）。
        """
        df = self._load_knowledge_base()
        df = df[df["verified"]] if not df.empty else df
        if df.empty:
            return 0, pd.DataFrame(columns=KB_COLUMNS)
        if q.strip():
            needle = q.strip()
            mask = pd.Series(False, index=df.index)
            for col in ("raw_content", "summary"):
                mask |= df[col].fillna("").astype(str).str.contains(needle, case=False, regex=False, na=False)
            df = df[mask]
        if risk_type.strip():
            df = df[df["risk_type"].astype(str).str.upper() == risk_type.strip().upper()]
        return int(len(df)), newest_first(df).iloc[offset:offset + limit]

    def get_verified_by_ids(self, ids: Iterable[str]) -> pd.DataFrame:
        """指定 id 中已證實的列（/api/knowledge/hot 用）；不存在或未證實的 id 直接略過。"""
        wanted = {str(i) for i in ids if i}
        df = self._load_knowledge_base()
        if df.empty or not wanted:
            return pd.DataFrame(columns=KB_COLUMNS)
        return df[df["verified"] & df["id"].astype(str).isin(wanted)]


# 證據信心（nearest_verified）回傳的欄位
NEIGHBOR_COLUMNS = ["id", "raw_content", "risk_type", "label_source", "source_url", "sources", "summary"]


def _verified_scores(
    df: pd.DataFrame, query_vector: List[float], label_sources: Optional[Iterable[str]] = None,
) -> Optional[Tuple[List[Any], np.ndarray]]:
    """
    （df 的 index, cosine 分數）：只算 verified、有向量、且維度與查詢相同的列（FR-17；防舊資料混入不同維度）。
    label_sources：只比對這些 label_source 的列（None = 不限）。沒有可比對的列或查詢向量為空／零向量 → None。
    """
    if df.empty or "content_vector" not in df.columns:
        return None
    verified_mask = (
        df["verified"].fillna(False).astype(bool) if "verified" in df.columns
        else pd.Series(False, index=df.index)
    )
    if label_sources is not None:
        labels = df["label_source"] if "label_source" in df.columns else pd.Series("ai", index=df.index)
        verified_mask &= labels.fillna("ai").isin(list(label_sources))
    df_vec = df[df["content_vector"].notna() & verified_mask]
    if df_vec.empty:
        return None

    q = np.asarray(query_vector, dtype=np.float32)
    q_norm = np.linalg.norm(q)
    if q.size == 0 or q_norm == 0:
        return None

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
    return indices, scores


def build_kb_record(
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
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """
    一筆知識庫列的內容（本機版與 Postgres 版的 save_record／save_records 共用）：套用寫入門檻
    compute_write_gate，並把帶 tier 的來源同步寫進 ai_analysis（快取命中讀的是 ai_analysis）。
    related_discussions 原樣保留，由各 store 轉成 JSON 字串。
    """
    sources, source_tier, is_verified = compute_write_gate(
        ai_result.get("sources", []) if ai_result else [],
        source_url, raw_content, label_source=label_source, verified=verified,
    )
    ai_analysis = {**ai_result, "sources": sources} if ai_result else ai_result
    has_vector = content_vector is not None and len(content_vector) > 0
    at = now or datetime.now()
    return {
        "id": str(uuid.uuid4()),
        "data_type": data_type,
        "source_url": source_url,
        "raw_content": raw_content,
        "data_hash": content_hash,
        "content_vector": content_vector if has_vector else None,
        "is_risk": ai_result.get("is_risk", False) if ai_result else False,
        "risk_type": ai_result.get("risk_type") if ai_result else None,
        "category": ai_result.get("category") if ai_result else None,
        "confidence_score": ai_result.get("confidence_score") if ai_result else None,
        "summary": ai_result.get("summary", "") if ai_result else "",
        "explanation": ai_result.get("explanation", "") if ai_result else "",
        "sources": sources,
        "ai_analysis": ai_analysis,
        "created_at": at,
        "last_accessed_at": at,
        "hit_count": 1,
        "label_source": label_source,
        "origin": origin,
        "last_result_id": last_result_id,
        "source_tier": source_tier,
        "verified": is_verified,
        "related_discussions": related_discussions,
    }


def newest_first(df: pd.DataFrame) -> pd.DataFrame:
    """created_at 新到舊、id 小到大（多欄排序為穩定排序；缺時間排最後）。分頁不重複不遺漏。"""
    if df.empty:
        return df
    created = df["created_at"] if "created_at" in df.columns else pd.Series(pd.NaT, index=df.index)
    try:
        ts = pd.to_datetime(created, errors="coerce")
    except (TypeError, ValueError):
        ts = created.astype(str)
    ids = df["id"].fillna("").astype(str) if "id" in df.columns else pd.Series("", index=df.index)
    keyed = df.assign(_sort_ts=ts, _sort_id=ids)
    keyed = keyed.sort_values(
        ["_sort_ts", "_sort_id"], ascending=[False, True], na_position="last", kind="mergesort",
    )
    return keyed.drop(columns=["_sort_ts", "_sort_id"])
