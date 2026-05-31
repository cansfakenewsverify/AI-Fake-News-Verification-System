# AI-Driven Fake News and Scam Verification System

![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-blue)
![React 19](https://img.shields.io/badge/Frontend-React%2019-61DAFB?logo=react&logoColor=white)
![FastAPI](https://img.shields.io/badge/Backend-FastAPI-009688?logo=fastapi&logoColor=white)
![SQLite + Parquet](https://img.shields.io/badge/Storage-SQLite%20%2B%20Parquet-336791)

整合 **Google Gemini** 大型語言模型與多元事實查核資料來源，提供**自動化假訊息辨識**與**熱門詐騙趨勢追蹤**的全端應用程式。

> 🎯 **核心特色**：三層快取（URL / Hash / Vector）大幅降低 API 成本；自動從 MyGoPen、Cofacts、Google News 抓取熱門查核；支援文字、網址、圖片三種輸入方式。

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
2. 安裝前端 npm 套件
3. 開兩個視窗（後端 + 前端）
4. 自動開啟瀏覽器到 http://localhost:5173

**首次使用前**：到 `code/backend/factcheck_system/.env` 填入 `GOOGLE_API_KEY`（[免費申請](https://aistudio.google.com)）。

---

## ✨ Features

| 功能 | 說明 |
|------|------|
| **三層智能快取** | URL（完全相符）→ Hash（內容相符）→ Vector（語義相似），大幅降低 API 費用 |
| **自動趨勢抓取** | 每 6 小時從 MyGoPen / TFC / Cofacts / Google News 抓取最新查核 |
| **假訊息原文索引** | 從查核文章提取假訊息原文 + 向量，使用者再輸入時直接命中查證來源 |
| **多模態輸入** | 文字 / 網址 / 圖片三種模式，圖片支援拖曳上傳 |
| **背景排程** | APScheduler 每 30 分鐘自動重試 Gemini 暫時失敗的記錄 |
| **熱門趨勢看板** | 前端顯示即時熱門查核結果，可手動觸發更新 |
| **防 AI 幻覺** | Prompt 嚴禁編造 URL + 後端對 sources URL 做 HEAD 驗證 |

---

## 🛠️ 技術堆疊

**後端**
- FastAPI + Uvicorn
- SQLAlchemy + SQLite（趨勢資料）
- Pandas + Parquet（三層快取知識庫）
- Google Gemini（gemini-2.5-flash + text-embedding-004）
- APScheduler（背景排程）
- Trafilatura + Beautifulsoup4（爬蟲）

**前端**
- React 19 + Vite 8
- Tailwind CSS 4
- 漸層 UI、骨架載入、動效

**部署**
- Docker Compose（前端 nginx + 後端 + PostgreSQL）
- 可選擇 Render / Fly.io / Railway 免費雲端

---

## 📁 專案結構

```
AI-Fake-News-Verification-System/
├── README.md                          ← 本檔
├── start.bat / start.sh               ← 一鍵啟動腳本
│
├── code/
│   ├── backend/factcheck_system/      ← FastAPI 後端
│   │   ├── app/
│   │   │   ├── api/                   ← REST 路由（analyze / trending / admin / feedback）
│   │   │   ├── services/              ← 業務邏輯（AI / 爬蟲 / 快取 / 向量 / 新聞抓取）
│   │   │   ├── models/                ← SQLAlchemy 資料模型
│   │   │   ├── workers/               ← 非同步任務處理
│   │   │   ├── utils/                 ← URL 驗證等工具
│   │   │   ├── config.py              ← 設定
│   │   │   ├── database_sql.py        ← SQLite 連線
│   │   │   └── main.py                ← FastAPI 入口
│   │   ├── data/                      ← SQLite + Parquet 資料檔
│   │   │   ├── SCHEMA.md              ← 資料庫 schema 說明
│   │   │   ├── factcheck.db
│   │   │   └── knowledge_base.parquet
│   │   ├── scripts/                   ← 工具腳本
│   │   │   ├── check_db.py            ← 檢視資料庫
│   │   │   └── seed_data.py           ← 灌入範本資料
│   │   ├── _run_backend.bat           ← 後端啟動器
│   │   ├── .env.example               ← 環境變數範本
│   │   └── requirements.txt
│   │
│   └── frontend/                      ← React 前端
│       ├── src/
│       │   ├── App.jsx                ← 主元件
│       │   └── index.css              ← Tailwind + 自訂動效
│       ├── _run_frontend.bat
│       ├── Dockerfile                 ← 雲端部署
│       └── nginx.conf
│
├── docs/                              ← 白皮書、需求規格
├── presentations/                     ← 投影片、行政表格
└── assets/                            ← 架構圖、Demo 截圖
```

---

## 📖 使用方式

### 1. 查證單筆訊息（前端）

開啟 http://localhost:5173，選擇輸入方式：

| 模式 | 範例 |
|------|------|
| 📝 文字 | 「投資老師帶單穩賺不賠，加 LINE...」 |
| 🔗 網址 | https://example.com/article |
| 🖼️ 圖片 | 拖曳手機截圖、廣告圖 |

點「發布查證」後，AI 會回傳：
- 🚨 紅框：高風險詐騙 / 已查核假訊息
- ⚠️ 黃框：尚待確認
- ✅ 綠框：安全資訊

### 2. 瀏覽熱門趨勢

頁面頂部「**今日熱門趨勢**」自動顯示最新假訊息查核，點「立即更新」可手動觸發抓取。

### 3. 程式化 API

```bash
# 文字查證
curl -X POST http://localhost:8000/api/analyze/text \
  -H "Content-Type: application/json" \
  -d '{"content":"健康謠言..."}'

# 取得熱門趨勢
curl http://localhost:8000/api/trending?limit=10

# Swagger 文件
open http://localhost:8000/docs
```

### 4. 檢查資料庫

```powershell
cd code\backend\factcheck_system
.\venv\Scripts\python scripts\check_db.py
```

---

## ⚙️ 環境變數（`.env`）

| 變數 | 預設值 | 說明 |
|------|--------|------|
| `GOOGLE_API_KEY` | （必填） | Gemini API Key |
| `DEMO_MODE` | `false` | `true` 時回傳假資料，不呼叫 API |
| `TRENDING_FETCH_INTERVAL_HOURS` | `6` | 熱門新聞抓取間隔 |
| `SIMILARITY_THRESHOLD` | `0.95` | 向量快取命中門檻 |
| `SERPER_API_KEY` | 空 | （選填）Serper 搜尋 API，加強搜尋品質 |

完整列表請參考 [`code/backend/factcheck_system/.env.example`](code/backend/factcheck_system/.env.example)。

---

## 🐳 Docker 部署（雲端）

```bash
cd code/backend/factcheck_system
docker-compose up -d
```

會同時啟動：
- 前端 nginx（port 80）
- 後端 FastAPI（port 8000）
- PostgreSQL + pgvector
- Redis

詳見 [`code/backend/factcheck_system/docker-compose.yml`](code/backend/factcheck_system/docker-compose.yml)。

---

## 👥 Authors

- **廖晢勛** — 系統架構設計、API 整合、專案時程管理
- **石岱勳** — Prompt Engineering、Gemini API 邏輯實作

## 📄 License

學術用途；引用請註明來源。
