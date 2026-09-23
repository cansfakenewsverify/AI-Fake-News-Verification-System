"""
分析 API 路由（純 Pandas 版）

DEMO_MODE=True 時：暫停真實 API，立即回傳紅黃綠框 mock 結果，來源鎖定 Google 首頁
"""
import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Literal
from urllib.parse import urlparse

from fastapi import APIRouter, Request, UploadFile, File
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator
from pydantic_core import PydanticCustomError
from app.config import settings
from app.workers.task_queue import enqueue_analysis_task
from app.services.ai_budget import ai_budget
from app.services.store_factory import get_task_store
from app.utils import safe_url
from app.utils.body_limit import IMAGE_MAX_BYTES, payload_too_large_body
from app.utils.labels import CATEGORY_LABEL_UNKNOWN, category_label
from app.utils.rate_limit import rate_limited_response

router = APIRouter(prefix="/api/analyze", tags=["analyze"])
# 本機 TaskStore 或 Supabase 的 PgTaskStore（store_factory）；測試以 monkeypatch 換掉這個名稱。
# store 的方法是阻塞 IO（Parquet／資料庫）：async 端點一律經 asyncio.to_thread 呼叫。
task_store = get_task_store()
logger = logging.getLogger(__name__)

# spec §5.7 / §8.7 通用文案（原始例外只進 log，不回給客戶端）
MSG_INVALID_URL = "這不是有效的網址，請以 http:// 或 https:// 開頭。"
MSG_ANALYSIS_FAILED = "查證失敗，請稍後再試。"
MSG_TASK_CREATE_FAILED = "建立查證任務失敗，請稍後再試。"
MSG_BLOCKED_URL = "這個網址無法查證（內部或保留位址）。"
MSG_DAILY_CAP = "今日查證額度已用完，明天再試；已查過的內容仍可直接查到結果。"
MSG_UNSUPPORTED_MEDIA = "只接受 PNG、JPG、WEBP 圖片。"

# FR-03 驗收 1：以檔頭（magic bytes）判斷圖片格式，不信副檔名
_IMAGE_SIGNATURES = (
    (b"\x89PNG\r\n\x1a\n", "png"),
    (b"\xff\xd8", "jpg"),
)


TZ_TAIPEI = timezone(timedelta(hours=8))


def _now_taipei_iso() -> str:
    return datetime.now(TZ_TAIPEI).isoformat(timespec="seconds")


def _task_time_iso(task: dict) -> str:
    """舊任務沒有 analyzed_at：退用 completed_at（TaskStore 存 naive UTC）轉 +08:00。"""
    value = (task or {}).get("completed_at") or (task or {}).get("created_at")
    if value is None or value == "":
        return ""
    try:
        dt = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(TZ_TAIPEI).isoformat(timespec="seconds")
    except (TypeError, ValueError, AttributeError):  # 含 pandas NaT
        return ""


def api_error(status_code: int, detail: str, code: str) -> JSONResponse:
    """spec §5.7 錯誤格式：{"detail": 人可讀繁中, "code": 機器碼}"""
    return JSONResponse(status_code=status_code, content={"detail": detail, "code": code})


def is_valid_http_url(content: str) -> bool:
    """FR-02：strip 後以 http:// 或 https:// 開頭，且 urlparse 取得到 host。"""
    text = (content or "").strip()
    if not text.lower().startswith(("http://", "https://")):
        return False
    try:
        return bool(urlparse(text).hostname)
    except ValueError:
        return False


async def blocked_url_response(url: str) -> JSONResponse | None:
    """
    FR-02 驗收 2：建立任務前做 SSRF 檢查（只做 DNS 解析，不發 HTTP 請求）。
    被拒 → 422 blocked_url；DNS 解析失敗不算 SSRF，放行交給處理器回 UNVERIFIABLE。
    """
    try:
        await asyncio.to_thread(safe_url.check_url, url)
    except safe_url.BlockedURL as e:
        logger.info("blocked_url: %s", e.reason)
        return api_error(422, MSG_BLOCKED_URL, "blocked_url")
    except safe_url.SafeFetchError:
        pass
    return None


