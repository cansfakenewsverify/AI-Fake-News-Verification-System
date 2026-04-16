## Factcheck System（後端 + 爬蟲模組）

本專案已打包成可安裝的 Python 套件，方便與其他系統模組整合。

### 安裝（開發模式）

```bash
cd c:\Users\user\factcheck_system
.\.venv\Scripts\python.exe -m pip install -e .
```

### 啟動後端

```bash
factcheck-system-api
```

或指定 host/port：

```bash
set FACTCHECK_HOST=0.0.0.0
set FACTCHECK_PORT=8000
factcheck-system-api
```

### 給其他系統整合的 import 入口

#### 1) 爬蟲

```python
from factcheck_system import CrawlerClient

result = await CrawlerClient.crawl_url("https://example.com/news")
print(result.title, result.screenshot_path)
```

#### 2) AI 分析

```python
from factcheck_system import AIClient

ai = AIClient()
out = ai.analyze_text("要查證的內容", url="https://example.com")
print(out.is_risk, out.risk_type, out.summary)
```

# AI 驅動假訊息驗證系統

## 專案概述

本系統為一套高效、精準且具備可解釋性的 AI 驅動假訊息驗證系統，整合大型語言模型（LLM）與向量資料庫技術，提供即時的事實查核服務。

## 快速開始

### 1. 設定環境變數

```bash
# 已建立 .env 檔案，請編輯填入 API Keys
# 必須設定：
# - GOOGLE_API_KEY
# - DATABASE_URL
# - REDIS_URL
```

### 2. 安裝依賴

```bash
pip install -r requirements.txt
```

### 3. 啟動服務

```bash
# 啟動 PostgreSQL 和 Redis
docker-compose up -d postgres redis

# 初始化資料庫
python scripts/init_db.py
alembic upgrade head

# 啟動 API 伺服器
uvicorn app.main:app --reload
```

## API 文件

訪問: http://localhost:8000/docs

