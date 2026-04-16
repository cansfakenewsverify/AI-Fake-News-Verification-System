"""
FastAPI 主程式
"""
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.openapi.docs import get_swagger_ui_html

from app.config import settings
from app.api import analyze
from app.api import admin as admin_api
from app.api import feedback as feedback_api

# 建立 FastAPI 應用
app = FastAPI(
    title=settings.APP_NAME,
    description="AI 驅動假訊息驗證系統 API",
    version="0.1.0",
    docs_url=None,
    redoc_url="/redoc",
)

# 設定 CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 註冊路由
app.include_router(analyze.router)
app.include_router(admin_api.router)
app.include_router(feedback_api.router)

static_dir = Path(__file__).resolve().parent.parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/docs", include_in_schema=False)
async def custom_swagger_ui_html():
    """
    Swagger UI（維持原本畫面風格，僅隱藏 Try it out 按鈕）
    """
    return get_swagger_ui_html(
        openapi_url=app.openapi_url,
        title=f"{settings.APP_NAME}",
        swagger_ui_parameters={
            "tryItOutEnabled": True,
        },
        swagger_css_url="/static/swagger-custom.css",
    )


@app.on_event("startup")
async def startup_event():
    """應用啟動時執行"""
    mode = "成果展示 (DEMO_MODE)" if settings.DEMO_MODE else "正式"
    print(f"✅ 應用啟動完成 - {mode}")


@app.get("/")
async def root():
    """根路徑：純後端（不提供前端頁面）"""
    return {
        "message": "AI 驅動假訊息驗證系統 API",
        "version": "0.1.0",
        "docs": "/docs",
    }


@app.get("/health")
async def health_check():
    """健康檢查"""
    return {"status": "healthy"}

