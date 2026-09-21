"""
/api/trending - return latest trending fact-check records from SQLite.
"""
from fastapi import APIRouter, Depends, BackgroundTasks, Query
from sqlalchemy import case
from sqlalchemy.orm import Session

from app.database_sql import get_sql_db
from app.models.fact_check_record import FactCheckRecord
from app.utils.admin_auth import require_admin

router = APIRouter(prefix="/api/trending", tags=["trending"])

# Cofacts 是「網友投稿的個人 LINE 對話/截圖」，雖被查核為謠言(RUMOR)，但不像
# 熱門新聞(標題常是對話碎片)。故在熱門頁限量並排到真新聞(MyGoPen/TFC/Google)
# 之後，避免單一來源洗版。
_COFACTS_MAX = 3


def _is_cofacts(rec: FactCheckRecord) -> bool:
    return bool(rec.source_url and "cofacts.tw" in rec.source_url)


@router.get("")
def get_trending(
    limit: int = Query(default=10, ge=1, le=50),
    risk_type: str = Query(default=None),
    db: Session = Depends(get_sql_db),
):
    """Return latest trending records. Real news (MyGoPen/TFC/Google) first,
    Cofacts user-submitted messages capped at _COFACTS_MAX and pushed to the end.
    Within each group: verified (MISINFO/SCAM/SAFE) first, then PENDING.
    Filter by ?risk_type=SCAM|MISINFO|SAFE"""
    q = db.query(FactCheckRecord).filter(FactCheckRecord.is_trending == True)
    if risk_type:
        q = q.filter(FactCheckRecord.risk_type == risk_type.upper())
    # 已查證的(MISINFO/SCAM/SAFE)排前面，未查證(PENDING)排後面
    verified_first = case(
        (FactCheckRecord.risk_type.in_(["MISINFO", "SCAM", "SAFE"]), 0),
        else_=1,
    )
    # 多抓一些，後面再做來源分流(真新聞優先、Cofacts 限量排尾)
    rows = (
        q.order_by(verified_first, FactCheckRecord.created_at.desc())
        .limit(limit * 4)
        .all()
    )
    news = [r for r in rows if not _is_cofacts(r)]
    cofacts = [r for r in rows if _is_cofacts(r)][:_COFACTS_MAX]
    n_news = max(limit - len(cofacts), 0)
    records = (news[:n_news] + cofacts)[:limit]
    return {"total": len(records), "records": [r.to_dict() for r in records]}


@router.post("/refresh", dependencies=[Depends(require_admin)])
async def trigger_refresh(
    background_tasks: BackgroundTasks,
    analyze: bool = Query(default=True, description="false = 只抓查核文章並寫入知識庫，不呼叫判讀模型"),
    per_feed: int = Query(default=4, ge=1, le=25, description="每個 RSS 來源取幾篇"),
):
    """
    Manually trigger a trending news fetch in background.
    Requires X-Admin-Token (spec §5.2 / §5.6: 401 unauthorized, 403 admin_disabled).
    Requires a configured AI provider and DEMO_MODE=false to produce real results.
    ?analyze=false skips the AI step: fact-check claims are indexed (embedding only), nothing is judged.
    """
    from app.services.news_fetcher import run_trending_fetch
    # FastAPI BackgroundTasks handles async functions natively
    background_tasks.add_task(run_trending_fetch, analyze_pending=analyze, per_feed=per_feed)
    return {
        "message": "Trending refresh started. Check /api/trending in a few minutes.",
        "analyze": analyze,
        "per_feed": per_feed,
    }
