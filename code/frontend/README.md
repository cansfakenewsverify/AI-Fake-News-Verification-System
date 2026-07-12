# Frontend (React + Vite)

「全民查證公社」React 前端，採用 Vite + Tailwind CSS 4，提供查證介面與熱門趨勢看板。

## 快速啟動

從專案根目錄雙擊 `start.bat`（會同時起前後端）。

或單獨啟動前端：

```bash
# 雙擊 _run_frontend.bat（Windows）
# 或手動執行：
npm install
npm run dev
```

開發伺服器：http://localhost:5173

---

## 結構

```
src/
├── App.jsx        ← 主元件（包含 TrendingSection、AiResultCard、Composer）
├── main.jsx       ← React 入口
├── index.css      ← Tailwind import + 自訂動效（shimmer、fade-in、btn-primary）
└── assets/

public/            ← 靜態資源
index.html         ← Vite 入口模板
vite.config.js     ← 已設定 /api proxy → http://localhost:8000
```

---

## 主要元件（App.jsx 內）

| 元件 | 功能 |
|------|------|
| `App` | 主元件，管理發文列表、輸入狀態與深/淺色主題（localStorage 記憶） |
| `TrendingSection` | 今日熱門趨勢看板，輪詢 `/api/trending` |
| `KnowledgeSection` | 「資料庫」分頁：伺服器端搜尋/篩選快取知識庫 + 統計卡 |
| `InfoCard` | 熱門/資料庫共用的資訊卡片 |
| `AnalyzingCard` | AI 分析中骨架動畫 |
| `AiResultCard` | 紅 / 黃 / 綠分析結果卡片（含快取命中層 chip） |
| `normalizeAiResult` | 辨識 AI 額度用盡的 fallback，轉為「分析失敗」顯示 |
| `getAiCardStyle` | 依 risk_type 回傳對應配色（樣式集中在 `mockData.js` RISK_STYLES） |

---

## API 串接

所有請求走相對路徑 `/api/...`，由 Vite proxy 轉送：

| 動作 | 路徑 | 方法 |
|------|------|------|
| 文字查證 | `/api/analyze/text` | POST |
| 網址查證 | `/api/analyze/url` | POST |
| 圖片查證 | `/api/analyze/image` | POST（multipart） |
| 取結果 | `/api/analyze/task/{id}` | GET |
| 輪詢狀態 | `/api/analyze/task/{id}/status` | GET |
| 熱門列表 | `/api/trending?limit=N` | GET |
| 觸發更新 | `/api/trending/refresh` | POST |
| 知識庫列表/搜尋 | `/api/knowledge?q=&risk_type=&limit=` | GET |
| 知識庫統計 | `/api/knowledge/stats` | GET |

開發時 Vite 自動 proxy 到 `http://localhost:8000`；
部署到雲端時由 nginx 處理（見 `nginx.conf` 與 `Dockerfile`）。

---

## 樣式系統

採用 **Tailwind CSS v4** + **CSS 設計 token**（`index.css` 的 `--c-*` 變數；
深色為預設，`data-theme="light"` 覆蓋同一組 token，陰影也隨主題切換）：

| Class | 效果 |
|-------|------|
| `.shimmer` | 載入中的微光動畫 |
| `.fade-in` | 卡片淡入 |
| `.analyzing-pulse` | AI 分析中的脈動效果 |
| `.btn-primary` | 青綠微漸層主按鈕 |

色彩語意對應（token）：

| 風險類型 | 記號 / token |
|----------|--------------|
| SCAM | ✕ `--c-risk-high`（紅） |
| MISINFO | ! `--c-risk-mid`（黃） |
| SAFE | ✓ `--c-risk-low`（綠） |
| PENDING / UNVERIFIABLE / UNKNOWN | 中性灰 `--c-muted-soft` |

---

## 部署（Docker）

```bash
docker build -t factcheck-frontend .
docker run -p 80:80 factcheck-frontend
```

（後端的 docker-compose 為 backend-only；前端容器由 nginx 服務靜態檔並反代 `/api`，見 `nginx.conf`。）
