"""
/api/trending - return latest trending fact-check records from SQLite.
"""
from fastapi import APIRouter, Depends, BackgroundTasks, Query
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
    """Return latest trending news records. Filter by ?risk_type=SCAM|MISINFO|SAFE"""
    q = db.query(FactCheckRecord).filter(FactCheckRecord.is_trending == True)
    if risk_type:
        q = q.filter(FactCheckRecord.risk_type == risk_type.upper())
    records = q.order_by(FactCheckRecord.created_at.desc()).limit(limit).all()
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