async def daily_cap_response(content: str, input_type: str) -> JSONResponse | None:
    """
    FR-14：今日 AI 次數已達 DAILY_AI_CALL_CAP 時，未命中快取的查證在「建立任務前」回
    429 daily_cap_reached（Retry-After 到隔日 00:00 +08:00）；快取命中照常放行。
    """
    if not ai_budget.enabled or not await asyncio.to_thread(ai_budget.cap_reached):
        return None
    from app.workers.pandas_task_processor import cache_would_hit

    try:
        if await cache_would_hit(content, input_type):
            return None
    except Exception:
        # 快取查不了（資料庫／embedding 暫時失敗）就當作未命中：額度用完時寧可擋下
        logger.exception("daily cap: cache lookup failed")
    return JSONResponse(
        status_code=429,
        content={"detail": MSG_DAILY_CAP, "code": "daily_cap_reached"},
        headers={"Retry-After": str(ai_budget.seconds_until_reset())},
    )


def image_kind(head: bytes) -> str | None:
    """依檔頭回傳 png／jpg／webp；不是支援的圖片回 None。"""
    for signature, kind in _IMAGE_SIGNATURES:
        if head.startswith(signature):
            return kind
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "webp"
    return None


# 成果展示用：鎖死回傳 Google 首頁
DEMO_SOURCE_URL = "https://www.google.com/"
DEMO_SOURCES = [{"title": "相關查證來源", "url": DEMO_SOURCE_URL}]

FRAME_COLOR = {
    "red": "紅色",
    "yellow": "黃色",
    "green": "綠色",
}


def _decorate_display_fields(payload: dict) -> dict:
    """
    依使用者需求：在後端以文字欄位提供「顏色框」與「顯示資訊」。
    """
    frame_type = payload.get("frame_type")
    frame_label = payload.get("frame_label")
    border_color = FRAME_COLOR.get(frame_type, str(frame_type or ""))
    related_links = []
    for s in payload.get("sources", []) or []:
        u = (s or {}).get("url")
        if u:
            related_links.append(u)
    payload["border_color"] = border_color
    payload["display_info"] = frame_label or ""
    payload["related_links"] = related_links
    return payload


def _get_demo_result(frame_type: str) -> dict:
    """依紅/黃/綠框回傳 mock 結果"""
    frames = {
        "red": {
            "frame_type": "red",
            "frame_label": "已確認為假訊息",
            "is_risk": True,
            "risk_type": "MISINFO",
            "category": "Content_Farm",
            "confidence_score": 0.95,
            "summary": "此訊息經查證為不實內容。",
            "explanation": "經比對可信來源，此資訊多處與事實不符，建議勿轉傳。",
            "sources": DEMO_SOURCES,
        },
        "yellow": {
            "frame_type": "yellow",
            "frame_label": "尚待確認或未知的信息",
            "is_risk": False,
            "risk_type": "UNKNOWN",
            "category": "Irrelevant",
            "confidence_score": 0.5,
            "summary": "此訊息尚無法確認真假，請審慎判斷。",
            "explanation": "目前缺乏足夠查證資料，建議多方查證後再分享。",
            "sources": DEMO_SOURCES,
        },
        "green": {
            "frame_type": "green",
            "frame_label": "此為正確訊息",
            "is_risk": False,
            "risk_type": "SAFE",
            "category": "Safe",
            "confidence_score": 0.95,
            "summary": "此訊息經查證為正確資訊。",
            "explanation": "已比對官方及可信來源，內容與事實相符。",
            "sources": DEMO_SOURCES,
        },
    }
    return _decorate_display_fields(frames.get(frame_type, frames["yellow"]).copy())


