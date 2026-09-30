"""
管理者相關 API（覆寫 AI 判定、查核結論同步）。

整個 /api/admin/* 需要 X-Admin-Token（spec §5.6：缺或錯 401 unauthorized、未設定 ADMIN_TOKEN 403 admin_disabled）。
覆寫＝人工確定性標記（spec §6.2 label_source="admin"、FR-17 (b)）：tasks 列與其知識庫列一起更新。
查核結論同步（FR-23，app/services/factcheck_sync.py）：POST 背景執行（202；已有一輪在跑 409 sync_in_progress），
GET 讀進度。GitHub Actions 的 factcheck-sync workflow 每天兩次呼叫 recent、每週一次 full。
每週新查核自動評測（FR-24，app/services/weekly_eval.py）：POST 背景執行（202；409 eval_in_progress），GET 讀進度，
做完後 GET report.md／results.csv 取報告。GitHub Actions 的 weekly-eval workflow 每週呼叫一次並把報告存進版本庫。
"""
import json
import logging
from typing import Any, Dict, Literal, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field, constr

from app.services import factcheck_sync, weekly_eval
from app.services.store_factory import get_audit_store, get_knowledge_store, get_task_store
from app.utils.admin_auth import require_admin
from app.utils.labels import category_label
from app.utils.verdict import frame_of, is_fallback


router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_admin)])
# 本機檔案版或 Supabase 版（store_factory）；測試以 monkeypatch 換掉這三個名稱。
# 端點是同步 def，阻塞 IO 由 FastAPI 的 threadpool 承擔。
task_store = get_task_store()
audit_store = get_audit_store()
kb_store = get_knowledge_store()
logger = logging.getLogger(__name__)

ADMIN_LABEL_SOURCE = "admin"
MSG_SYNC_IN_PROGRESS = "查核結論同步正在進行中；進度請看 GET /api/admin/factcheck-sync。"
MSG_EVAL_IN_PROGRESS = "每週評測正在進行中；進度請看 GET /api/admin/weekly-eval。"
MSG_NO_EVAL_REPORT = "還沒有評測結果：先 POST /api/admin/weekly-eval。"
# 覆寫後同步寫入知識庫列的判定欄位：快取命中讀 ai_analysis，知識庫頁與統計讀頂層欄位
_VERDICT_FIELDS = ("risk_type", "category", "confidence_score", "is_risk")


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


def _mark_admin(result: Dict[str, Any]) -> Dict[str, Any]:
    """
    結果改為人工覆寫：label_source=admin，verification_status 依 spec §5.3 推導
    （admin → rule；UNVERIFIABLE 與 AI 不可用固定 unverified），框色由 verdict.frame_of 重算，
    避免覆寫後 frame_type 仍是舊判定的顏色。
    """
    ai_unavailable = is_fallback(result)
    risk_type = str(result.get("risk_type") or "").upper()
    status = "unverified" if ai_unavailable or risk_type == "UNVERIFIABLE" else "rule"
    result["label_source"] = ADMIN_LABEL_SOURCE
    result["verification_status"] = status
    result["verified"] = status != "unverified"
    frame_type, frame_label, _light = frame_of(
        {**result, "ai_unavailable": ai_unavailable, "verification_status": status}
    )
    result["frame_type"] = frame_type
    result["frame_label"] = frame_label
    if result.get("category"):
        result["category_label"] = category_label(result["category"])
    return result


def _mark_kb_row_admin(kb_id: str, result: Dict[str, Any]) -> bool:
    """知識庫列：label_source=admin、verified=True（參與向量命中），並寫入覆寫後的判定欄位。"""
    apply_override = getattr(kb_store, "apply_admin_override", None)
    if callable(apply_override):
        # Supabase 版（PgKnowledgeStore）：同一套規則的單列 UPDATE，不整表重寫
        verdict = {k: result[k] for k in _VERDICT_FIELDS if k in result}
        return bool(apply_override(kb_id, verdict))
    df = kb_store.get_all_records()
    if df.empty or "id" not in df.columns:
        return False
    matches = df.index[df["id"] == kb_id]
    if len(matches) == 0:
        return False
    idx = matches[0]
    verdict = {k: result[k] for k in _VERDICT_FIELDS if k in result}
    df.at[idx, "label_source"] = ADMIN_LABEL_SOURCE
    df.at[idx, "verified"] = True
    for key, value in verdict.items():
        if key in df.columns:
            df.at[idx, key] = value
    analysis = df.at[idx, "ai_analysis"] if "ai_analysis" in df.columns else None
    if isinstance(analysis, dict):
        df.at[idx, "ai_analysis"] = {**analysis, **verdict}
    kb_store._save_knowledge_base(df)
    return True


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
    4. label_source 改 admin 並重算 verification_status／frame；寫回 tasks 列（含 label_source、verified 欄）。
    5. 任務有 kb_id 時，知識庫列同步改為 label_source=admin、verified=True 與覆寫後的判定。
    6. 新增一筆 AdminOverride 紀錄。
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

    _mark_admin(updated_result)

    task_store.update_task(
        task_id,
        result_data=json.dumps(updated_result, ensure_ascii=False),
        label_source=ADMIN_LABEL_SOURCE,
        verified=updated_result["verified"],
    )

    kb_id = task.get("kb_id") or current_result.get("kb_id")
    if kb_id and not _mark_kb_row_admin(str(kb_id), updated_result):
        logger.warning("override %s: knowledge_base row %s not found, KB not updated", task_id, kb_id)

    audit_store.append_override(
        task_id=task_id,
        admin_id=request.admin_id,
        reason=request.reason,
        new_risk_type=updated_result.get("risk_type"),
        new_category=updated_result.get("category"),
        new_confidence_score=updated_result.get("confidence_score"),
    )

    return updated_result


