"""
使用者回饋 API
"""
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, constr
from app.services.task_store import TaskStore
from app.services.audit_store import AuditStore


router = APIRouter(prefix="/api/feedback", tags=["feedback"])
task_store = TaskStore()
audit_store = AuditStore()


class FeedbackRequest(BaseModel):
    """使用者回饋請求模型"""

    rating: constr(strip_whitespace=True, min_length=1) = Field(
        ...,
        description="回饋等級（例如：agree / disagree / uncertain）",
    )
    comment: Optional[constr(strip_whitespace=True)] = Field(
        None,
        description="補充說明（可選）",
    )
    user_id: Optional[constr(strip_whitespace=True)] = Field(
        None,
        description="使用者識別 ID（可選，未來可與登入機制串接）",
    )


@router.post("/tasks/{task_id}")
def submit_feedback(
    task_id: str,
    request: FeedbackRequest,
):
    """
    提交對指定任務結果的使用者回饋。
    """
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

