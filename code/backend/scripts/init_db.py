"""
初始化資料庫腳本 - 建立 pgvector 擴展
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import create_engine, text
from app.config import settings

def init_database():
    """初始化資料庫（建立 pgvector 擴展）"""
    try:
        # 建立連線（不使用連線池）
        engine = create_engine(settings.DATABASE_URL)
        
        with engine.connect() as conn:
            # 建立 pgvector 擴展
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            conn.commit()
            print("✅ pgvector 擴展建立成功")
            
            # 建立 UUID 擴展（如果需要的話）
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS \"uuid-ossp\""))
            conn.commit()
            print("✅ uuid-ossp 擴展建立成功")
        
        print("\n🎉 資料庫初始化完成！")
        print("   現在可以執行: alembic upgrade head")
        
    except Exception as e:
        print(f"❌ 資料庫初始化失敗: {str(e)}")
        print("\n請確認：")
        print("1. PostgreSQL 已安裝並運行")
        print("2. pgvector 擴展已安裝到 PostgreSQL")
        print("3. DATABASE_URL 設定正確")
        raise

if __name__ == "__main__":
    init_database()

