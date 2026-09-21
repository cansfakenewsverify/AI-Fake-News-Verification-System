"""
/api/knowledge - 瀏覽 / 搜尋 knowledge_base.parquet（三層快取裡已查證的內容）。
給前端「知識庫」頁（S4）用。

- 只回 verified == True 的列（FR-17）；verified=false 列仍在 Parquet 供稽核，但不出現、不計數。
- 關鍵字比對一律字面比對（regex=False）：q 含 ( [ * 等字元不得 500（FR-07 驗收 1）。
- offset 分頁：排序 created_at desc、id asc，同一時間寫入的列順序也固定，分頁不重複不遺漏。
- sources 只留 Tier 1／2（FR-16），raw_content 只回前 500 字（spec §9 隱私）。
- /hot：最近 7 天的熱門查證（查證紀錄 × 時間衰減），同樣只回 verified 列。
"""
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import pandas as pd
from fastapi import APIRouter, Query

from app.services import hot_claims
from app.services.store_factory import get_knowledge_store, get_task_store
from app.utils.source_tier import (
    ALWAYS_TIER3_DOMAINS,
    COFACTS_DOMAINS,
    TIER_LABELS,
    _host_matches,
    _host_of,
    tier_of,
)

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])
# 本機 PandasStore 或 Supabase 的 PgKnowledgeStore（store_factory）；兩者 get_all_records() 回傳同形狀的
# DataFrame。端點是同步 def（FastAPI 丟 threadpool），阻塞讀取不卡 event loop。
_store = get_knowledge_store()
# 熱門查證讀查證紀錄（本機 TaskStore 或 PgTaskStore）；測試以 monkeypatch 換掉
_task_store = get_task_store()

RAW_CONTENT_MAX = 500
_VERDICT_TYPES = ("RUMOR", "NOT_RUMOR")
# stats.counts 四格；UNKNOWN／UNVERIFIABLE／其他（含缺值）一律併入 unverifiable
_COUNT_KEYS = {"SCAM": "scam", "MISINFO": "misinfo", "SAFE": "safe"}


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


def _num(v: Any, cast=float):
    """數值欄位的 None / NaN → 0（JSON 不接受 NaN，否則整頁 500）。"""
    try:
        return cast(v) if v is not None and not pd.isna(v) else cast(0)
    except (TypeError, ValueError):
        return cast(0)


def _tier_value(v: Any) -> Optional[int]:
    try:
        tier = int(v)
    except (TypeError, ValueError):
        return None
    return tier if tier in TIER_LABELS else None


def _offline_tier(item: Dict[str, Any]) -> int:
    """
    以 tier_of(..., offline=True) 重新分級（不發網路請求；TIER1_DOMAINS 或標題規則變動即時生效）。
    唯一例外是 Cofacts：離線模式查不到有無回覆、一律回 3；該項若已帶線上查詢或清洗腳本
    寫入的結論（tier == 1 或 verdict 為 RUMOR／NOT_RUMOR）則沿用，與 FR-17「已帶 tier 者採用」一致。
    """
    url = _s(item.get("url"))
    title = _s(item.get("title"))
    host = _host_of(url)
    if _host_matches(host, COFACTS_DOMAINS) and not _host_matches(host, ALWAYS_TIER3_DOMAINS):
        if _tier_value(item.get("tier")) == 1 or item.get("verdict") in _VERDICT_TYPES:
            return 1
    return tier_of(url, title, offline=True)


def _public_sources(v) -> List[Dict[str, Any]]:
    """只留 Tier 1／2，每項附 tier / tier_label；parquet 補出來的 None 鍵去掉。"""
    out: List[Dict[str, Any]] = []
    for raw in _sources(v):
        if isinstance(raw, dict):
            item = {k: val for k, val in raw.items() if val is not None}
        else:
            item = {"title": "", "url": _s(raw)}
        tier = _offline_tier(item)
        if tier in (1, 2):
            item["tier"] = tier
            item["tier_label"] = TIER_LABELS[tier]
            out.append(item)
    return out


