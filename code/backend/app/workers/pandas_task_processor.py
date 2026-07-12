"""
任務處理器 - 三層快取 + AI 分析
Layer 0: URL 快取 → Layer 1: Hash 快取 → Layer 2: 向量快取 → Layer 3: AI

注意：AI / embedding / 來源驗證都是同步 requests（最長 150s），
必須用 asyncio.to_thread 丟到執行緒，否則會把整個 FastAPI event loop
卡死（/api/analyze/sync 分析期間連 /api/trending 都無法回應）。
"""
import asyncio
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


def _build_result(
    ai_analysis: Dict[str, Any], similar_news: list, timeline: list,
    cached: bool, cache_layer: str = None,
) -> Dict[str, Any]:
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
        # 哪一層快取命中（url / hash / vector；None = 走了完整 AI 分析）。
        # 前端顯示與論文「三層快取有效性」的實據都靠這個欄位。
        "cache_layer": cache_layer,
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
                result = _build_result(ai_analysis, [], [], cached=True, cache_layer="url")
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
            result = _build_result(ai_analysis, [], [], cached=True, cache_layer="hash")
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
            ai_result = await asyncio.to_thread(ai_service.analyze_image, input_data)
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

        # ── Layer 2（文字輸入）：向量快取，先於爬蟲 ────────────────────
        # 知識庫存的是「謠言主張」的向量，必須拿使用者原文比對才會命中
        # 「換句話說的同一謠言」。命中即回，連最慢的關鍵字搜尋與 AI 都省下。
        # （先前版本拿爬完的網頁全文比對，長文對短句幾乎不會過 0.88 門檻，
        #  導致向量層形同虛設——勿改回。）
        query_vector: list = []
        if not is_url:
            query_vector = await asyncio.to_thread(
                vector_service.vectorize_content, input_data
            )
            vector_cached = await asyncio.to_thread(
                pandas_store.find_similar_by_vector, query_vector
            )
            if vector_cached and not _is_fallback(vector_cached.get("ai_analysis")):
                result = _build_result(
                    vector_cached["ai_analysis"], [], [], cached=True, cache_layer="vector"
                )
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

        if is_url:
            content = crawl_result.get("content", input_data) or input_data
            url = crawl_result.get("url") or input_data
            similar_news = crawl_result.get("similar_news", []) or []
        else:
            # 文字輸入：分析對象一律是「使用者原文」。舊版會被關鍵字搜尋
            # 爬到的第一個網頁全文取代——AI 判的是別人的網頁而不是使用者
            # 的訊息（評測 96% 是以原文量測，上線行為必須一致）。
            # 爬到的網頁（常是相關查核文章）全部降級為 similar_news 參考脈絡。
            content = input_data
            url = None
            similar_news = []
            if crawl_result.get("url") and crawl_result.get("content"):
                similar_news.append({
                    "title": crawl_result.get("title"),
                    "url": crawl_result.get("url"),
                    "date": crawl_result.get("date"),
                    "source": crawl_result.get("source"),
                    "content": (crawl_result.get("content") or "")[:500],
                })
            similar_news += crawl_result.get("similar_news", []) or []

        # ── Layer 2（網址輸入）：向量快取，以爬到的內文語意比對 ───────
        if is_url:
            content_vector = await asyncio.to_thread(vector_service.vectorize_content, content)
            vector_cached = await asyncio.to_thread(pandas_store.find_similar_by_vector, content_vector)
            if vector_cached and not _is_fallback(vector_cached.get("ai_analysis")):
                ai_analysis = vector_cached["ai_analysis"]
                result = _build_result(ai_analysis, similar_news, [], cached=True, cache_layer="vector")
                task_store.update_task(
                    task_id, status="completed",
                    result_data=json.dumps(result, ensure_ascii=False),
                    completed_at=datetime.utcnow(),
                )
                return result
        else:
            # 文字輸入沿用原文向量（上面已比對過、未命中），存檔用
            content_vector = query_vector

        # ── Layer 3: AI 分析（全流程）─────────────────────────────────
        context = {"similar_news": similar_news, "crawl_result": crawl_result}
        ai_result = await asyncio.to_thread(
            ai_service.analyze_content, content, url=url, context=context
        )

        # Filter out hallucinated/dead URLs from AI sources
        if ai_result and ai_result.get("sources"):
            try:
                ai_result["sources"] = await asyncio.to_thread(
                    filter_valid_sources, ai_result["sources"]
                )
            except Exception as e:
                print(f"URL validation error: {e}")

        if not _is_fallback(ai_result):
            # 文字輸入存「使用者原文」：與 content_vector（原文向量）語意一致，
            # 未來的相似查詢才比得中；網址輸入存爬到的內文。
            pandas_store.save_record(
                data_type=input_type.upper(),
                raw_content=content if is_url else input_data,
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
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        loop.create_task(process_analysis_task_async(task_id, input_data, input_type))
    else:
        asyncio.run(process_analysis_task_async(task_id, input_data, input_type))
