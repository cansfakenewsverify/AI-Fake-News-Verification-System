"""
測試 AI 分析流程（不依賴資料庫，使用 Pandas 儲存）
"""
import sys
import os
import asyncio
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.services.crawler import CrawlerService
from app.services.ai_service import AIService
from app.services.cache_service import CacheService
from app.services.pandas_store import PandasStore


async def test_ai_pipeline():
    """測試完整的 AI 分析流程"""
    print("🚀 開始測試 AI 分析流程...\n")
    
    # 初始化服務
    crawler = CrawlerService()
    ai_service = AIService()
    cache_service = CacheService()
    pandas_store = PandasStore()
    
    # 測試 URL（使用真實可訪問的網址，或使用文字內容直接測試）
    # 選項 1: 使用真實網址（如果有的話）
    # test_url = "https://example.com"
    
    # 選項 2: 直接使用文字內容測試（不爬取）
    test_url = None
    test_content = "台積電內部消息！限時投資機會，保證獲利 300%，立即點擊連結加入！這是一個典型的投資詐騙訊息。"
    print(f"📝 測試內容: {test_content[:50]}...\n")
    
    # ===== Step 1: 取得內容 =====
    if test_url:
        print("1️⃣ 爬取網頁內容...")
        crawl_result = await crawler.process_input(test_url, "url")
        
        if not crawl_result.get('success'):
            print(f"❌ 爬取失敗: {crawl_result.get('error')}")
            print("   改用直接文字內容測試...\n")
            content = test_content
            url = None
        else:
            content = crawl_result.get('content', test_url)
            url = crawl_result.get('url', test_url)
            print(f"✅ 爬取成功，內容長度: {len(content)} 字元\n")
    else:
        print("1️⃣ 使用直接文字內容（跳過爬取）...")
        content = test_content
        url = None
        print(f"✅ 內容長度: {len(content)} 字元\n")
    
    # ===== Step 2: Layer 1 Hash 快取檢查 =====
    print("2️⃣ 檢查 Hash 快取（Layer 1）...")
    content_hash = cache_service.generate_hash(content)
    cached_record = pandas_store.find_by_hash(content_hash)
    
    if cached_record:
        print(f"🎯 Layer 1 快取命中！")
        print(f"   風險類型: {cached_record.get('risk_type')}")
        print(f"   分類: {cached_record.get('category')}")
        print(f"   可信度: {cached_record.get('confidence_score')}")
        return cached_record
    
    print("   ⏭️  未命中快取，繼續分析...\n")
    
    # ===== Step 3: AI 分析 =====
    print("3️⃣ 執行 AI 分析（Gemini）...")
    try:
        ai_result = ai_service.analyze_content(content, url=url)
        print("✅ AI 分析完成\n")
        print("📊 分析結果:")
        print(f"   - 是否為風險: {ai_result.get('is_risk')}")
        print(f"   - 風險類型: {ai_result.get('risk_type')}")
        print(f"   - 分類: {ai_result.get('category')}")
        print(f"   - 可信度分數: {ai_result.get('confidence_score')}")
        print(f"   - 摘要: {ai_result.get('summary', '')[:100]}...")
        print(f"   - 說明: {ai_result.get('explanation', '')[:100]}...")
        print()
    except Exception as e:
        print(f"❌ AI 分析失敗: {str(e)}")
        print("\n⚠️  請確認:")
        print("   1. .env 檔案中的 GOOGLE_API_KEY 已正確設定")
        print("   2. API Key 有效且有足夠配額")
        return
    
    # ===== Step 4: 儲存到 Pandas =====
    print("4️⃣ 儲存結果到 Pandas...")
    try:
        record = pandas_store.save_record(
            data_type="URL",
            raw_content=content,
            content_hash=content_hash,
            content_vector=None,  # 簡化版先不存向量
            ai_result=ai_result
        )
        print(f"✅ 已寫入 knowledge_base.parquet")
        print(f"   記錄 ID: {record['id']}")
        print(f"   檔案位置: {pandas_store.knowledge_base_path}")
        print()
    except Exception as e:
        print(f"❌ 儲存失敗: {str(e)}")
        return
    
    # ===== Step 5: 驗證讀取 =====
    print("5️⃣ 驗證讀取...")
    all_records = pandas_store.get_all_records()
    print(f"✅ 知識庫目前有 {len(all_records)} 筆記錄")
    
    print("\n🎉 測試完成！")
    print("\n📝 下一步:")
    print("   - 你可以在 Node.js 後端讀取 data/knowledge_base.parquet")
    print("   - 或使用 pandas.read_parquet() 來查詢記錄")


if __name__ == "__main__":
    asyncio.run(test_ai_pipeline())

