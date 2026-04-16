from __future__ import annotations

import os
import sys


def main() -> None:
    """
    啟動後端 API（供其他系統/部署腳本呼叫）。

    用法：
      factcheck-system-api
      FACTCHECK_HOST=0.0.0.0 FACTCHECK_PORT=8000 factcheck-system-api
    """
    host = os.getenv("FACTCHECK_HOST", "127.0.0.1")
    port = int(os.getenv("FACTCHECK_PORT", "8000"))

    try:
        import uvicorn
    except Exception as e:
        print(f"無法匯入 uvicorn: {e}", file=sys.stderr)
        raise

    uvicorn.run("app.main:app", host=host, port=port, reload=False)

