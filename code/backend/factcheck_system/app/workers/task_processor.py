"""
任務處理器 - 執行實際的分析工作
"""
import asyncio
from typing import Dict, Any
import uuid
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models.task import Task, TaskStatus
from app.models.scam_knowledge_base import ScamKnowledgeBase
from app.services.crawler import CrawlerService
from app.services.ai_service import AIService
from app.services.vector_service import VectorService
from app.services.cache_service import CacheService
import json
from datetime import datetime


def process_analysis_task(task_id: str, input_data: str, input_type: str):
    """
    處理分析任務（同步函數，由 RQ Worker 呼叫）
    
    Args:
        task_id: 任務 ID
        input_data: 輸入資料
        input_type: 輸入類型
    """
    db = SessionLocal()
    
    try:
        # 更新任務狀態為處理中
        task = db.query(Task).filter(Task.id == uuid.UUID(task_id)).first()
        if not task:
            print(f"❌ 任務不存在: {task_id}")
            return
        
        task.status = TaskStatus.PROCESSING
        db.commit()
        
        # 執行非同步處理
        result = asyncio.run(_process_async(task_id, input_data, input_type, db))
        
        # 更新任務結果
        task.status = TaskStatus.COMPLETED
        task.result_data = json.dumps(result, ensure_ascii=False)
        task.completed_at = datetime.utcnow()
        db.commit()
        
        print(f"✅ 任務完成: {task_id}")
        
    except Exception as e:
        # 更新任務為失敗
        task = db.query(Task).filter(Task.id == uuid.UUID(task_id)).first()
        if task:
            task.status = TaskStatus.FAILED
            task.error_message = str(e)
            db.commit()
        print(f"❌ 任務失敗: {task_id}, 錯誤: {str(e)}")
        
    finally:
        db.close()


async def _process_async(
    task_id: str,
    input_data: str,
    input_type: str,
    db: Session
) -> Dict[str, Any]:
    """
    非同步處理邏輯
    """
    # 初始化服務
    crawler = CrawlerService()
    ai_service = AIService()
    vector_service = VectorService()
    cache_service = CacheService()
    
    # ===== Layer 1: Hash 快取檢查 =====
    content_hash = cache_service.generate_hash(input_data)
    cached_record = cache_service.check_hash_cache(db, content_hash)
    
    if cached_record:
        print(f"🎯 Layer 1 快取命中: {content_hash[:8]}...")
        return {
            "is_risk": cached_record.is_risk,
            "risk_type": cached_record.risk_type,
            "category": cached_record.category,
            "confidence_score": cached_record.confidence_score,
            "summary": cached_record.ai_analysis.get("summary", "") if cached_record.ai_analysis else "",
            "explanation": cached_record.ai_analysis.get("explanation", "") if cached_record.ai_analysis else "",
            "sources": cached_record.ai_analysis.get("sources", []) if cached_record.ai_analysis else [],
            "cached": True
        }
    
    # ===== 爬取內容 =====
    if input_type == "text" or input_type == "url":
        # 判斷是否為 URL
        if input_data.startswith("http://") or input_data.startswith("https://"):
            crawl_result = await crawler.process_input(input_data, "url")
        else:
            # 關鍵字搜尋（待實作）
            crawl_result = {
                'success': True,
                'url': None,
                'title': None,
                'content': input_data,
                'author': None,
                'date': None,
                'source': None
            }
    else:
        crawl_result = {'success': False, 'error': '不支援的輸入類型'}
    
    if not crawl_result.get('success'):
        raise Exception(f"爬取失敗: {crawl_result.get('error')}")
    
    # 取得內容
    content = crawl_result.get('content', input_data)
    url = crawl_result.get('url', input_data)
    
    # ===== Layer 2: 向量快取檢查 =====
    content_vector = vector_service.vectorize_content(content)
    similar_record = cache_service.check_vector_cache(db, content_vector)
    
    if similar_record:
        print(f"🎯 Layer 2 快取命中: 相似度 {similar_record.ai_analysis.get('confidence_score', 0) if similar_record.ai_analysis else 0}")
        return {
            "is_risk": similar_record.is_risk,
            "risk_type": similar_record.risk_type,
            "category": similar_record.category,
            "confidence_score": similar_record.confidence_score,
            "summary": similar_record.ai_analysis.get("summary", "") if similar_record.ai_analysis else "",
            "explanation": similar_record.ai_analysis.get("explanation", "") if similar_record.ai_analysis else "",
            "sources": similar_record.ai_analysis.get("sources", []) if similar_record.ai_analysis else [],
            "cached": True
        }
    
    # ===== Layer 3: AI 深度分析 =====
    # 尋找相似新聞（用於時間軸）
    similar_news = vector_service.find_similar_news(db, content_vector, top_n=5)
    
    context = {
        'similar_news': similar_news,
        'crawl_result': crawl_result
    }
    
    # 執行 AI 分析
    ai_result = ai_service.analyze_content(content, url=url, context=context)
    
    # ===== 儲存到快取 =====
    cache_service.save_to_cache(
        db=db,
        data_type=input_type.upper(),
        raw_content=content,
        content_hash=content_hash,
        content_vector=content_vector,
        ai_result=ai_result
    )
    
    # 返回結果
    return {
        "is_risk": ai_result.get("is_risk", False),
        "risk_type": ai_result.get("risk_type", "SAFE"),
        "category": ai_result.get("category", "Irrelevant"),
        "confidence_score": ai_result.get("confidence_score", 0.0),
        "summary": ai_result.get("summary", ""),
        "explanation": ai_result.get("explanation", ""),
        "sources": ai_result.get("sources", []),
        "cached": False,
        "timeline": similar_news
    }

