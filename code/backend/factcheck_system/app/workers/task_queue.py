"""
任務佇列管理（純 Pandas 模式：同步直接處理）

說明：為了讓本機不依賴 Redis/PostgreSQL，也能完成整個流程，
這裡直接呼叫處理器同步執行。
"""


def enqueue_analysis_task(task_id: str, input_data: str, input_type: str):
    """
    將分析任務加入佇列
    
    Args:
        task_id: 任務 ID
        input_data: 輸入資料（文字/URL 或圖片檔案路徑）
        input_type: 輸入類型（text, url, image）
    """
    from app.workers.pandas_task_processor import process_analysis_task

    process_analysis_task(task_id, input_data, input_type)
    return task_id

