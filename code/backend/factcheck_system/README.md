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
│   ├── ai_service.py     ← 雙引擎（Claude 主／OpenAI 備援）、web_search 佐證、語音轉文字
│   ├── crawler.py        ← Trafilatura + Playwright 爬蟲、影片字幕／STT 逐字稿
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
# 學校 myai168 中繼閘道金鑰（OpenAI 與 Claude 中繼共用同一把）
# 用 MYAI_* 命名，避免被系統內建的 OPENAI_API_KEY / ANTHROPIC_BASE_URL 覆寫
MYAI_API_KEY=your_developer_key_here

# 雙引擎：主引擎 claude（推薦）或 openai，另一個自動作為備援
AI_PROVIDER=claude
CLAUDE_RELAY_URL=https://www.myai168.com/cgu/api/anthropic/v1
CLAUDE_MODEL=claude-opus-4-8
OPENAI_RELAY_URL=https://www.myai168.com/cgu/api/openai/v1
OPENAI_MODEL=gpt-5

# 選填：Gemini 僅供向量 embedding（中繼 API 無此端點，留空則停用 Layer 2）
GOOGLE_API_KEY=

DEMO_MODE=false
TRENDING_FETCH_INTERVAL_HOURS=6
SIMILARITY_THRESHOLD=0.95
```

> **AI 引擎**：分析走學校中繼閘道，主引擎 **Claude Opus**（擅長細緻判斷）、
> 失敗時自動退到 **OpenAI gpt-5**；兩者皆用 `web_search` 取得真實佐證來源。
> 影片無字幕時，以 `whisper` 語音轉文字補上逐字稿。

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

# 評測判定引擎（混淆矩陣 / accuracy / P/R/F1）
.\venv\Scripts\python scripts\evaluate.py
```

---

## API 文件

啟動後到 http://localhost:8000/docs 看完整 Swagger UI，主要路由：

- `POST /api/analyze/text` — 文字/URL 查證（非同步，回 task_id 後輪詢）
- `POST /api/analyze/sync` — 文字/URL 查證（**同步，一次回傳結果**，適合手機捷徑）
- `POST /api/analyze/image` — 圖片查證（multipart）
- `GET  /api/analyze/task/{id}` — 取得結果
- `GET  /api/trending` — 熱門列表
- `POST /api/trending/refresh` — 手動觸發抓取

---

## 評測（論文數據來源）

判定引擎的效能以 `scripts/evaluate.py` 量測，產出混淆矩陣與各項指標：

```powershell
# 1. 確認 .env 的 GOOGLE_API_KEY 已設定且有額度（評測會呼叫真實 Gemini）
# 2. 編輯 data/eval_set.csv，每筆填 gold_label（SCAM / MISINFO / SAFE）
#    內附 30 筆種子範例，建議擴充到 150~300 筆（可取自 Cofacts / TFC / MyGoPen / 165）
.\venv\Scripts\python scripts\evaluate.py            # 全部
.\venv\Scripts\python scripts\evaluate.py --limit 10 # 先試 10 筆
.\venv\Scripts\python scripts\evaluate.py --resume   # 中斷後續跑
```

產出：
| 檔案 | 內容 |
|------|------|
| `data/eval_predictions.csv` | 每筆的 gold / pred / confidence / 是否正確 |
| `data/eval_report.csv` | 各類 precision / recall / f1 + accuracy + macro-F1 |
| `../../assets/confusion_matrix.png` | 混淆矩陣熱力圖 |

> **信心分數說明**：`confidence_score` 為模型自評，**未經機率校準**，前端以「高/中/低」呈現。
> 系統真實效能請以本評測報告（accuracy / F1）為準。

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
輸入 → Layer 0: URL → Layer 1: Hash → Layer 2: Vector → Layer 3: AI 分析
                                                              │
                                          結果回填知識庫 ◄────┘
```

對重複查詢，省下最貴的 AI 分析呼叫（學校中繼閘道：Claude 主／OpenAI 備援）。
（Layer 2 向量層需要 embedding；學校中繼無此端點，未設 `GOOGLE_API_KEY` 時自動略過。）

---

## Docker

```bash
docker-compose up -d
```

啟動完整環境（後端 + 前端 nginx + PostgreSQL + Redis）。
