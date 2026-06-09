"""
任務處理器 - 三層快取 + AI 分析
Layer 0: URL 快取 → Layer 1: Hash 快取 → Layer 2: 向量快取 → Layer 3: AI
"""
import json
import os
from datetime import datetime
from typing import Dict, Any, Tuple

from app.services.task_store import TaskStore
from app.services.pandas_store import PandasStore
from app.services.crawler import CrawlerService
from app.services.ai_service import AIService
from app.services.cache_service import CacheService
from app.services.vector_service import VectorService
from app.utils.url_validator import filter_valid_sources


def _ai_result_to_frame(ai_result: Dict[str, Any]) -> Tuple[str, str]:
    """
    依 AI 判定結果映射紅黃綠框（F2.x）
    """
    is_risk = ai_result.get("is_risk", False)
    conf = float(ai_result.get("confidence_score", 0) or 0)
    if is_risk:
        return "red", "已確認為假訊息"
    if conf >= 0.7:
        return "green", "此為正確訊息"
    return "yellow", "尚待確認或未知的信息"


def _is_fallback(ai_analysis: Any) -> bool:
    """判斷是否為 API 失敗的 fallback 結果，不應快取。"""
    if not isinstance(ai_analysis, dict):
        return True
    summary = ai_analysis.get("summary", "")
    return summary.startswith("AI 分析暫時無法使用") or "服務異常" in summary


def _safe_list(val):
    """Safely convert value to list, handling numpy arrays from parquet."""
    if val is None:
        return []
    if hasattr(val, "tolist"):  # numpy array
        return val.tolist()
    if isinstance(val, list):
        return val
    try:
        return list(val)
    except Exception:
        return []


def _safe_str(val):
    if val is None:
        return ""
    if hasattr(val, "item"):  # numpy scalar
        try:
            val = val.item()
        except Exception:
            pass
    return str(val) if val else ""


# confidence_score 由 LLM 自評，未經機率校準。對外改以離散等級呈現，
# 避免把「自評信心」誤當成「真實命中機率」。實際準確率以評測腳本量測。
CONFIDENCE_NOTE = "模型自評信心，未經機率校準（實際效能請參考評測報告）"


def _confidence_level(score: float) -> str:
    """把模型自評信心轉成離散等級（高/中/低），僅供顯示。"""
    if score >= 0.8:
        return "高"
    if score >= 0.5:
        return "中"
    return "低"


def _build_result(ai_analysis: Dict[str, Any], similar_news: list, timeline: list, cached: bool) -> Dict[str, Any]:
    ft, fl = _ai_result_to_frame(ai_analysis)
    conf = float(ai_analysis.get("confidence_score") or 0.0)
    return {
        "frame_type": ft,
        "frame_label": fl,
        "is_risk": bool(ai_analysis.get("is_risk", False)),
        "risk_type": _safe_str(ai_analysis.get("risk_type")) or "SAFE",
        "category": _safe_str(ai_analysis.get("category")) or "Irrelevant",
        "confidence_score": conf,
        "confidence_level": _confidence_level(conf),
        "confidence_note": CONFIDENCE_NOTE,
        "summary": _safe_str(ai_analysis.get("summary")),
        "explanation": _safe_str(ai_analysis.get("explanation")),
        "sources": _safe_list(ai_analysis.get("sources")),
        "similar_news": similar_news,
        "timeline": timeline,
        "cached": cached,
    }


