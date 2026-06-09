"""
清理測試資料腳本 - 刪除錯誤的測試記錄
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.services.pandas_store import PandasStore
from pathlib import Path

def clear_test_data():
    """清理測試資料"""
    store = PandasStore()
    
    # 刪除錯誤的記錄（confidence_score 為 0.0 且 risk_type 為 SAFE 的記錄）
    df = store.get_all_records()
    
    if df.empty:
        print("✅ 知識庫是空的，無需清理")
        return
    
    print(f"📊 清理前有 {len(df)} 筆記錄")
    
    # 過濾掉錯誤的記錄
    df_clean = df[
        ~((df['confidence_score'] == 0.0) & (df['risk_type'] == 'SAFE'))
    ]
    
    removed_count = len(df) - len(df_clean)
    
    if removed_count > 0:
        # 儲存清理後的資料
        if len(df_clean) > 0:
            df_clean.to_parquet(store.knowledge_base_path, index=False)
            print(f"✅ 已刪除 {removed_count} 筆錯誤記錄")
            print(f"📊 清理後剩餘 {len(df_clean)} 筆記錄")
        else:
            # 如果全部刪除，刪除檔案
            if store.knowledge_base_path.exists():
                store.knowledge_base_path.unlink()
                print(f"✅ 已刪除所有記錄並移除檔案")
    else:
        print("✅ 沒有需要清理的錯誤記錄")

if __name__ == "__main__":
    clear_test_data()

