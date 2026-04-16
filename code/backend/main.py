import sys
from pathlib import Path

# 將 factcheck_system 目錄加入 Python 路徑，
# 這樣可以直接載入隊友開發的 `app` 模組，而不必更動他們的程式碼。
base_dir = Path(__file__).resolve().parent
factcheck_dir = base_dir / "factcheck_system"
if str(factcheck_dir) not in sys.path:
    sys.path.insert(0, str(factcheck_dir))

# 從隊友的 main.py 匯入完整版 FastAPI app
# 這樣前端原本戳的 API 以及 Uvicorn 啟動都能無縫接軌
from app.main import app

# 如果有需要自定義外掛或是針對現有 frontend 維持相容性的臨時路由，可以寫在這裡
# 目前直接使用隊友的 app 作為進入點
