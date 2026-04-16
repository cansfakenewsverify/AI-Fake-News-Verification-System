"""
測試模式 - 不使用真實 API，使用模擬資料測試流程
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.services.cache_service import CacheService
from app.services.pandas_store import PandasStore
import uuid
from datetime import datetime


def test_without_api():
    """使用模擬資料測試流程（不需要 API Key）"""
    print("🧪 測試模式：使用模擬資料（不需要 API Key）\n")
    
    cache_service = CacheService()
    pandas_store = PandasStore()
    
    # 模擬測試資料
    test_content = "台積電內部消息！限時投資機會，保證獲利 300%，立即點擊連結加入！"
    print(f"📝 測試內容: {test_content}\n")
    
    # ===== Step 1: Hash 快取檢查 =====
    print("1️⃣ 檢查 Hash 快取（Layer 1）...")
    content_hash = cache_service.generate_hash(test_content)
    cached_record = pandas_store.find_by_hash(content_hash)
    
    if cached_record:
        print(f"🎯 Layer 1 快取命中！")
        print(f"   風險類型: {cached_record.get('risk_type')}")
        print(f"   分類: {cached_record.get('category')}")
        print(f"   可信度: {cached_record.get('confidence_score')}")
        return
    
    print("   ⏭️  未命中快取\n")
    
    # ===== Step 2: 模擬 AI 分析結果 =====
    print("2️⃣ 模擬 AI 分析結果...")
    mock_ai_result = {
        "is_risk": True,
        "risk_type": "SCAM",
        "category": "Investment",
        "confidence_score": 0.95,
        "summary": "假冒台積電名義的投資詐騙訊息，宣稱保證獲利 300%，屬於典型的高風險投資詐騙",
        "explanation": "此訊息包含多個詐騙特徵：1) 假冒知名企業（台積電）名義 2) 宣稱不切實際的高獲利（300%） 3) 使用緊迫性話術（限時） 4) 要求點擊連結。真實的投資機會不會以這種方式宣傳。",
        "sources": []
    }
    
    print("✅ 模擬分析完成")
    print("📊 模擬結果:")
    print(f"   - 是否為風險: {mock_ai_result.get('is_risk')}")
    print(f"   - 風險類型: {mock_ai_result.get('risk_type')}")
    print(f"   - 分類: {mock_ai_result.get('category')}")
    print(f"   - 可信度分數: {mock_ai_result.get('confidence_score')}")
    print(f"   - 摘要: {mock_ai_result.get('summary')}")
    print()
    
    # ===== Step 3: 儲存到 Pandas =====
    print("3️⃣ 儲存結果到 Pandas...")
    try:
        record = pandas_store.save_record(
            data_type="TEXT",
            raw_content=test_content,
            content_hash=content_hash,
            content_vector=None,  # 簡化版先不存向量
            ai_result=mock_ai_result
        )
        print(f"✅ 已寫入 knowledge_base.parquet")
        print(f"   記錄 ID: {record['id']}")
        print(f"   檔案位置: {pandas_store.knowledge_base_path}")
        print()
    except Exception as e:
        print(f"❌ 儲存失敗: {str(e)}")
        return
    
    # ===== Step 4: 驗證讀取 =====
    print("4️⃣ 驗證讀取...")
    all_records = pandas_store.get_all_records()
    print(f"✅ 知識庫目前有 {len(all_records)} 筆記錄")
    
    # ===== Step 5: 測試快取命中 =====
    print("\n5️⃣ 測試快取命中...")
    cached_record2 = pandas_store.find_by_hash(content_hash)
    if cached_record2:
        print(f"✅ 快取測試成功！")
        print(f"   風險類型: {cached_record2.get('risk_type')}")
        print(f"   分類: {cached_record2.get('category')}")
        print(f"   可信度: {cached_record2.get('confidence_score')}")
    
    print("\n🎉 測試完成！")
    print("\n📝 說明:")
    print("   - 這是模擬模式，使用假資料測試流程")
    print("   - 實際使用時，需要有效的 Google API Key 且有足夠配額")
    print("   - 你可以在 Node.js 後端讀取 data/knowledge_base.parquet")


if __name__ == "__main__":
    test_without_api()