class AnalyzeTextRequest(BaseModel):
    """文字分析請求（空字串直接 422，不浪費爬蟲/AI 資源）"""
    content: str = Field(..., min_length=1, max_length=20000)

    @field_validator("content")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        # 只有空白也視為空字串（FR-01 驗收 4），不送 AI
        if not value.strip():
            raise PydanticCustomError(
                "string_too_short", "String should have at least 1 character",
                {"min_length": 1},
            )
        return value


class AnalyzeResponse(BaseModel):
    """分析回應（非 Demo 模式）"""
    task_id: str
    result_id: str | None = None             # = task_id（spec §5.2）
    status: str
    message: str


class DemoAnalysisResult(BaseModel):
    """Demo 模式分析結果（含紅黃綠框）"""
    frame_type: str
    frame_label: str
    border_color: str
    display_info: str
    related_links: list
    is_risk: bool
    risk_type: str
    category: str
    confidence_score: float
    summary: str
    explanation: str
    sources: list


class AnalysisResult(BaseModel):
    """分析結果"""
    frame_type: str | None = None
    frame_label: str | None = None
    border_color: str | None = None
    display_info: str | None = None
    related_links: list | None = None
    is_risk: bool
    risk_type: str
    category: str
    confidence_score: float
    confidence_level: str | None = None      # 高/中/低（證據信心：與已證實內容的相似度；app/services/evidence.py）
    confidence_basis: str | None = None      # 依據代碼（factchecked／similar_case／pattern／…）
    confidence_note: str | None = None        # 依據說明
    evidence: dict | None = None             # nearest_similarity／nearest_degrees／pattern_margin
    summary: str
    explanation: str
    sources: list
    cached: bool | None = None                # 是否命中快取（未呼叫 AI）
    cache_layer: str | None = None            # 命中哪一層：url / hash / vector
    # ── v2 欄位（spec §5.4）──
    # 必填、非 null：處理器任何路徑漏填都會在 response_model 驗證時被抓到
    result_id: str
    ai_unavailable: bool
    similar_news: list
    category_label: str
    label_source: str
    analyzed_at: str
    verified: bool
    verification_status: Literal["verified", "rule", "unverified"]
    source_tier: int | None                   # 無 Tier 1/2 來源時為 null（spec §5.4）
    related_discussions: list
    kb_id: str | None = None


def _with_v2_defaults(payload: dict, result_id: str, analyzed_at: str = "") -> dict:
    """
    舊任務（v2 前寫入的 result_data）與 DEMO 結果缺 §5.4 v2 欄位時補保守預設
    （spec §6：舊列 verified=False、unverified），讓必填的 response_model 不因舊資料 500。
    處理器新產生的結果已帶齊，setdefault 不會覆寫。
    """
    payload["result_id"] = payload.get("result_id") or result_id
    payload.setdefault("ai_unavailable", False)
    payload.setdefault("similar_news", [])
    if not payload.get("category_label"):
        payload["category_label"] = category_label(payload.get("category")) or CATEGORY_LABEL_UNKNOWN
    payload["label_source"] = payload.get("label_source") or "ai"
    payload["analyzed_at"] = payload.get("analyzed_at") or analyzed_at
    if payload.get("verification_status") not in ("verified", "rule", "unverified"):
        payload["verification_status"] = "unverified"
    payload["verified"] = payload["verification_status"] != "unverified"
    payload.setdefault("source_tier", None)
    payload.setdefault("related_discussions", [])
    return payload


