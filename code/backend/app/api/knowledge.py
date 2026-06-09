"""
/api/knowledge - 瀏覽 / 搜尋 knowledge_base.parquet（三層快取裡已查證的內容）。
給前端「資料庫內容」頁面用。
"""
from fastapi import APIRouter, Query

from app.services.pandas_store import PandasStore

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])
_store = PandasStore()


def _s(v) -> str:
    """安全轉字串（處理 numpy / None / NaN）。"""
    if v is None:
        return ""
    if hasattr(v, "item"):
        try:
            v = v.item()
        except Exception:
            pass
    s = str(v)
    return "" if s in ("nan", "None", "NaT") else s


def _sources(v):
    """sources 可能是 list / numpy array / None。"""
    if v is None:
        return []
    if hasattr(v, "tolist"):
        v = v.tolist()
    return v if isinstance(v, list) else []


@router.get("/stats")
def knowledge_stats():
    """資料庫摘要：總筆數 + 各風險類型數量。"""
    df = _store.get_all_records()
    if df.empty:
        return {"total": 0, "by_risk": {}}
    by_risk = df["risk_type"].fillna("UNKNOWN").value_counts().to_dict()
    return {"total": int(len(df)), "by_risk": {str(k): int(v) for k, v in by_risk.items()}}


@router.get("")
def list_knowledge(
    q: str = Query(default="", description="關鍵字（比對內容與摘要）"),
    risk_type: str = Query(default=""),
    limit: int = Query(default=50, le=200),
):
    """列出 / 搜尋已查證內容。"""
    df = _store.get_all_records()
    if df.empty:
        return {"total": 0, "records": []}

    if q.strip():
        ql = q.strip()
        mask = (
            df["raw_content"].astype(str).str.contains(ql, case=False, na=False)
            | df["summary"].astype(str).str.contains(ql, case=False, na=False)
        )
        df = df[mask]
    if risk_type.strip():
        df = df[df["risk_type"].astype(str).str.upper() == risk_type.strip().upper()]

    if "created_at" in df.columns:
        try:
            df = df.sort_values("created_at", ascending=False)
        except Exception:
            pass
    df = df.head(limit)

    records = []
    for _, r in df.iterrows():
        records.append({
            "raw_content": _s(r.get("raw_content")),
            "risk_type": _s(r.get("risk_type")) or "UNKNOWN",
            "category": _s(r.get("category")),
            "summary": _s(r.get("summary")),
            "confidence_score": float(r.get("confidence_score") or 0),
            "sources": _sources(r.get("sources")),
            "source_url": _s(r.get("source_url")),
            "hit_count": int(r.get("hit_count") or 0),
            "created_at": _s(r.get("created_at")),
        })
    return {"total": len(records), "records": records}
