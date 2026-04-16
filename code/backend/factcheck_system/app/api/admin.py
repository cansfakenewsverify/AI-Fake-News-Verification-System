"""
管理者相關 API（覆寫 AI 判定）
"""
import json
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, constr

from app.services.task_store import TaskStore
from app.services.audit_store import AuditStore


router = APIRouter(prefix="/api/admin", tags=["admin"])
task_store = TaskStore()
audit_store = AuditStore()


class AdminOverrideRequest(BaseModel):
    """管理者覆寫請求模型"""

    risk_type: Optional[constr(strip_whitespace=True)] = Field(
        None, description="新的風險類型（SCAM / MISINFO / SAFE）"
    )
    category: Optional[constr(strip_whitespace=True)] = Field(
        None, description="新的分類（例如 Investment, Health_Rumor 等）"
    )
    confidence_score: Optional[float] = Field(
        None,
        ge=0.0,
        le=1.0,
        description="新的可信度分數（0.0~1.0）",
    )
    reason: constr(strip_whitespace=True, min_length=1) = Field(
        ..., description="覆寫原因（必填）"
    )
    admin_id: constr(strip_whitespace=True, min_length=1) = Field(
        ..., description="管理者識別 ID（之後可與登入機制串接）"
    )


@router.post("/tasks/{task_id}/override")
def override_task_result(
    task_id: str,
    request: AdminOverrideRequest,
):
    """
    管理者覆寫指定任務的 AI 判定結果。

    實作策略：
    1. 讀取既有的 task.result_data JSON。
    2. 套用管理者提供的覆寫欄位（risk_type / category / confidence_score）。
    3. 自動更新 is_risk（若 risk_type 為 SCAM 或 MISINFO 則為 true，SAFE 則為 false）。
    4. 將更新後的結果寫回 task.result_data，並新增一筆 AdminOverride 紀錄。
    """
    task = task_store.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任務不存在")

    if task.get("status") != "completed" or not task.get("result_data"):
        raise HTTPException(status_code=400, detail="任務尚未完成或尚無可覆寫的結果")

    try:
        current_result = json.loads(task["result_data"])
    except json.JSONDecodeError:
        current_result = {}

    updated_result = dict(current_result)

    if request.risk_type is not None:
        updated_result["risk_type"] = request.risk_type

    if request.category is not None:
        updated_result["category"] = request.category

    if request.confidence_score is not None:
        updated_result["confidence_score"] = float(request.confidence_score)

    risk_type_value = updated_result.get("risk_type")
    if risk_type_value in ("SCAM", "MISINFO"):
        updated_result["is_risk"] = True
    elif risk_type_value == "SAFE":
        updated_result["is_risk"] = False

    task_store.update_task(task_id, result_data=json.dumps(updated_result, ensure_ascii=False))

    audit_store.append_override(
        task_id=task_id,
        admin_id=request.admin_id,
        reason=request.reason,
        new_risk_type=updated_result.get("risk_type"),
        new_category=updated_result.get("category"),
        new_confidence_score=updated_result.get("confidence_score"),
    )

    return updated_result