def _verified_only(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "verified" not in df.columns:
        return df.iloc[0:0]
    return df[df["verified"].fillna(False).astype(bool)]


def _newest_first(df: pd.DataFrame) -> pd.DataFrame:
    """created_at desc、id asc（多欄排序為穩定排序；缺時間排最後）。"""
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


def _count_key(risk_type: Any) -> str:
    return _COUNT_KEYS.get(_s(risk_type).strip().upper(), "unverifiable")


@router.get("/stats")
def knowledge_stats():
    """知識庫摘要：只計 verified=true 列；counts 四格加總 = total；unverified_count 供稽核（S4 不顯示）。"""
    df = _store.get_all_records()
    verified = _verified_only(df)
    counts = {"scam": 0, "misinfo": 0, "safe": 0, "unverifiable": 0}
    by_risk: Dict[str, int] = {}
    if not verified.empty:
        risk = verified["risk_type"] if "risk_type" in verified.columns else pd.Series(None, index=verified.index)
        by_risk = {str(k): int(v) for k, v in risk.fillna("UNKNOWN").value_counts().to_dict().items()}
        for value in risk:
            counts[_count_key(value)] += 1
    return {
        "total": int(len(verified)),
        "by_risk": by_risk,
        "counts": counts,
        "unverified_count": int(len(df) - len(verified)),
    }


@router.get("")
def list_knowledge(
    q: str = Query(default="", description="關鍵字（字面比對內容與摘要，不分大小寫）"),
    risk_type: str = Query(default=""),
    limit: int = Query(default=30, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    """列出 / 搜尋已證實的知識庫內容（offset 分頁；total 為篩選後、分頁前的筆數）。"""
    df = _verified_only(_store.get_all_records())
    if df.empty:
        return {"total": 0, "records": []}

    if q.strip():
        ql = q.strip()
        mask = pd.Series(False, index=df.index)
        for col in ("raw_content", "summary"):
            if col in df.columns:
                mask |= df[col].fillna("").astype(str).str.contains(ql, case=False, regex=False, na=False)
        df = df[mask]
    if risk_type.strip():
        df = df[df["risk_type"].astype(str).str.upper() == risk_type.strip().upper()]

    total = int(len(df))
    page = _newest_first(df).iloc[offset:offset + limit]
    return {"total": total, "records": [_public_record(r) for _, r in page.iterrows()]}


@router.get("/hot")
def hot_knowledge(limit: int = Query(default=10, ge=1, le=50)):
    """
    熱門查證（熱門頁「本站熱門查證」分頁）：最近 7 天被查證的次數，依時間衰減排序
    （演算法見 app/services/hot_claims.py）。快取命中也算一次查證。
    只列已證實的列，與 /api/knowledge 同一份欄位，另加 recent_24h／recent_7d／last_seen_at；
    尚未證實的內容是使用者送出的原文，不公開。
    """
    now = datetime.utcnow()
    ranked = hot_claims.rank(
        _task_store.recent_kb_refs(now - timedelta(days=hot_claims.WINDOW_DAYS)), now,
    )
    body = {
        "window_days": hot_claims.WINDOW_DAYS,
        "half_life_hours": hot_claims.HALF_LIFE_HOURS,
        "total": 0,
        "records": [],
    }
    if not ranked:
        return body

    df = _verified_only(_store.get_all_records())
    if df.empty or "id" not in df.columns:
        return body
    ids = {item["kb_id"] for item in ranked}
    rows = {_s(r.get("id")): r for _, r in df[df["id"].astype(str).isin(ids)].iterrows()}

    records = []
    for item in ranked:
        row = rows.get(item["kb_id"])
        if row is None:          # 未證實、已刪除或不在這個資料庫
            continue
        record = _public_record(row)
        record.update({
            "recent_24h": item["count_24h"],
            "recent_7d": item["count_window"],
            "last_seen_at": item["last_seen"].isoformat(),
        })
        records.append(record)
        if len(records) >= limit:
            break
    body.update({"total": len(records), "records": records})
    return body


def _public_record(r) -> Dict[str, Any]:
    """知識庫列 → 對外欄位（/api/knowledge 與 /api/knowledge/hot 共用）。"""
    sources = _public_sources(r.get("sources"))
    return {
        "id": _s(r.get("id")),
        "data_type": _s(r.get("data_type")),
        "raw_content": _s(r.get("raw_content"))[:RAW_CONTENT_MAX],
        "risk_type": _s(r.get("risk_type")) or "UNKNOWN",
        "category": _s(r.get("category")),
        "summary": _s(r.get("summary")),
        "confidence_score": _num(r.get("confidence_score")),
        "sources": sources,
        # 與 sources 同一份分級結果：其中最高等級（1 或 2），無 Tier 1／2 來源為 null
        "source_tier": min((s["tier"] for s in sources), default=None),
        "source_url": _s(r.get("source_url")),
        "label_source": _s(r.get("label_source")) or "ai",
        "last_result_id": _s(r.get("last_result_id")) or None,
        "hit_count": _num(r.get("hit_count"), int),
        "created_at": _s(r.get("created_at")),
    }