@router.post("/text")
async def analyze_text(
    request: AnalyzeTextRequest,
    http_request: Request,
):
    """
    分析文字內容（URL 或關鍵字）
    DEMO_MODE 時：立即回傳紅框 mock 結果。
    """
    if settings.DEMO_MODE:
        return _get_demo_result("red")
    guard = rate_limited_response(http_request)
    if guard is None:
        guard = await daily_cap_response(request.content, "text")
    if guard is not None:
        return guard
    try:
        task_id = await asyncio.to_thread(
            task_store.create_task,
            "analyze_text", request.content, input_type="text", origin="web",
        )
        enqueue_analysis_task(task_id, request.content, "text")
        return AnalyzeResponse(
            task_id=task_id,
            result_id=task_id,
            status="pending",
            message="任務已提交處理，請使用 task_id 查詢結果",
        )
    except Exception:
        logger.exception("analyze_text: create task failed")
        return api_error(500, MSG_TASK_CREATE_FAILED, "analysis_failed")


@router.post("/url")
async def analyze_url(
    request: AnalyzeTextRequest,
    http_request: Request,
):
    """
    分析 URL（FR-02）：伺服器端驗證網址，不再委派 /text。
    DEMO_MODE 時：立即回傳黃框 mock 結果。
    """
    if not is_valid_http_url(request.content):
        return api_error(422, MSG_INVALID_URL, "invalid_url")
    url = request.content.strip()
    # 限速放在 SSRF 檢查（會做 DNS 解析）之前
    limited = None if settings.DEMO_MODE else rate_limited_response(http_request)
    if limited is not None:
        return limited
    blocked = await blocked_url_response(url)
    if blocked is not None:
        return blocked
    if settings.DEMO_MODE:
        return _get_demo_result("yellow")
    capped = await daily_cap_response(url, "url")
    if capped is not None:
        return capped
    try:
        task_id = await asyncio.to_thread(
            task_store.create_task,
            "analyze_url", url, input_type="url", origin="web",
        )
        # 處理器以 input_type="url" 寫知識庫 data_type="URL"
        enqueue_analysis_task(task_id, url, "url")
        return AnalyzeResponse(
            task_id=task_id,
            result_id=task_id,
            status="pending",
            message="任務已提交處理，請使用 task_id 查詢結果",
        )
    except Exception:
        logger.exception("analyze_url: create task failed")
        return api_error(500, MSG_TASK_CREATE_FAILED, "analysis_failed")


@router.post("/sync", response_model=AnalysisResult)
async def analyze_sync(
    request: AnalyzeTextRequest,
    http_request: Request,
):
    """
    同步分析端點（給 iOS 捷徑 / 自動化用）。
    一次請求直接回傳最終結果，不需輪詢 task_id。
    內部直接 await 完整三層快取 + AI 流程。
    """
    is_url = request.content.strip().lower().startswith(("http://", "https://"))
    content = request.content.strip() if is_url else request.content
    if is_url and not is_valid_http_url(content):
        return api_error(422, MSG_INVALID_URL, "invalid_url")
    limited = None if settings.DEMO_MODE else rate_limited_response(http_request)
    if limited is not None:
        return limited
    if is_url:
        blocked = await blocked_url_response(content)
        if blocked is not None:
            return blocked
    if settings.DEMO_MODE:
        return _with_v2_defaults(
            _get_demo_result("yellow" if is_url else "red"), "demo", _now_taipei_iso(),
        )
    capped = await daily_cap_response(content, "url" if is_url else "text")
    if capped is not None:
        return capped
    try:
        from app.workers.pandas_task_processor import process_analysis_task_async

        input_type = "url" if is_url else "text"
        task_id = await asyncio.to_thread(
            task_store.create_task,
            f"analyze_{input_type}", content,
            input_type=input_type, origin="web",
        )
        result = await process_analysis_task_async(task_id, content, input_type)
        result = dict(result or {})
        return _decorate_display_fields(_with_v2_defaults(result, task_id, _now_taipei_iso()))
    except Exception:
        logger.exception("analyze_sync failed")
        return api_error(500, MSG_ANALYSIS_FAILED, "analysis_failed")


