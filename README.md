# AI-Driven Fake News and Scam Verification System

![CI](https://github.com/cansfakenewsverify/AI-Fake-News-Verification-System/actions/workflows/ci.yml/badge.svg)
![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-blue)
![React 19](https://img.shields.io/badge/Frontend-React%2019-61DAFB?logo=react&logoColor=white)
![FastAPI](https://img.shields.io/badge/Backend-FastAPI-009688?logo=fastapi&logoColor=white)
![SQLite + Parquet](https://img.shields.io/badge/Storage-SQLite%20%2B%20Parquet-336791)
![Accuracy 96%](https://img.shields.io/badge/Eval-accuracy%2096%25%20%2F%20FN%3D0-success)

整合 **myai168 OpenAI/Claude** 與 **CGU AIR Gateway** 多 AI provider，加上多元事實查核資料來源，提供**自動化假訊息辨識**與**熱門詐騙趨勢追蹤**的全端應用程式。

> 🎯 **核心特色**：三層快取（URL / Hash / Vector，門檻經實測校準）大幅降低 AI 成本；
> 自動從 MyGoPen、TFC、Cofacts、Google News 抓取熱門查核並索引謠言原文；
> 支援文字、網址、圖片三種輸入；150 筆標註集評測 **accuracy 96%、漏判 FN=0**。

---

## 🚀 一鍵啟動

### Windows
```
雙擊 start.bat
```

### macOS / Linux
```bash
chmod +x start.sh && ./start.sh
```

啟動後自動：
1. 建立 Python 虛擬環境並安裝套件
2. 安裝前端 npm 套件（首次）
3. 開兩個視窗（後端 FastAPI + React 主介面）
4. 自動開啟瀏覽器到 http://localhost:5173

**首次使用前**：複製 `code/backend/.env.example` 為 `code/backend/.env`，填入 `MYAI_API_KEY` 或 `CGU_API_KEY`，並用 `AI_PROVIDER=openai` / `claude` / `cgu` 選擇 AI 方案。

> 🧯 **離線備援**：`fake-news-detector.html`（單檔查核儀）雙擊即可離線 demo
> （前端啟發式＋範例資料）；要接真後端時跑 `_run_detector.bat`（port 8090）。

---

## ✨ Features

| 功能 | 說明 |
|------|------|
| **三層智能快取** | URL（完全相符）→ Hash（內容相符）→ Vector（語義相似，門檻 0.75 實測校準），「換句話說的謠言」也命中，省下最貴的 AI 呼叫 |
| **自動趨勢抓取** | 每 6 小時從 MyGoPen / TFC / Cofacts / Google News 抓取最新查核（opt-in） |
| **假訊息原文索引** | 從查核文章提取謠言原文＋向量，使用者再輸入時直接命中查證來源 |
| **多模態輸入** | 文字 / 網址 / 圖片三種模式，圖片支援拖曳上傳；影片自動抓字幕或 whisper 逐字稿 |
| **多 AI Provider** | myai168 OpenAI/Claude + CGU AIR Gateway，`AI_PROVIDER` 切換、自動備援 |
| **Threads 查核機器人** | @機器人回覆可疑貼文 → 自動回覆紅黃綠判定＋來源（延伸功能，預設關） |
| **防 AI 幻覺** | Prompt 嚴禁編造 URL + 後端對 sources URL 做 HEAD 驗證 |
| **韌性設計** | AI 額度用盡時前端優雅降級（離線啟發式／分析失敗提示）；查核儀可完全離線運作 |
| **可驗證品質** | 150 筆標註集評測（accuracy 96%、FN=0）＋ 31 個單元測試＋ GitHub Actions CI |

---

## 🛠️ 技術堆疊

**後端**
- FastAPI + Uvicorn（阻塞呼叫全走 `asyncio.to_thread`，分析期間 API 不卡死）
- SQLAlchemy + SQLite(趨勢資料)；Pandas + Parquet(三層快取知識庫，向量搜尋 numpy 矩陣化)
- myai168 OpenAI/Claude + CGU AIR Gateway（OpenAI-compatible Responses API）
- CGU embedding（text-embedding-3-small, 1536 維）/ Gemini 備援
- APScheduler（背景排程，opt-in）
- Trafilatura + BeautifulSoup4 + Playwright + yt-dlp（爬蟲/影音）

**前端**
- React 19 + Vite 8 + Tailwind CSS 4（設計 token、深/淺色主題）
- 單檔查核儀（零依賴 HTML，離線備援）

**品質**
- pytest（31 tests，離線零 AI 成本）+ GitHub Actions CI
- `scripts/evaluate.py` 評測管線（混淆矩陣 / P/R/F1 / FP/FN 分析）

---

## 📁 專案結構

```
AI-Fake-News-Verification-System/
├── README.md                    ← 本檔
├── CLAUDE.md                    ← 專案完整技術地圖（AI 助理/接手者必讀）
├── start.bat / start.sh         ← 一鍵啟動（後端 + React）
├── fake-news-detector.html      ← 單檔查核儀（離線備援）
├── _run_detector.bat            ← 查核儀靜態伺服器（8090，選用）
│
├── code/
│   ├── backend/                 ← FastAPI 後端
│   │   ├── app/
│   │   │   ├── api/             ← analyze / trending / knowledge / threads / admin / feedback
│   │   │   ├── services/        ← AI 多引擎 / 爬蟲 / 三層快取 / 新聞抓取 / Threads
│   │   │   ├── workers/         ← 分析主流程 / Threads 機器人
│   │   │   ├── models/          ← SQLite 熱門記錄 model
│   │   │   └── utils/           ← URL 幻覺過濾
│   │   ├── tests/               ← 31 個單元測試（CI 自動跑）
│   │   ├── scripts/             ← 評測 / 批次查證 / provider 測試 / Threads 測試
│   │   ├── data/                ← SQLite + Parquet + 評測資料（SCHEMA.md 有欄位定義）
│   │   ├── .env.example         ← 環境變數範本
│   │   └── requirements.txt
│   │
│   └── frontend/                ← React 主介面
│       └── src/                 ← App.jsx / index.css(設計token) / mockData.js(風險樣式)
│
├── .github/workflows/ci.yml     ← push/PR 自動跑測試
├── assets/                      ← 架構圖（PlantUML）+ 混淆矩陣
└── 期末專題文件/                 ← OOSE 文件（使用案例/活動圖/類別圖）
```

---

## 📖 使用方式

### 1. 查證單筆訊息（前端）

開啟 http://localhost:5173，選擇輸入方式：

| 模式 | 範例 |
|------|------|
| 文字 | 「投資老師帶單穩賺不賠，加 LINE...」 |
| 網址 | https://example.com/article |
| 圖片 | 拖曳手機截圖、廣告圖 |

點「發布查證」後，AI 會回傳：
- 🔴 紅框：高風險詐騙 / 已查核假訊息
- 🟡 黃框：尚待確認
- 🟢 綠框：安全資訊

命中快取時會標示「快取·語意相似」等字樣（未重複呼叫 AI）。

### 2. 瀏覽熱門趨勢與查證資料庫

「今日熱門趨勢」顯示最新查核結果（可手動觸發更新）；「資料庫」分頁可搜尋/篩選
已查證的快取內容。

### 3. 程式化 API

```bash
# 同步查證（一次回傳結果，適合自動化/手機捷徑）
curl -X POST http://localhost:8000/api/analyze/sync \
  -H "Content-Type: application/json" \
  -d '{"content":"健康謠言..."}'

# 熱門趨勢 / 知識庫
curl "http://localhost:8000/api/trending?limit=10"
curl "http://localhost:8000/api/knowledge?q=詐騙&limit=20"

# Swagger 文件
open http://localhost:8000/docs
```

### 4. 評測與工具

```powershell
cd code\backend
.\venv\Scripts\python scripts\evaluate.py --report-only   # 重算評測報告（零成本）
.\venv\Scripts\python scripts\batch_verify_pending.py     # 批次查證熱門 PENDING
.\venv\Scripts\python -m pytest tests -q                  # 單元測試
```

---

## ⚙️ 環境變數（`.env`）

| 變數 | 預設值 | 說明 |
|------|--------|------|
| `AI_PROVIDER` | `openai` | `openai` / `claude` 使用 myai168；`cgu` 使用 CGU AIR Gateway |
| `MYAI_API_KEY` | 空 | myai168 OpenAI/Claude 共用金鑰 |
| `CGU_API_KEY` | 空 | CGU AIR Gateway 金鑰 |
| `EMBED_API_KEY` | 空 | 向量 embedding 金鑰（空時退用 CGU_API_KEY） |
| `DEMO_MODE` | `false` | `true` 時回傳假資料，不呼叫 API |
| `ENABLE_SCHEDULER` | `false` | 背景自動抓新聞（會持續花點數） |
| `ENABLE_THREADS_BOT` | `false` | Threads 查核機器人（需 Meta token） |
| `USE_WEB_SEARCH` | `true` | 分析時帶 web_search 佐證（貴 3~7 倍） |
| `SIMILARITY_THRESHOLD` | `0.75` | 向量快取命中門檻（實測校準值） |

完整列表請參考 [`code/backend/.env.example`](code/backend/.env.example)。

---

## 📊 評測（論文數據）

150 筆人工標註資料集（SCAM/MISINFO/SAFE 各 50，含刻意設計的「像詐騙的合法官方訊息」難題）：

| 指標 | 結果 |
|------|------|
| Accuracy | **96.0%** |
| Macro-F1 | 0.960 |
| 偽陰性 FN（漏判風險） | **0** |
| 偽陽性 FP（誤報） | 5（多為反詐宣導被過度反應） |

重現方式與錯誤分析見 [`code/backend/README.md`](code/backend/README.md)。

---

## 🐳 Docker 部署

```bash
cd code/backend
docker-compose up -d      # 單一 backend 容器（SQLite + Parquet，免資料庫服務）
```

前端 `npm run build` 出靜態檔後由 nginx 服務並反代 `/api`（見 `code/frontend/nginx.conf`）。

---

## 👥 Authors

- **廖晢勛** — 系統架構設計、API 整合、專案時程管理
- **石岱勳** — Prompt Engineering、Gemini API 邏輯實作

## 📄 License

學術用途；引用請註明來源。
