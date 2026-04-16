"""
RQ Worker 主程式（背景任務執行器）
"""
import os
from rq import Worker, Queue, Connection
from redis import Redis
from app.config import settings

if __name__ == '__main__':
    # 建立 Redis 連線
    redis_conn = Redis.from_url(settings.REDIS_URL)
    
    # 建立佇列
    queue = Queue(settings.QUEUE_NAME, connection=redis_conn)
    
    # 啟動 Worker
    with Connection(redis_conn):
        worker = Worker([queue])
        print(f"🚀 Worker 啟動，監聽佇列: {settings.QUEUE_NAME}")
        worker.work()