@router.post("/image")
async def analyze_image(
    http_request: Request,
    file: UploadFile = File(...),
):
    """
    分析圖片內容（FR-03 驗收 1：檔頭不是 PNG／JPG／WEBP → 415；超過 10 MB → 413）
    DEMO_MODE 時：立即回傳綠框 mock 結果。
    """
    if settings.DEMO_MODE:
        return _get_demo_result("green")
    limited = rate_limited_response(http_request)
    if limited is not None:
        return limited
    # 多讀 1 byte 就能判斷有沒有超過上限，不必把超大檔整個讀進記憶體
    image_content = await file.read(IMAGE_MAX_BYTES + 1)
    if len(image_content) > IMAGE_MAX_BYTES:
        return JSONResponse(status_code=413, content=payload_too_large_body())
    kind = image_kind(image_content[:12])
    if kind is None:
        return api_error(415, MSG_UNSUPPORTED_MEDIA, "unsupported_media")
    capped = await daily_cap_response("", "image")
    if capped is not None:
        return capped
    try:
        import os

        task_id = await asyncio.to_thread(
            task_store.create_task,
            "analyze_image",
            file.filename or "uploaded_image",
            input_type="image", origin="web",
        )
        # 專題規格：圖片分析需儲存至暫存檔並傳路徑給處理器
        data_dir = "data"
        uploads_dir = os.path.join(data_dir, "uploads")
        os.makedirs(uploads_dir, exist_ok=True)
        # 副檔名取自檔頭判斷結果，不用使用者給的檔名
        image_path = os.path.join(uploads_dir, f"{task_id}.{kind}")
        with open(image_path, "wb") as f:
            f.write(image_content)
        enqueue_analysis_task(task_id, image_path, "image")
        return AnalyzeResponse(
            task_id=task_id,
            result_id=task_id,
            status="pending",
            message="圖片分析任務已提交處理",
        )
    except Exception:
        logger.exception("analyze_image: create task failed")
        return api_error(500, MSG_TASK_CREATE_FAILED, "analysis_failed")


def task_result_payload(task: dict) -> dict | None:
    """
    completed 任務的 result 物件（spec §5.4：/api/analyze/task/{id} 與 /api/result/{id}.result 同結構）。
    result_data 缺或格式錯誤 → None（原因只進 log）。
    """
    raw = (task or {}).get("result_data")
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        logger.warning("task %s: result_data is not valid JSON", (task or {}).get("id"))
        return None
    if not isinstance(data, dict):
        return None
    _with_v2_defaults(data, str(task.get("id") or ""), _task_time_iso(task))
    return _decorate_display_fields(data)


@router.get(
    "/task/{task_id}",
    response_model=AnalysisResult,
    responses={202: {"description": "任務處理中：{task_id, status}"}},
)
async def get_task_result(
    task_id: str,
):
    """
    查詢任務結果（舊端點，保留相容；新前端改用 /api/result/{id}）。
    pending／processing → 202 {task_id, status}（不再回 SAFE 佔位，spec §5.1）。
    """
    task = await asyncio.to_thread(task_store.get_task, task_id)
    if not task:
        return api_error(404, "任務不存在", "task_not_found")

    status = task.get("status")
    if status in ("pending", "processing"):
        return JSONResponse(status_code=202, content={"task_id": task_id, "status": status})

    if status == "failed":
        logger.warning("task %s failed: %s", task_id, task.get("error_message"))
        return api_error(500, MSG_ANALYSIS_FAILED, "analysis_failed")

    payload = task_result_payload(task)
    if payload is not None:
        return payload
    return api_error(500, MSG_ANALYSIS_FAILED, "analysis_failed")


@router.get("/task/{task_id}/status")
async def get_task_status(
    task_id: str,
):
    """
    查詢任務狀態
    """
    task = await asyncio.to_thread(task_store.get_task, task_id)
    if not task:
        return api_error(404, "任務不存在", "task_not_found")

    return {
        "task_id": task["id"],
        "status": task.get("status"),
        "created_at": task.get("created_at"),
        "updated_at": task.get("updated_at"),
        "completed_at": task.get("completed_at"),
    }