@router.post("/factcheck-sync", status_code=202)
def trigger_factcheck_sync(
    background_tasks: BackgroundTasks,
    mode: Literal["recent", "full"] = Query(
        default="recent", description="recent = 各來源最新一批（每天兩次）；full = 全部掃過（每週一次，第一次即完整回填）"
    ),
):
    """把查核機構新發布的判定寫進知識庫（只呼叫 embedding，不呼叫判讀模型）。背景執行，立即回 202。"""
    if not factcheck_sync.try_start(mode, background_tasks):
        return JSONResponse(
            status_code=409,
            content={"detail": MSG_SYNC_IN_PROGRESS, "code": "sync_in_progress", "status": factcheck_sync.status()},
        )
    return {"started": True, "mode": mode}


@router.get("/factcheck-sync")
def get_factcheck_sync_status():
    """同步進度：state = idle／queued／running／done／failed，另有候選、已存在、已寫入筆數與 embedding tokens。"""
    return factcheck_sync.status()


@router.post("/weekly-eval", status_code=202)
def trigger_weekly_eval(
    background_tasks: BackgroundTasks,
    max_usd: Optional[float] = Query(default=None, gt=0, le=10, description="本次上限（不超過 WEEKLY_EVAL_MAX_USD）"),
    plan_only: bool = Query(default=False, description="true = 只抓題目、算出會出幾題，不呼叫 AI（零成本）"),
    days: int = Query(default=weekly_eval.FRESH_DAYS, ge=1, le=31, description="本週新查核的天數範圍"),
):
    """每週新查核自動評測：用 CGU 每週剩下的額度量 AI 準確率（保留 WEEKLY_EVAL_RESERVE_USD 給網站使用者）。"""
    if not weekly_eval.try_start(max_usd=max_usd, plan_only=plan_only, days=days, background_tasks=background_tasks):
        return JSONResponse(
            status_code=409,
            content={"detail": MSG_EVAL_IN_PROGRESS, "code": "eval_in_progress", "status": weekly_eval.status()},
        )
    return {"started": True, "plan_only": plan_only, "max_usd": weekly_eval.status()["max_usd"], "days": days}


@router.get("/weekly-eval")
def get_weekly_eval_status():
    """評測進度：state = idle／queued／running／done／skipped（額度接近保留額）／failed；做完時附兩部分的統計。"""
    return weekly_eval.status()


def _eval_report_guard() -> Optional[JSONResponse]:
    if weekly_eval.is_running():
        return JSONResponse(status_code=409, content={"detail": MSG_EVAL_IN_PROGRESS, "code": "eval_in_progress"})
    if not weekly_eval.has_report():
        return JSONResponse(status_code=404, content={"detail": MSG_NO_EVAL_REPORT, "code": "no_eval_report"})
    return None


@router.get("/weekly-eval/report.md")
def get_weekly_eval_report():
    """最近一次評測的 Markdown 報告（不含訊息原文）。"""
    return _eval_report_guard() or PlainTextResponse(weekly_eval.report_markdown(),
                                                     media_type="text/markdown; charset=utf-8")


@router.get("/weekly-eval/results.csv")
def get_weekly_eval_results():
    """最近一次評測的逐題結果（網址、雜湊、真值、AI 判定；不含訊息原文）。"""
    return _eval_report_guard() or PlainTextResponse(weekly_eval.results_csv(), media_type="text/csv; charset=utf-8")
