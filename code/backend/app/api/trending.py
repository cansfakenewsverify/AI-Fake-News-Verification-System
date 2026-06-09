"""
/api/trending - return latest trending fact-check records from SQLite.
"""
from fastapi import APIRouter, Depends, BackgroundTasks, Query
from sqlalchemy import case
from sqlalchemy.orm import Session

from app.database_sql import get_sql_db
from app.models.fact_check_record import FactCheckRecord

router = APIRouter(prefix="/api/trending", tags=["trending"])


@router.get("")
def get_trending(
    limit: int = Query(default=10, le=50),
    risk_type: str = Query(default=None),
    db: Session = Depends(get_sql_db),
):
    """Return latest trending records. Verified (MISINFO/SCAM/SAFE) first, then
    unverified (PENDING). Filter by ?risk_type=SCAM|MISINFO|SAFE"""
    q = db.query(FactCheckRecord).filter(FactCheckRecord.is_trending == True)
    if risk_type:
        q = q.filter(FactCheckRecord.risk_type == risk_type.upper())
    # 已查證的(MISINFO/SCAM/SAFE)排前面，未查證(PENDING)排後面
    verified_first = case(
        (FactCheckRecord.risk_type.in_(["MISINFO", "SCAM", "SAFE"]), 0),
        else_=1,
    )
    records = (
        q.order_by(verified_first, FactCheckRecord.created_at.desc())
        .limit(limit)
        .all()
    )
    return {"total": len(records), "records": [r.to_dict() for r in records]}


@router.post("/refresh")
async def trigger_refresh(background_tasks: BackgroundTasks):
    """
    Manually trigger a trending news fetch in background.
    Requires GOOGLE_API_KEY and DEMO_MODE=false to produce real results.
    """
    from app.services.news_fetcher import run_trending_fetch
    # FastAPI BackgroundTasks handles async functions natively
    background_tasks.add_task(run_trending_fetch)
    return {"message": "Trending refresh started. Check /api/trending in a few minutes."}
