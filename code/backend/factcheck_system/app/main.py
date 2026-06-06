"""
FastAPI main application entry point.
"""
import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.openapi.docs import get_swagger_ui_html

from app.config import settings
from app.api import (
    analyze, admin as admin_api, feedback as feedback_api,
    trending as trending_api, knowledge as knowledge_api,
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

    scheduler = None
    # 排程預設關閉，避免背景持續呼叫 AI 燒點數；需自動抓新聞時在 .env 設 ENABLE_SCHEDULER=true
    if settings.ENABLE_SCHEDULER and not settings.DEMO_MODE:
        try:
            from apscheduler.schedulers.asyncio import AsyncIOScheduler
            from app.services.news_fetcher import run_trending_fetch, retry_pending_records

            scheduler = AsyncIOScheduler(timezone="Asia/Taipei")
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
            scheduler.start()
            app.state.scheduler = scheduler
            logger.info("Scheduler started:")
            logger.info("  - Full RSS fetch: every %dh", settings.TRENDING_FETCH_INTERVAL_HOURS)
            logger.info("  - Retry pending : every 30min")

            # First fetch in background after 30s (don't block startup)
            asyncio.get_event_loop().call_later(
                30, lambda: asyncio.create_task(run_trending_fetch())
            )
            logger.info("First fetch in 30 seconds...")
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
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routes
app.include_router(analyze.router)
app.include_router(admin_api.router)
app.include_router(feedback_api.router)
app.include_router(trending_api.router)
app.include_router(knowledge_api.router)

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
