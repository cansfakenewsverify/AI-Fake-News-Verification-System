"""
任務處理器 - 專題規格整合
支援文字、URL、關鍵字、圖片分析；回傳紅黃綠框與相似新聞
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


def _ai_result_to_frame(ai_result: Dict[str, Any]) -> Tuple[str, str]:
    """
    依 AI 判定結果映射紅黃綠框（專題規格 F2.x）
    - 紅：已確認為假訊息
    - 黃：尚待確認或未知
    - 綠：此為正確訊息
    """
    is_risk = ai_result.get("is_risk", False)
    conf = float(ai_result.get("confidence_score", 0) or 0)
    if is_risk:
        return "red", "已確認為假訊息"
    if conf >= 0.7:
        return "green", "此為正確訊息"
    return "yellow", "尚待確認或未知的信息"


async def process_analysis_task_async(
    task_id: str, input_data: str, input_type: str
) -> Dict[str, Any]:
    """
    非同步處理分析任務。
    - 任務狀態與結果：data/tasks.parquet
    - 知識庫快取：data/knowledge_base.parquet
    """
    task_store = TaskStore()
    pandas_store = PandasStore()
    crawler = CrawlerService()
    ai_service = AIService()
    cache_service = CacheService()
    vector_service = VectorService()

    # 狀態：processing
    task_store.update_task(task_id, status="processing")

    try:
        # ===== Layer 1: Hash 快取檢查（跳過 fallback 錯誤結果）=====
        content_hash = cache_service.generate_hash(input_data)
        cached = pandas_store.find_by_hash(content_hash)
        is_fallback = lambda a: (a or {}).get("summary", "").startswith("AI 分析暫時無法使用") or "服務異常" in (a or {}).get("summary", "")
        if cached and isinstance(cached.get("ai_analysis"), dict) and not is_fallback(cached.get("ai_analysis")):
            ai_analysis = cached["ai_analysis"]
            ft, fl = _ai_result_to_frame(ai_analysis)
            result = {
                "frame_type": ft,
                "frame_label": fl,
                "is_risk": bool(ai_analysis.get("is_risk", False)),
                "risk_type": ai_analysis.get("risk_type", "SAFE"),
                "category": ai_analysis.get("category", "Irrelevant"),
                "confidence_score": float(
                    ai_analysis.get("confidence_score", 0.0) or 0.0
                ),
                "summary": ai_analysis.get("summary", "") or "",
                "explanation": ai_analysis.get("explanation", "") or "",
                "sources": ai_analysis.get("sources", []) or [],
                "similar_news": [],
                "timeline": [],
                "cached": True,
            }
            task_store.update_task(
                task_id,
                status="completed",
                result_data=json.dumps(result, ensure_ascii=False),
                completed_at=datetime.utcnow(),
            )
            return result

        # ===== 爬取內容 =====
        if input_type == "image":
            # 圖片分析：input_data 為暫存檔路徑
            if not os.path.isfile(input_data):
                raise Exception("圖片檔案不存在")
            ai_result = ai_service.analyze_image(input_data)
            try:
                os.remove(input_data)
            except Exception:
                pass
            similar_news = []
            timeline = []
        elif input_type in ("text", "url"):
            if input_data.startswith("http://") or input_data.startswith("https://"):
                crawl_result = await crawler.process_input(input_data, "url")
            else:
                # F1.3: 關鍵字搜尋並爬取相似新聞
                crawl_result = await crawler.process_input(input_data, "keyword")
            if not crawl_result.get("success"):
                raise Exception(f"爬取失敗: {crawl_result.get('error')}")
            content = crawl_result.get("content", input_data) or input_data
            url = crawl_result.get("url") or input_data
            similar_news = crawl_result.get("similar_news", [])

            # ===== 向量化 =====
            content_vector = vector_service.vectorize_content(content)

            # ===== AI 分析 =====
            context = {"similar_news": similar_news, "crawl_result": crawl_result}
            ai_result = ai_service.analyze_content(content, url=url, context=context)

            # ===== 寫入知識庫（不儲存 fallback 錯誤結果）=====
            if not is_fallback(ai_result):
                pandas_store.save_record(
                    data_type=input_type.upper(),
                    raw_content=content,
                    content_hash=content_hash,
                    content_vector=content_vector,
                    ai_result=ai_result,
                )

            # F2.x: 相似新聞時間軸
            timeline = [
                {"title": n.get("title"), "date": n.get("date"), "url": n.get("url"), "source": n.get("source")}
                for n in similar_news
            ]
        else:
            raise Exception("不支援的輸入類型")

        # ===== 紅黃綠框對應（專題規格 F2.x）=====
        frame_type, frame_label = _ai_result_to_frame(ai_result)

        result = {
            "frame_type": frame_type,
            "frame_label": frame_label,
            "is_risk": ai_result.get("is_risk", False),
            "risk_type": ai_result.get("risk_type", "SAFE"),
            "category": ai_result.get("category", "Irrelevant"),
            "confidence_score": ai_result.get("confidence_score", 0.0),
            "summary": ai_result.get("summary", ""),
            "explanation": ai_result.get("explanation", ""),
            "sources": ai_result.get("sources", []),
            "similar_news": similar_news if input_type != "image" else [],
            "timeline": timeline if input_type != "image" else [],
            "cached": False,
        }

        task_store.update_task(
            task_id,
            status="completed",
            result_data=json.dumps(result, ensure_ascii=False),
            completed_at=datetime.utcnow(),
        )
        return result

    except Exception as e:
        task_store.update_task(task_id, status="failed", error_message=str(e))
        raise


def process_analysis_task(task_id: str, input_data: str, input_type: str) -> None:
    """
    包裝函式：在有 event loop 時，用 create_task 背景執行；
    沒有 event loop（例如獨立腳本）時，使用 asyncio.run 執行。
    """
    import asyncio

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        loop.create_task(process_analysis_task_async(task_id, input_data, input_type))
    else:
        asyncio.run(process_analysis_task_async(task_id, input_data, input_type))

