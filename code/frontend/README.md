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
| `App` | 主元件，管理發文列表與輸入狀態 |
| `TrendingSection` | 今日熱門趨勢看板，輪詢 `/api/trending` |
| `AnalyzingCard` | AI 分析中骨架動畫 |
| `AiResultCard` | 紅 / 黃 / 綠分析結果卡片 |
| `getAiCardStyle` | 依 risk_type 回傳對應配色 |

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

開發時 Vite 自動 proxy 到 `http://localhost:8000`；
部署到雲端時由 nginx 處理（見 `nginx.conf` 與 `Dockerfile`）。

---

## 樣式系統

採用 **Tailwind CSS v4**，搭配自訂 utility（定義在 `index.css`）：

| Class | 效果 |
|-------|------|
| `.shimmer` | 載入中的微光動畫 |
| `.fade-in` | 卡片淡入 |
| `.analyzing-pulse` | AI 分析中的脈動效果 |
| `.btn-primary` | 漸層主按鈕 |

色彩語意對應：

| 風險類型 | 配色 |
|----------|------|
| SCAM | red / rose |
| MISINFO | amber / orange |
| SAFE | emerald / teal |
| PENDING / UNKNOWN | slate |

---

## 部署（Docker）

```bash
docker build -t factcheck-frontend .
docker run -p 80:80 factcheck-frontend
```

或從專案根 docker-compose 一鍵啟動所有服務。
