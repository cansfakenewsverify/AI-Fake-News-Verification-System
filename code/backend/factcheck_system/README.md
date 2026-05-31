# Factcheck System Backend

FastAPI 後端，負責 AI 查證、爬蟲、三層快取、熱門趨勢抓取。

## 快速啟動

```powershell
# 從專案根目錄
.\start.bat        # Windows
./start.sh         # macOS / Linux
```

或單獨啟動後端：

```powershell
# 雙擊
_run_backend.bat

# 或手動
.\venv\Scripts\activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

啟動後：
- API 服務：http://localhost:8000
- Swagger UI：http://localhost:8000/docs

---

## 模組結構

```
app/
├── api/                  ← REST 路由
│   ├── analyze.py        ← /api/analyze/* (文字 / URL / 圖片)
│   ├── trending.py       ← /api/trending (熱門趨勢)
│   ├── admin.py          ← /api/admin (人工覆寫)
│   └── feedback.py       ← /api/feedback (使用者評分)
│
├── services/             ← 業務邏輯
│   ├── ai_service.py     ← Gemini 呼叫、Embedding、Prompt
│   ├── crawler.py        ← Trafilatura + Playwright 爬蟲
│   ├── cache_service.py  ← Hash 工具 + PostgreSQL 快取（lazy import）
│   ├── pandas_store.py   ← Parquet 三層快取實作
│   ├── vector_service.py ← Embedding 包裝
│   ├── search_service.py ← RSS / Cofacts / Google News 聚合
│   ├── news_fetcher.py   ← 兩階段熱門新聞處理流程
│   ├── task_store.py     ← 非同步任務狀態（Parquet）
│   └── audit_store.py    ← 覆寫、評分記錄
│
├── workers/
│   └── pandas_task_processor.py  ← 三層快取 + AI 分析主流程
│
├── models/               ← SQLAlchemy 資料模型
│   ├── fact_check_record.py    ← 熱門趨勢用（SQLite）
│   └── scam_knowledge_base.py  ← PostgreSQL/pgvector 用（未啟用）
│
├── utils/
│   └── url_validator.py  ← AI 回傳 sources URL 的 HEAD 驗證
│
├── config.py             ← Pydantic Settings
├── database_sql.py       ← SQLite engine (預設)
├── database.py           ← PostgreSQL engine (備用)
└── main.py               ← FastAPI 入口 + APScheduler
```

---

## 環境變數

複製 `.env.example` 為 `.env` 並填入：

```ini
GOOGLE_API_KEY=your_api_key_here
DEMO_MODE=false
TRENDING_FETCH_INTERVAL_HOURS=6
SIMILARITY_THRESHOLD=0.95
```

---

## 資料儲存

| 檔案 | 內容 |
|------|------|
| `data/factcheck.db` | SQLite，熱門趨勢記錄 |
| `data/knowledge_base.parquet` | 三層快取知識庫（含向量） |
| `data/tasks.parquet` | 非同步任務狀態 |
| `data/uploads/` | 圖片暫存（分析完自動刪除） |

Schema 詳見 [`data/SCHEMA.md`](data/SCHEMA.md)。

---

## 工具腳本

```powershell
# 檢視資料庫內容
.\venv\Scripts\python scripts\check_db.py

# 灌入範本資料（測試用）
.\venv\Scripts\python scripts\seed_data.py
```

---

## API 文件

啟動後到 http://localhost:8000/docs 看完整 Swagger UI，主要路由：

- `POST /api/analyze/text` — 文字/URL 查證
- `POST /api/analyze/image` — 圖片查證（multipart）
- `GET  /api/analyze/task/{id}` — 取得結果
- `GET  /api/trending` — 熱門列表
- `POST /api/trending/refresh` — 手動觸發抓取

---

## 開發

```powershell
# 套件以開發模式安裝（會自動讀取目前的程式碼變動）
pip install -e .

# Hot reload 已開啟，存檔即自動重啟
```

`pyproject.toml` 已定義為可安裝套件（`pip install -e .`），其他模組可：

```python
from factcheck_system import CrawlerClient, AIClient
```

避免直接耦合 `app.*` 結構。

---

## 三層快取設計

```
輸入 → Layer 0: URL → Layer 1: Hash → Layer 2: Vector → Layer 3: Gemini
                                                              │
                                          結果回填知識庫 ◄────┘
```

對重複查詢，省下最貴的 Gemini 分析呼叫。

---

## Docker

```bash
docker-compose up -d
```

啟動完整環境（後端 + 前端 nginx + PostgreSQL + Redis）。
