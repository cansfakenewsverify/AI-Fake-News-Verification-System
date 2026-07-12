"""
/api/threads — Threads 查核機器人的狀態與手動觸發（測試用）。

正式運作靠排程（.env 設 ENABLE_THREADS_BOT=true）；
開發時可用 POST /api/threads/poll 立刻跑一輪，不用等排程。
"""
from fastapi import APIRouter, BackgroundTasks

from app.config import settings
from app.services.threads_service import ThreadsService
from app.workers.threads_bot import run_threads_poll, _load_state

router = APIRouter(prefix="/api/threads", tags=["threads"])


@router.get("/status")
def threads_status():
    """機器人設定狀態 + 已回覆數量。"""
    svc = ThreadsService()
    state = _load_state()
    return {
        "enabled": settings.ENABLE_THREADS_BOT,
        "configured": svc.available,
        "poll_minutes": settings.THREADS_POLL_MINUTES,
        "replied_count": len(state.get("replied_ids", [])),
    }


@router.post("/poll")
async def trigger_poll(background_tasks: BackgroundTasks):
    """手動觸發一輪 mentions 輪詢（背景執行，馬上回應）。"""
    svc = ThreadsService()
    if not svc.available:
        return {
            "started": False,
            "message": "未設定 THREADS_ACCESS_TOKEN / THREADS_USER_ID（見 .env.example）",
        }
    background_tasks.add_task(run_threads_poll)
    return {"started": True, "message": "輪詢已在背景開始，結果見後端 log 與 /api/threads/status"}
