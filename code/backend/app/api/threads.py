"""
/api/threads — Threads 查核機器人的狀態與手動觸發（測試用）。

正式運作靠排程（.env 設 ENABLE_THREADS_BOT=true）；
開發時可用 POST /api/threads/poll 立刻跑一輪，不用等排程。
poll 授權順序（spec §5.2、§5.6）：THREADS_MODE=off → 200 threads_disabled（不驗 token）；
其餘模式才需要 X-Admin-Token。
"""
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Header

from app.config import settings
from app.services.threads_service import ThreadsService
from app.utils.admin_auth import require_admin
from app.workers.threads_bot import run_threads_poll, _load_state

router = APIRouter(prefix="/api/threads", tags=["threads"])


def poll_allowed(x_admin_token: Optional[str] = Header(default=None)) -> bool:
    """False = THREADS_MODE=off（直接回 threads_disabled）；否則驗 X-Admin-Token，失敗丟 401／403。"""
    if settings.threads_mode_effective == "off":
        return False
    require_admin(x_admin_token)
    return True


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
async def trigger_poll(background_tasks: BackgroundTasks, allowed: bool = Depends(poll_allowed)):
    """手動觸發一輪 mentions 輪詢（背景執行，馬上回應）。"""
    if not allowed:
        return {"started": False, "code": "threads_disabled"}
    svc = ThreadsService()
    if not svc.available:
        return {
            "started": False,
            "message": "未設定 THREADS_ACCESS_TOKEN / THREADS_USER_ID（見 .env.example）",
        }
    background_tasks.add_task(run_threads_poll)
    return {"started": True, "message": "輪詢已在背景開始，結果見後端 log 與 /api/threads/status"}