async def process_analysis_task_async(
    task_id: str, input_data: str, input_type: str
) -> Dict[str, Any]:
    """
    非同步處理分析任務。三層快取策略：
      Layer 0: URL 快取（URL 輸入專用）
      Layer 1: Hash 快取（完全重複）
      Layer 2: 向量快取（語義相似）
      Layer 3: AI 分析（全流程）
    """
    task_store = TaskStore()
    pandas_store = PandasStore()
    crawler = CrawlerService()
    ai_service = AIService()
    cache_service = CacheService()
    vector_service = VectorService()

    task_store.update_task(task_id, status="processing")

    try:
        is_url = input_data.startswith("http://") or input_data.startswith("https://")

        # ── Layer 0: URL 快取 ──────────────────────────────────────────
        if input_type in ("text", "url") and is_url:
            url_cached = pandas_store.find_by_url(input_data)
            if url_cached and not _is_fallback(url_cached.get("ai_analysis")):
                ai_analysis = url_cached["ai_analysis"]
                result = _build_result(ai_analysis, [], [], cached=True)
                task_store.update_task(
                    task_id, status="completed",
                    result_data=json.dumps(result, ensure_ascii=False),
                    completed_at=datetime.utcnow(),
                )
                return result

        # ── Layer 1: Hash 快取（對原始輸入做 hash）────────────────────
        content_hash = cache_service.generate_hash(input_data)
        hash_cached = pandas_store.find_by_hash(content_hash)
        if hash_cached and not _is_fallback(hash_cached.get("ai_analysis")):
            ai_analysis = hash_cached["ai_analysis"]
            result = _build_result(ai_analysis, [], [], cached=True)
            task_store.update_task(
                task_id, status="completed",
                result_data=json.dumps(result, ensure_ascii=False),
                completed_at=datetime.utcnow(),
            )
            return result

        # ── 圖片分析路徑（無快取層）────────────────────────────────────
        if input_type == "image":
            if not os.path.isfile(input_data):
                raise Exception("圖片檔案不存在")
            ai_result = ai_service.analyze_image(input_data)
            try:
                os.remove(input_data)
            except Exception:
                pass
            result = _build_result(ai_result, [], [], cached=False)
            task_store.update_task(
                task_id, status="completed",
                result_data=json.dumps(result, ensure_ascii=False),
                completed_at=datetime.utcnow(),
            )
            return result

        # ── 爬取內容（文字 / URL）──────────────────────────────────────
        if is_url:
            crawl_result = await crawler.process_input(input_data, "url")
        else:
            crawl_result = await crawler.process_input(input_data, "keyword")

        if not crawl_result.get("success"):
            raise Exception(f"爬取失敗: {crawl_result.get('error')}")

        content = crawl_result.get("content", input_data) or input_data
        url = crawl_result.get("url") or (input_data if is_url else None)
        similar_news = crawl_result.get("similar_news", [])

        # ── Layer 2: 向量快取（語義相似）─────────────────────────────
        content_vector = vector_service.vectorize_content(content)
        vector_cached = pandas_store.find_similar_by_vector(content_vector)
        if vector_cached and not _is_fallback(vector_cached.get("ai_analysis")):
            ai_analysis = vector_cached["ai_analysis"]
            result = _build_result(ai_analysis, similar_news, [], cached=True)
            task_store.update_task(
                task_id, status="completed",
                result_data=json.dumps(result, ensure_ascii=False),
                completed_at=datetime.utcnow(),
            )
            return result

        # ── Layer 3: AI 分析（全流程）─────────────────────────────────
        context = {"similar_news": similar_news, "crawl_result": crawl_result}
        ai_result = ai_service.analyze_content(content, url=url, context=context)

        # Filter out hallucinated/dead URLs from AI sources
        if ai_result and ai_result.get("sources"):
            try:
                ai_result["sources"] = filter_valid_sources(ai_result["sources"])
            except Exception as e:
                print(f"URL validation error: {e}")

        if not _is_fallback(ai_result):
            pandas_store.save_record(
                data_type=input_type.upper(),
                raw_content=content,
                content_hash=content_hash,
                content_vector=content_vector,
                ai_result=ai_result,
                source_url=url,
            )

        timeline = [
            {"title": n.get("title"), "date": n.get("date"), "url": n.get("url"), "source": n.get("source")}
            for n in similar_news
        ]

        result = _build_result(ai_result, similar_news, timeline, cached=False)
        task_store.update_task(
            task_id, status="completed",
            result_data=json.dumps(result, ensure_ascii=False),
            completed_at=datetime.utcnow(),
        )
        return result

    except Exception as e:
        task_store.update_task(task_id, status="failed", error_message=str(e))
        raise


def process_analysis_task(task_id: str, input_data: str, input_type: str) -> None:
    import asyncio

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        loop.create_task(process_analysis_task_async(task_id, input_data, input_type))
    else:
        asyncio.run(process_analysis_task_async(task_id, input_data, input_type))
