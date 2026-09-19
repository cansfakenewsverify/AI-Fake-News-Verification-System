"""
使用者回饋 API
"""
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, constr
from app.services.store_factory import get_audit_store, get_task_store
from app.utils.rate_limit import rate_limited_response


router = APIRouter(prefix="/api/feedback", tags=["feedback"])
# 本機檔案版或 Supabase 版（store_factory）；端點是同步 def，阻塞 IO 由 threadpool 承擔
task_store = get_task_store()
audit_store = get_audit_store()


class FeedbackRequest(BaseModel):
    """使用者回饋請求模型"""

    # 長度上限：公開端點，不讓單筆回饋塞進大量文字（雲端資料庫只有 500 MB）
    rating: constr(strip_whitespace=True, min_length=1, max_length=32) = Field(
        ...,
        description="回饋等級（例如：agree / disagree / uncertain）",
    )
    comment: Optional[constr(strip_whitespace=True, max_length=2000)] = Field(
        None,
        description="補充說明（可選）",
    )
    user_id: Optional[constr(strip_whitespace=True, max_length=64)] = Field(
        None,
        description="使用者識別 ID（可選，未來可與登入機制串接）",
    )


@router.post("/tasks/{task_id}")
def submit_feedback(
    task_id: str,
    request: FeedbackRequest,
    http_request: Request,
):
    """
    提交對指定任務結果的使用者回饋。
    """
    limited = rate_limited_response(http_request, "feedback")
    if limited is not None:
        return limited
    task = task_store.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任務不存在")

    audit_store.append_feedback(
        task_id=task_id,
        rating=request.rating,
        comment=request.comment,
        user_id=request.user_id,
    )

    return {"status": "ok"}

