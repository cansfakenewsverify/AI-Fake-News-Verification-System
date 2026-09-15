"""
結果頁 API（FR-04、spec §5.3）：GET /api/result/{id}

公開、無驗證；Cache-Control: max-age=5。資料來源 tasks.parquet（TaskStore）。
- status != completed → result: null、share: null
- failed → error: {code: "analysis_failed", message: 通用文案}（原始例外只進 log）
- ai_unavailable → share: null
- 找不到 → 404 {"detail": "找不到這筆查證", "code": "result_not_found"}
"""
import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.api.analyze import MSG_ANALYSIS_FAILED, api_error, task_result_payload
from app.services.task_store import TaskStore, input_type_from_task_type
from app.utils.share import build_share
from app.utils.verdict import is_fallback

router = APIRouter(prefix="/api/result", tags=["result"])
task_store = TaskStore()
logger = logging.getLogger(__name__)

TZ_TAIPEI = timezone(timedelta(hours=8))
INPUT_PREVIEW_MAX = 200
IMAGE_PREVIEW = "[圖片]"
CACHE_CONTROL = "max-age=5"
MSG_RESULT_NOT_FOUND = "找不到這筆查證"


def to_taipei_iso(value: Any) -> Optional[str]:
    """TaskStore 以 naive UTC 存時間；輸出 +08:00 ISO 字串。"""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        try:
            dt = datetime.fromisoformat(str(value))
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(TZ_TAIPEI).isoformat(timespec="seconds")


def input_preview(task: Dict[str, Any], input_type: str) -> str:
    if input_type == "image":
        return IMAGE_PREVIEW
    text = str(task.get("input_data") or "")
    if input_type == "url":
        return text.strip()
    return text[:INPUT_PREVIEW_MAX]


def parse_platform_post(task: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """只在 origin 為 threads* 時解析；其餘或解析失敗 → None。"""
    origin = str(task.get("origin") or "")
    if not origin.startswith("threads"):
        return None
    raw = task.get("platform_post")
    if isinstance(raw, dict):
        return raw
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def request_base_url(request: Optional[Request]) -> Optional[str]:
    """PUBLIC_BASE_URL 未設定時的分享網址後備：優先 X-Forwarded-Proto/Host（反向代理），否則請求 base URL。"""
    if request is None:
        return None
    fwd_host = (request.headers.get("x-forwarded-host") or "").split(",")[0].strip()
    if fwd_host:
        proto = (request.headers.get("x-forwarded-proto") or "").split(",")[0].strip() or request.url.scheme
        return f"{proto}://{fwd_host}"
    return str(request.base_url).rstrip("/")


def build_result_response(task: Dict[str, Any], base_url: Optional[str] = None) -> Dict[str, Any]:
    task_id = task.get("id")
    status = task.get("status") or "pending"
    input_type = task.get("input_type") or input_type_from_task_type(task.get("task_type"))

    result = task_result_payload(task) if status == "completed" else None
    # v1.0 前的舊任務沒有 ai_unavailable 欄位（載入時補 False）；AI 失敗的舊結果要從內容判斷，
    # 否則會把 fallback 當有效判定顯示並提供分享（測試報告 D-1）
    legacy_fallback = result is not None and is_fallback(result)
    if legacy_fallback and isinstance(result, dict):
        result["ai_unavailable"] = True
    ai_unavailable = (bool(task.get("ai_unavailable"))
                      or bool((result or {}).get("ai_unavailable"))
                      or legacy_fallback)

    error = None
    if status == "failed":
        logger.warning("result %s failed: %s", task_id, task.get("error_message"))
        error = {"code": "analysis_failed", "message": MSG_ANALYSIS_FAILED}

    share = None
    if result is not None and not ai_unavailable:
        share = build_share(result, task_id, fallback_base_url=base_url)

    return {
        "id": task_id,
        "status": status,
        "input_type": input_type,
        "input_preview": input_preview(task, input_type),
        "source_url": (task.get("input_data") or "").strip() if input_type == "url" else None,
        "origin": task.get("origin") or "web",
        "platform_post": parse_platform_post(task),
        "created_at": to_taipei_iso(task.get("created_at")),
        "completed_at": to_taipei_iso(task.get("completed_at")),
        "ai_unavailable": ai_unavailable,
        "result": result,
        "error": error,
        "share": share,
    }


@router.get("/{result_id}")
async def get_result(result_id: str, request: Request):
    """結果頁資料（spec §5.3）。"""
    task = await asyncio.to_thread(task_store.get_task, result_id)
    if not task:
        return api_error(404, MSG_RESULT_NOT_FOUND, "result_not_found")
    body = build_result_response(task, base_url=request_base_url(request))
    return JSONResponse(content=body, headers={"Cache-Control": CACHE_CONTROL})
