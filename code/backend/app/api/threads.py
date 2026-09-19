"""
/api/threads — Threads 查核機器人的狀態、回覆紀錄與手動觸發（spec §5.2、§5.3、§5.6、§5.7；T-10）。

- GET  /status   公開唯讀：模式、設定、上次輪詢、token 期限、每日回覆數、dev_mode_notice（不含 token 本體）
- GET  /replies  公開唯讀：data/threads_replies.jsonl 倒序（最新在前），limit 1–50
- POST /poll     管理端點，非同步啟動一輪（spec §5.2），判斷順序固定：
    1. THREADS_MODE=off                      → 200 {started:false, code:"threads_disabled"}（不驗 token，B-20 順序）
    2. X-Admin-Token 缺／錯 → 401 unauthorized；ADMIN_TOKEN 為空 → 403 admin_disabled
    3. 客戶端不可用（live 沒 token、token 過期）→ 200 {started:false, code:"threads_not_configured"|"token_invalid", detail}
       （spec 未列此情況；回 202 會讓腳本空等 last_poll_at，故明確回「沒開始」）
    4. 已有一輪進行中（同行程 asyncio.Lock 或 data/threads_poll.lock）→ 409 {detail, code:"poll_in_progress"}
    5. 否則以 BackgroundTasks 啟動 → 202 {started:true}

排程（app/main.py）與本端點都跑 run_poll_quietly → run_threads_poll，共用 T-09 的兩層鎖；
檢查到啟動之間若被另一輪搶先，PollInProgress 在背景被吞下（threads_bot 已記一行 warning，不丟 traceback）。
last_error 由輪詢寫入 state、status 只讀；例外：客戶端 invalid_reason 非空（token 過期）時 status 直接回
token_invalid，尚未輪詢也看得到（S-11 threads_mode_invalid 徽章）。
backoff（spec §7.10；T-13）：HTTP 429／401／連續 3 輪 5xx 時輪詢把 backoff_until（UTC ISO）與 last_error
（rate_limited／token_invalid／transient_error…）寫進 state，status 原樣回傳；backoff 未到期時 POST /poll 仍回 202，
但背景那一輪整輪略過（不打 API、last_poll_at 不變）——scripts/test_threads_bot.py --poll 會讀 status 提示「輪詢暫停中」。

端點皆為同步 def：只讀本機小檔（state／jsonl／token 檔），交給 threadpool，不卡 event loop。
"""
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Header, Query
from fastapi.responses import JSONResponse

from app.config import settings
from app.services import threads_state
from app.services.threads_service import get_threads_client
from app.utils.admin_auth import require_admin
from app.workers.threads_bot import PollInProgress, poll_in_progress, run_threads_poll

router = APIRouter(prefix="/api/threads", tags=["threads"])
logger = logging.getLogger("threads_api")

# spec §7.2／§8.7 dev_mode_notice（逐字；@{BOT_HANDLE} 代入）
DEV_MODE_NOTICE = (
    "目前為開發模式：只有被加入為測試人員的 Threads 帳號 @{bot_handle} 才會收到回覆。"
    "公開服務需通過 Meta App Review 與企業驗證，為本專題論文所述之上線條件。"
)

MSG_POLL_IN_PROGRESS = "另一輪輪詢正在進行中，請稍後再試。"
MSG_CLIENT_UNAVAILABLE = {
    "threads_not_configured": "Threads 尚未設定完成：live 模式需要有效的 access token 與 user id。",
    "token_invalid": "Threads access token 已過期或失效，請重新授權（scripts/threads_auth.py）。",
}

REPLIES_LIMIT_DEFAULT = 10
REPLIES_LIMIT_MAX = 50


def poll_allowed(x_admin_token: Optional[str] = Header(default=None)) -> bool:
    """False = THREADS_MODE=off（直接回 threads_disabled）；否則驗 X-Admin-Token，失敗丟 401／403。"""
    if settings.threads_mode_effective == "off":
        return False
    require_admin(x_admin_token)
    return True


# ── status ───────────────────────────────────────────────────────
def _bot_handle() -> str:
    return str(settings.BOT_HANDLE or "").strip().lstrip("@")


