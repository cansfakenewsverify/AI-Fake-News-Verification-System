# Factcheck System Backend

FastAPI 後端，負責 AI 查證、爬蟲、三層快取、熱門趨勢抓取、Threads 查核機器人。

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
│   ├── analyze.py        ← /api/analyze/* (文字 / URL / 圖片；sync 同步端點)
│   ├── trending.py       ← /api/trending (熱門趨勢)
│   ├── knowledge.py      ← /api/knowledge (瀏覽/搜尋快取知識庫)
│   ├── threads.py        ← /api/threads (Threads 機器人狀態/手動觸發)
│   ├── admin.py          ← /api/admin (人工覆寫)
│   └── feedback.py       ← /api/feedback (使用者評分)
│
├── services/             ← 業務邏輯
│   ├── ai_service.py     ← 多引擎（myai168 OpenAI/Claude + CGU AIR）、web_search 佐證、語音轉文字
│   ├── crawler.py        ← Trafilatura + Playwright 爬蟲、影片字幕／STT 逐字稿
│   ├── cache_service.py  ← 內容 SHA-256 指紋
│   ├── pandas_store.py   ← Parquet 三層快取（向量搜尋 numpy 矩陣化）
│   ├── vector_service.py ← Embedding 包裝
│   ├── search_service.py ← RSS / Cofacts / Google News 聚合
│   ├── news_fetcher.py   ← 兩階段熱門新聞處理流程（標記規則見專案根 CLAUDE.md 第 9 節）
│   ├── threads_service.py← Threads Graph API 客戶端 + 回覆格式化
│   ├── task_store.py     ← 非同步任務狀態（Parquet，自動修剪保留最近 500 筆）
│   └── audit_store.py    ← 覆寫、評分記錄
│
├── workers/
│   ├── pandas_task_processor.py  ← 三層快取 + AI 分析主流程
│   └── threads_bot.py            ← Threads 機器人輪詢（mentions→分析→回覆）
│
├── models/
│   └── fact_check_record.py      ← 熱門趨勢記錄（SQLite，唯一的 SQLAlchemy model）
│
├── utils/
│   └── url_validator.py  ← AI 回傳 sources URL 的 HEAD 驗證（過濾幻覺連結）
│
├── config.py             ← Pydantic Settings（讀 .env，UTF-8）
├── database_sql.py       ← SQLite engine
└── main.py               ← FastAPI 入口 + APScheduler（排程皆 opt-in）

tests/                    ← pytest 單元測試（30 tests、離線零點數；CI 自動跑）
```

---

## 環境變數

複製 `.env.example` 為 `.env` 並填入：

```ini
# Provider 選擇：openai / claude = 原本 myai168；cgu = CGU AIR Gateway 新增選項
AI_PROVIDER=openai

# 方案 A：myai168 中繼閘道（原本方案，保留）
MYAI_API_KEY=your_developer_key_here

CLAUDE_RELAY_URL=https://www.myai168.com/cgu/api/anthropic/v1
CLAUDE_MODEL=claude-opus-4-8
OPENAI_RELAY_URL=https://www.myai168.com/cgu/api/openai/v1
OPENAI_MODEL=gpt-5-mini
OPENAI_REASONING_EFFORT=minimal

# 方案 B：CGU AIR Gateway（OpenAI 相容 Responses API）
# 參考：https://air.cgu.edu.tw/workspace4/LLMAPI/api_call.html
CGU_API_KEY=your_cgu_api_key_here
CGU_BASE_URL=https://air.cgu.edu.tw/cgullmapi/v1
CGU_MODEL=gpt-5.4-mini
CGU_REASONING_EFFORT=medium
CGU_STT_MODEL=gpt-4o-mini-transcribe

# 向量 embedding：CGU AIR Gateway（EMBED_API_KEY 空時會退用 CGU_API_KEY）
EMBED_RELAY_URL=https://air.cgu.edu.tw/cgullmapi/v1
EMBED_API_KEY=your_cgu_api_key_here
EMBED_MODEL=text-embedding-3-small

# 選填：Gemini embedding 備援（CGU 失敗時才用，可留空）
GOOGLE_API_KEY=

DEMO_MODE=false
TRENDING_FETCH_INTERVAL_HOURS=6
# 向量層門檻：0.75 為實測校準值（改寫版同謠言 0.79~0.82、不同謠言 <=0.68）
SIMILARITY_THRESHOLD=0.75
```

> **AI 引擎**：`AI_PROVIDER=openai` / `claude` 使用原本 myai168 中繼；
> `AI_PROVIDER=cgu` 使用 CGU AIR Gateway（OpenAI 相容 `/responses`）。
> fallback 順序：`cgu -> openai -> claude`、`openai -> claude -> cgu`、`claude -> openai -> cgu`。
> 影片無字幕時，以 `whisper` 語音轉文字補上逐字稿。
> **向量 embedding** 走 CGU AIR Gateway（`text-embedding-3-small`，1536 維），
> 啟用 Layer 2 語義快取；失敗時退到 Gemini，皆無則自動停用向量層。

---

## 資料儲存

| 檔案 | 內容 |
|------|------|
| `data/factcheck.db` | SQLite，熱門趨勢記錄 |
| `data/knowledge_base.parquet` | 三層快取知識庫（含向量） |
| `data/tasks.parquet` | 非同步任務狀態（自動保留最近 500 筆） |
| `data/uploads/` | 圖片暫存（分析完自動刪除） |
| `data/threads_state.json` | Threads 機器人已回覆記錄（gitignored） |

Schema 詳見 [`data/SCHEMA.md`](data/SCHEMA.md)。

---

## 工具腳本

```powershell
# 檢視資料庫內容
.\venv\Scripts\python scripts\check_db.py

# 灌入範本資料（測試用）
.\venv\Scripts\python scripts\seed_data.py

# 評測判定引擎（混淆矩陣 / accuracy / P/R/F1；會呼叫 AI 花點數）
.\venv\Scripts\python scripts\evaluate.py
.\venv\Scripts\python scripts\evaluate.py --report-only   # 只重算報告，零點數

# 測試目前 AI provider（低成本 smoke test）
.\venv\Scripts\python scripts\test_ai_provider.py --provider cgu

# 批次查證熱門 PENDING（抓 RSS + AI 分析直到清空，內建預算護欄）
.\venv\Scripts\python scripts\batch_verify_pending.py

# Threads 機器人：乾跑 / 驗憑證 / 真跑一輪
.\venv\Scripts\python scripts\test_threads_bot.py [--live | --poll]

# 單元測試（30 tests、離線、零點數）
.\venv\Scripts\python -m pytest tests -q
```

---

## API 文件

啟動後到 http://localhost:8000/docs 看完整 Swagger UI，主要路由：

- `POST /api/analyze/text` — 文字/URL 查證（非同步，回 task_id 後輪詢）
- `POST /api/analyze/sync` — 文字/URL 查證（**同步，一次回傳結果**，適合手機捷徑）
- `POST /api/analyze/image` — 圖片查證（multipart）
- `GET  /api/analyze/task/{id}` — 取得結果
- `GET  /api/trending` — 熱門列表；`POST /api/trending/refresh` 手動觸發抓取
- `GET  /api/knowledge` — 瀏覽/搜尋快取知識庫；`/api/knowledge/stats` 統計
- `GET  /api/threads/status` — Threads 機器人狀態；`POST /api/threads/poll` 手動跑一輪

回應中的 `cached` / `cache_layer`（url / hash / vector）標示是否命中快取與命中層。

---

## 評測（論文數據來源）

判定引擎的效能以 `scripts/evaluate.py` 量測（使用 `.env` 設定的 AI provider），
產出混淆矩陣與各項指標。最新結果：**accuracy 96.0%、macro-F1 0.960、FN=0**。

```powershell
.\venv\Scripts\python scripts\evaluate.py            # 全部 150 筆
.\venv\Scripts\python scripts\evaluate.py --limit 10 # 先試 10 筆
.\venv\Scripts\python scripts\evaluate.py --resume   # 中斷後續跑
.\venv\Scripts\python scripts\evaluate.py --seed-db  # 判對案例回填知識庫
```

產出：
| 檔案 | 內容 |
|------|------|
| `data/eval_predictions.csv` | 每筆的 gold / pred / confidence / 是否正確 |
| `data/eval_report.csv` | 各類 precision / recall / f1 + accuracy + macro-F1 |
| `data/eval_binary.csv` | 二分類 FP/FN（偽陽性/偽陰性） |
| `data/eval_errors.csv` | 判錯案例（錯誤分析用） |
| `../../assets/confusion_matrix.png` | 混淆矩陣熱力圖 |

> **信心分數說明**：`confidence_score` 為模型自評，**未經機率校準**，前端以「高/中/低」呈現。
> 系統真實效能請以本評測報告（accuracy / F1）為準。

---

## 三層快取設計

```
文字輸入 → L1: Hash → L2: 向量(以使用者原文比對，先於爬蟲) → 爬蟲 → L3: AI 分析
網址輸入 → L0: URL → L1: Hash → 爬蟲 → L2: 向量(以內文比對) → L3: AI 分析
                                                結果回填知識庫 ◄──┘
```

對重複與「換句話說」的查詢，省下最貴的 AI 分析呼叫（向量命中實測 ~6s、零 AI 點數）。
Layer 2 門檻 `SIMILARITY_THRESHOLD=0.75` 為實測校準值；未設 `EMBED_API_KEY` 時
向量層自動略過，URL/Hash 兩層仍正常。

---

## Docker

```bash
docker-compose up -d
```

單一 backend 容器（SQLite + Parquet 免資料庫服務）；正式部署可自行加 nginx 反代 `/api`。
