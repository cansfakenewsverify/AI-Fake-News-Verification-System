"""
資料庫種子腳本 - 建立測試資料（Phase 1 Mock Data）
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.database import SessionLocal, init_db
from app.models.scam_knowledge_base import ScamKnowledgeBase
from app.services.cache_service import CacheService
from app.services.vector_service import VectorService
import uuid


def seed_mock_data():
    """建立 Mock 測試資料"""
    db = SessionLocal()
    cache_service = CacheService()
    vector_service = VectorService()
    
    try:
        # 初始化資料庫
        init_db()
        print("✅ 資料庫初始化完成")
        
        # 測試資料 1: 必死型詐騙（SCAM）
        scam_url = "http://bad-scam.xyz/investment"
        scam_content = "台積電內部消息！限時投資機會，保證獲利 300%，立即點擊連結加入！"
        scam_hash = cache_service.generate_hash(scam_content)
        scam_vector = vector_service.vectorize_content(scam_content)
        
        scam_record = ScamKnowledgeBase(
            id=uuid.uuid4(),
            data_type="URL",
            raw_content=scam_content,
            data_hash=scam_hash,
            content_vector=scam_vector,
            is_risk=True,
            risk_type="SCAM",
            category="Investment",
            confidence_score=0.98,
            ai_analysis={
                "is_risk": True,
                "risk_type": "SCAM",
                "category": "Investment",
                "confidence_score": 0.98,
                "summary": "假冒台積電名義的投資詐騙，使用免洗網域",
                "explanation": "此網址為高風險免洗網域，非官方管道，屬於典型投資詐騙",
                "sources": []
            }
        )
        db.add(scam_record)
        print("✅ 建立測試資料 1: 詐騙案例")
        
        # 測試資料 2: 謠言型假訊息（MISINFO）
        rumor_content = "吃香蕉會致癌！專家警告：香蕉含有大量致癌物質，千萬不要吃！"
        rumor_hash = cache_service.generate_hash(rumor_content)
        rumor_vector = vector_service.vectorize_content(rumor_content)
        
        rumor_record = ScamKnowledgeBase(
            id=uuid.uuid4(),
            data_type="TEXT",
            raw_content=rumor_content,
            data_hash=rumor_hash,
            content_vector=rumor_vector,
            is_risk=True,
            risk_type="MISINFO",
            category="Health_Rumor",
            confidence_score=0.85,
            ai_analysis={
                "is_risk": True,
                "risk_type": "MISINFO",
                "category": "Health_Rumor",
                "confidence_score": 0.85,
                "summary": "關於香蕉致癌的健康謠言",
                "explanation": "這是錯誤的健康謠言。香蕉是安全且營養豐富的水果，沒有科學證據顯示會致癌。正確事實：香蕉富含鉀、維生素B6和纖維，是健康的食物選擇。",
                "sources": [
                    {
                        "title": "台灣事實查核中心 - 香蕉謠言澄清",
                        "url": "https://tfc-taiwan.org.tw/articles/example-banana"
                    }
                ]
            }
        )
        db.add(rumor_record)
        print("✅ 建立測試資料 2: 假訊息案例")
        
        # 測試資料 3: 安全型內容（SAFE）
        safe_url = "https://www.tsmc.com/news-events/news"
        safe_content = "台積電官方公告：本公司將持續投資先進製程技術，為全球半導體產業貢獻。"
        safe_hash = cache_service.generate_hash(safe_content)
        safe_vector = vector_service.vectorize_content(safe_content)
        
        safe_record = ScamKnowledgeBase(
            id=uuid.uuid4(),
            data_type="URL",
            raw_content=safe_content,
            data_hash=safe_hash,
            content_vector=safe_vector,
            is_risk=False,
            risk_type="SAFE",
            category="Safe",
            confidence_score=0.95,
            ai_analysis={
                "is_risk": False,
                "risk_type": "SAFE",
                "category": "Safe",
                "confidence_score": 0.95,
                "summary": "台積電官方公告，來源可信",
                "explanation": "這是來自台積電官方網站的正式公告，內容可信且安全",
                "sources": [
                    {
                        "title": "台積電官方網站",
                        "url": safe_url
                    }
                ]
            }
        )
        db.add(safe_record)
        print("✅ 建立測試資料 3: 安全案例")
        
        # 提交所有變更
        db.commit()
        print("\n🎉 所有測試資料建立完成！")
        print(f"   - 詐騙案例: {scam_record.id}")
        print(f"   - 假訊息案例: {rumor_record.id}")
        print(f"   - 安全案例: {safe_record.id}")
        
    except Exception as e:
        db.rollback()
        print(f"❌ 建立測試資料失敗: {str(e)}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed_mock_data()