def _iso(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _int_or_none(value: Any) -> Optional[int]:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _reply_quota(raw: Any) -> Optional[Dict[str, int]]:
    """state.reply_quota（T-14 寫入 {usage,total}）；未寫入或格式不對 → None。"""
    if not isinstance(raw, dict):
        return None
    usage, total = _int_or_none(raw.get("usage")), _int_or_none(raw.get("total"))
    if usage is None or total is None:
        return None
    return {"usage": usage, "total": total}


def _display_path(path: Any) -> Optional[str]:
    """公開端點不外洩本機絕對路徑：相對路徑原樣（posix）；絕對路徑在工作目錄下 → 相對，否則只留最後兩段。"""
    if path is None:
        return None
    p = Path(path)
    if not p.is_absolute():
        return p.as_posix()
    try:
        return p.relative_to(Path.cwd()).as_posix()
    except ValueError:
        return Path(*p.parts[-2:]).as_posix()


def build_status() -> Dict[str, Any]:
    mode = settings.threads_mode_effective
    client = get_threads_client()
    state = threads_state.load_state()
    daily = state.get("daily") if isinstance(state.get("daily"), dict) else {}
    last_stats = state.get("last_stats")
    invalid_reason = getattr(client, "invalid_reason", None) or None
    return {
        "enabled": mode in ("live", "sim"),
        "mode": mode,
        "configured": bool(client is not None and client.available),
        "poll_minutes": int(settings.THREADS_POLL_MINUTES),
        "replied_count": len(state.get("replied_ids") or []),
        "last_poll_at": state.get("last_poll_at"),
        "last_poll_stats": last_stats if isinstance(last_stats, dict) else None,
        # token 過期時不必等輪詢：客戶端的 invalid_reason 優先（spec §7.3 第 3 點）
        "last_error": invalid_reason or state.get("last_error"),
        "backoff_until": state.get("backoff_until"),
        # token 期限取自「目前模式的客戶端」：live 讀 token 檔／.env；sim／off 無 token → null
        "token_expires_at": _iso(getattr(client, "token_expires_at", None)),
        "token_days_left": _int_or_none(getattr(client, "token_days_left", None)),
        "authorized_at": _iso(getattr(client, "authorized_at", None)),
        "auth_days_left": _int_or_none(getattr(client, "auth_days_left", None)),
        "reply_quota": _reply_quota(state.get("reply_quota")),
        "daily_replies": _int_or_none(daily.get("replies")) or 0,
        "daily_cap": int(settings.THREADS_MAX_REPLIES_PER_DAY),
        "dev_mode_notice": DEV_MODE_NOTICE.format(bot_handle=_bot_handle()),
        # S-11 sim 徽章旁的路徑提示；其他模式固定 null（鍵永遠存在，前端不必判斷缺鍵）
        "sim_mentions_path": _display_path(getattr(client, "mentions_path", None)) if mode == "sim" else None,
    }


@router.get("/status")
def threads_status():
    """機器人狀態（spec §5.3）；公開唯讀、不含 token。"""
    return build_status()


# ── replies ──────────────────────────────────────────────────────
@router.get("/replies")
def threads_replies(limit: int = Query(REPLIES_LIMIT_DEFAULT, ge=1, le=REPLIES_LIMIT_MAX)):
    """最近回覆紀錄（spec §5.3），倒序（最新在前）；只輸出紀錄的 11 個欄位。"""
    records = threads_state.read_reply_records(limit)
    fields = threads_state.REPLY_RECORD_FIELDS
    return {"records": [{f: rec.get(f) for f in fields} for rec in records]}


# ── poll ─────────────────────────────────────────────────────────
async def run_poll_quietly(trigger: str = "api") -> Optional[dict]:
    """背景工作與排程共用的輪詢入口。

    另一輪進行中（PollInProgress）：run_threads_poll 已記一行 warning，這裡只記 debug、不再往外丟
    （避免 APScheduler／ASGI 背景工作印 traceback）。其他非預期例外記 log 後吞下。"""
    try:
        return await run_threads_poll()
    except PollInProgress:
        logger.debug("threads poll skipped (trigger=%s): poll_in_progress", trigger)
    except Exception:
        logger.exception("threads poll failed (trigger=%s)", trigger)
    return None


@router.post("/poll", status_code=202)
def trigger_poll(background_tasks: BackgroundTasks, allowed: bool = Depends(poll_allowed)):
    """手動觸發一輪 mentions 輪詢（背景執行，立即回 202；腳本改輪詢 status.last_poll_at）。"""
    if not allowed:
        return JSONResponse(status_code=200, content={"started": False, "code": "threads_disabled"})

    client = get_threads_client()
    if client is None or not client.available:
        code = getattr(client, "invalid_reason", None) or "threads_not_configured"
        detail = MSG_CLIENT_UNAVAILABLE.get(code, MSG_CLIENT_UNAVAILABLE["threads_not_configured"])
        return JSONResponse(status_code=200, content={"started": False, "code": code, "detail": detail})

    if poll_in_progress():
        return JSONResponse(
            status_code=409, content={"detail": MSG_POLL_IN_PROGRESS, "code": "poll_in_progress"},
        )

    background_tasks.add_task(run_poll_quietly, "api")
    return {"started": True}
