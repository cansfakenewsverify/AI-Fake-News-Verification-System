"""
分析 API 路由（純 Pandas 版）

DEMO_MODE=True 時：暫停真實 API，立即回傳紅黃綠框 mock 結果，來源鎖定 Google 首頁
"""
import json
from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel
from app.config import settings
from app.workers.task_queue import enqueue_analysis_task
from app.services.task_store import TaskStore

router = APIRouter(prefix="/api/analyze", tags=["analyze"])
task_store = TaskStore()

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
    """文字分析請求"""
    content: str


class AnalyzeResponse(BaseModel):
    """分析回應（非 Demo 模式）"""
    task_id: str
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
    summary: str
    explanation: str
    sources: list


@router.post("/text")
async def analyze_text(
    request: AnalyzeTextRequest,
):
    """
    分析文字內容（URL 或關鍵字）
    DEMO_MODE 時：立即回傳紅框 mock 結果。
    """
    if settings.DEMO_MODE:
        return _get_demo_result("red")
    try:
        task_id = task_store.create_task("analyze_text", request.content)
        enqueue_analysis_task(task_id, request.content, "text")
        return AnalyzeResponse(
            task_id=task_id,
            status="pending",
            message="任務已提交處理，請使用 task_id 查詢結果",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"建立任務失敗: {str(e)}")


@router.post("/url")
async def analyze_url(
    request: AnalyzeTextRequest,
):
    """
    分析 URL
    DEMO_MODE 時：立即回傳黃框 mock 結果。
    """
    if settings.DEMO_MODE:
        return _get_demo_result("yellow")
    return await analyze_text(request)


@router.post("/image")
async def analyze_image(
    file: UploadFile = File(...),
):
    """
    分析圖片內容
    DEMO_MODE 時：立即回傳綠框 mock 結果。
    """
    if settings.DEMO_MODE:
        return _get_demo_result("green")
    try:
        import tempfile
        import os
        import uuid

        image_content = await file.read()
        task_id = task_store.create_task(
            "analyze_image",
            file.filename or "uploaded_image",
        )
        # 專題規格：圖片分析需儲存至暫存檔並傳路徑給處理器
        data_dir = "data"
        uploads_dir = os.path.join(data_dir, "uploads")
        os.makedirs(uploads_dir, exist_ok=True)
        ext = "png"
        if file.filename and "." in file.filename:
            ext = file.filename.rsplit(".", 1)[-1].lower()
            if ext not in ("png", "jpg", "jpeg", "webp", "gif"):
                ext = "png"
        image_path = os.path.join(uploads_dir, f"{task_id}.{ext}")
        with open(image_path, "wb") as f:
            f.write(image_content)
        enqueue_analysis_task(task_id, image_path, "image")
        return AnalyzeResponse(
            task_id=task_id,
            status="pending",
            message="圖片分析任務已提交處理",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"建立任務失敗: {str(e)}")


@router.get("/task/{task_id}", response_model=AnalysisResult)
async def get_task_result(
    task_id: str,
):
    """
    查詢任務結果
    """
    task = task_store.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任務不存在")

    status = task.get("status")
    if status in ("pending", "processing"):
        return _decorate_display_fields({
            "is_risk": False,
            "risk_type": "SAFE",
            "category": "Irrelevant",
            "confidence_score": 0.0,
            "summary": "任務處理中...",
            "explanation": "請稍後再試",
            "sources": [],
        })

    if status == "failed":
        raise HTTPException(
            status_code=500,
            detail=f"任務執行失敗: {task.get('error_message')}",
        )

    result_data = task.get("result_data")
    if result_data:
        try:
            return _decorate_display_fields(json.loads(result_data))
        except json.JSONDecodeError:
            raise HTTPException(status_code=500, detail="任務結果格式錯誤")

    raise HTTPException(status_code=404, detail="結果尚未準備好")


@router.get("/task/{task_id}/status")
async def get_task_status(
    task_id: str,
):
    """
    查詢任務狀態
    """
    task = task_store.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任務不存在")

    return {
        "task_id": task["id"],
        "status": task.get("status"),
        "created_at": task.get("created_at"),
        "updated_at": task.get("updated_at"),
        "completed_at": task.get("completed_at"),
    }

