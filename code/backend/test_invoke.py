import sys
from pathlib import Path
import asyncio

base_dir = Path(__file__).resolve().parent
factcheck_dir = base_dir / "factcheck_system"
sys.path.insert(0, str(factcheck_dir))

from app.services.task_store import TaskStore
from app.workers.task_queue import enqueue_analysis_task

async def main():
    try:
        task_store = TaskStore()
        content = "https://tw.news.yahoo.com/example"
        task_id = task_store.create_task("analyze_text", content)
        print("Task created:", task_id)
        enqueue_analysis_task(task_id, content, "url")
        print("Enqueued!")
    except Exception as e:
        print("ERROR:", str(e))
        import traceback
        traceback.print_exc()

asyncio.run(main())
