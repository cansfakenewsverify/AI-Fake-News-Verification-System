"""
FastAPI main application entry point.
"""
import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.openapi.docs import get_swagger_ui_html

from app.config import settings
from app.api import (
    analyze, admin as admin_api, feedback as feedback_api,
    trending as trending_api, knowledge as knowledge_api,
    threads as threads_api, result as result_api,
)
from app.database_sql import init_sql_db

# ── Logging setup ────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("app.main")


# ── Lifespan handler (replaces deprecated @app.on_event) ────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize on startup, cleanup on shutdown."""
    # Startup
    init_sql_db()

    from app.utils.share import warn_if_public_base_url_missing
    warn_if_public_base_url_missing()

    scheduler = None
    # 兩個排程都預設關閉（省 AI 點數）：
    #   ENABLE_SCHEDULER=true    → 自動抓熱門新聞
    #   THREADS_MODE=live|sim    → Threads 查核機器人輪詢 mentions（DEMO_MODE 不影響）
    want_trending = settings.ENABLE_SCHEDULER and not settings.DEMO_MODE
    threads_mode = settings.threads_mode_effective
    want_threads = threads_mode in ("live", "sim")
    logger.info("Threads mode: %s", threads_mode)
    if want_trending or want_threads:
        try:
            from apscheduler.schedulers.asyncio import AsyncIOScheduler

            scheduler = AsyncIOScheduler(timezone="Asia/Taipei")
            logger.info("Scheduler starting:")

            if want_trending:
                from app.services.news_fetcher import run_trending_fetch, retry_pending_records

                scheduler.add_job(
                    run_trending_fetch, "interval",
                    hours=settings.TRENDING_FETCH_INTERVAL_HOURS,
                    id="trending_fetch", replace_existing=True,
                )
                scheduler.add_job(
                    retry_pending_records, "interval",
                    minutes=30,
                    id="retry_pending", replace_existing=True,
                )
                logger.info("  - Full RSS fetch: every %dh", settings.TRENDING_FETCH_INTERVAL_HOURS)
                logger.info("  - Retry pending : every 30min")

                # First fetch in background after 30s (don't block startup)
                asyncio.get_running_loop().call_later(
                    30, lambda: asyncio.create_task(run_trending_fetch())
                )
                logger.info("First fetch in 30 seconds...")

            if want_threads:
                from app.workers.threads_bot import run_threads_poll

                scheduler.add_job(
                    run_threads_poll, "interval",
                    minutes=settings.THREADS_POLL_MINUTES,
                    id="threads_poll", replace_existing=True,
                )
                logger.info("  - Threads bot   : poll mentions every %dmin", settings.THREADS_POLL_MINUTES)

            scheduler.start()
            app.state.scheduler = scheduler
        except Exception as e:
            logger.error("Scheduler failed to start: %s", e)

    mode = "DEMO" if settings.DEMO_MODE else "LIVE"
    logger.info("App started [%s] - http://localhost:8000/docs", mode)

    yield  # ── application runs here ──

    # Shutdown
    if scheduler:
        scheduler.shutdown()
        logger.info("Scheduler stopped")


# ── FastAPI app ──────────────────────────────────────────────
app = FastAPI(
    title=settings.APP_NAME,
    description="AI Fake News Verification System API",
    version="0.2.0",
    docs_url=None,
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    # 無 cookie / 登入：不需要 credentials（spec §9 安全：CORS）
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── 422 錯誤格式（spec §5.7）─────────────────────────────────
_MSG_EMPTY = "請先貼上要查證的內容。"
_MSG_TOO_LONG = "內容超過 20,000 字，請刪減後再試。"
_MSG_INVALID = "輸入格式不正確，請檢查後再試。"


def _validation_message(errors) -> str:
    """把 pydantic 錯誤陣列轉成一句繁中（文案取自 spec §8.7 err_empty／err_too_long）。"""
    for err in errors or []:
        etype = str(err.get("type") or "")
        if etype in ("string_too_short", "missing"):
            return _MSG_EMPTY
        if etype == "string_too_long":
            return _MSG_TOO_LONG
    return _MSG_INVALID


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = exc.errors()
    # ctx 內可能帶例外物件（無法 JSON 序列化），轉成字串再輸出
    detail = jsonable_encoder(errors, custom_encoder={Exception: str})
    return JSONResponse(
        status_code=422,
        content={
            "detail": detail,
            "code": "validation_error",
            "message": _validation_message(errors),
        },
    )

# Routes
app.include_router(analyze.router)
app.include_router(admin_api.router)
app.include_router(feedback_api.router)
app.include_router(trending_api.router)
app.include_router(knowledge_api.router)
app.include_router(threads_api.router)
app.include_router(result_api.router)

# Static
_static_dir = Path(__file__).resolve().parent.parent / "static"
if _static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")


@app.get("/docs", include_in_schema=False)
async def custom_swagger_ui_html():
    return get_swagger_ui_html(
        openapi_url=app.openapi_url,
        title=settings.APP_NAME,
        swagger_ui_parameters={"tryItOutEnabled": True},
        swagger_css_url="/static/swagger-custom.css",
    )


@app.get("/")
async def root():
    return {"message": "AI Fake News Verification System", "version": "0.2.0", "docs": "/docs"}


@app.get("/health")
async def health_check():
    return {"status": "healthy"}
