# Frontend（React + Vite）

「全民查證公社」的網頁前端：React 19 + Vite 8.3.0 + Tailwind CSS 4 + React Router 7。

> 線上版本：**https://fakenewsverify.vercel.app**（部署在 Vercel）。要使用系統，開這個網址就可以。
> 本機的 dev server 只有改前端程式時才需要。

---

## ☁️ 部署（Vercel）

| 項目 | 內容 |
|------|------|
| Root Directory | `code/frontend`（Vercel 專案設定） |
| Build | `npm run build`，輸出到 `dist/` |
| API 代理 | [`vercel.json`](vercel.json) 把 `/api/*` rewrite 到 Render 後端 `https://fakenewsverify-api.onrender.com/api/*`。對瀏覽器來說 API 與網頁同源，前端程式一律呼叫相對路徑 `/api/...` |
| SPA fallback | 同一個 `vercel.json`：不是 `.html` 結尾的路徑都回 `index.html`，所以直接打開 `/r/<id>`、`/trending` 這類網址也能運作 |
| 靜態檔 | `public/` 的檔案原樣提供：`privacy.html`、`data-deletion.html`、`deauthorize.html`（Meta App 需要的三個頁面）、`og.png`、`demo/demo_v0.4.0.mp4`（demo 影片，約 12 MB） |

`main` 分支 push 之後 Vercel 會自動重新部署。後端搬家時，只要改 `vercel.json` 的 `destination`。完整的上雲步驟見 [`docs/rebuild/runbook_cloud_deploy.md`](../../docs/rebuild/runbook_cloud_deploy.md)。

Demo 影片網址：https://fakenewsverify.vercel.app/demo/demo_v0.4.0.mp4

---

## 💻 本機開發

需要 Node.js 20.19 以上（Vite 8.3.0 的要求；CI 用 Node 20）。

```powershell
cd code\frontend
npm install
npm run dev
```

- dev server：http://localhost:5173
- [`vite.config.js`](vite.config.js) 把 `/api` 代理到 `http://localhost:8000`，所以要查證功能可用，後端也要在本機跑起來（見 [`code/backend/README.md`](../backend/README.md)）。從專案根目錄跑 `.\start.bat` 會同時啟動兩邊；`_run_frontend.bat` 是它用來開前端視窗的輔助檔。
- 不想啟動後端時，用下面的 fixture 模式。

可用的環境變數（都是選填）：

| 變數 | 用途 |
|------|------|
| `VITE_FIXTURES=1` | 開發用 fixture 模式（見下方），只在 dev server 生效 |
| `VITE_API_BASE_URL` | API 的 base URL；預設空字串，也就是同源的 `/api` |
| `VITE_BRAND_NAME` | 品牌名稱；預設「全民查證公社」 |

---

## 🧭 路由

定義在 [`src/routes.jsx`](src/routes.jsx)，所有頁面都包在 `AppShell`（頂欄、導覽、頁尾、「連不上伺服器」橫幅）裡。

| 路徑 | 頁面 | 說明 |
|------|------|------|
| `/` | `pages/Home.jsx` | 首頁：輸入卡（文字／網址）、範例、Threads 說明卡、最近查證 |
| `/r/:id` | `pages/Result.jsx` | 結果頁，可分享。輪詢 `/api/result/{id}`，依狀態顯示載入、成功、無法查證、AI 暫時無法使用、找不到、錯誤 |
| `/trending` | `pages/Trending.jsx` | 熱門：兩個分頁，「查核機構最新」（熱門牆）與「本站熱門查證」（`?tab=hot`，最近 7 天大家查最多的已證實內容） |
| `/knowledge` | `pages/Knowledge.jsx` | 知識庫：關鍵字搜尋、依判定篩選 |
| `/bot` | `pages/Bot.jsx` | Threads 機器人頁，**目前是佔位頁** |
| `/oauth/callback` | `pages/OAuthCallback.jsx` | Meta 授權完成後的導回頁：只顯示授權碼讓負責人複製，不發任何網路請求 |
| `*` | `pages/NotFound.jsx` | 找不到頁面，**目前是佔位頁** |

手機（寬度 <768px）用頂欄 + 底部分頁列（查證／熱門／知識庫），桌機改用頂部導覽並多一個「機器人」項目。

首頁目前只開放文字與網址兩種輸入。圖片查證的後端端點已經完成，但上傳介面尚未開放，所以圖片分頁先隱藏。

---

## 📁 資料夾結構

```
code/frontend/
├── index.html               ← Vite 入口；首繪前的 inline script 先設定 data-theme，避免閃白
├── vercel.json              ← Vercel：/api/* 代理到 Render + SPA fallback
├── vite.config.js           ← dev server 的 /api 代理（→ localhost:8000）
├── eslint.config.js / postcss.config.js / tailwind.config.js
├── public/                  ← 原樣提供的靜態檔（隱私頁、og.png、demo 影片）
└── src/
    ├── main.jsx             ← React 入口（createBrowserRouter）
    ├── routes.jsx           ← 路由表
    ├── i18n.js              ← 繁中文案表與 t()
    ├── index.css            ← 設計 token、深淺色主題、字級
    ├── pages/
    │   ├── Home.jsx、Result.jsx、Trending.jsx、Knowledge.jsx、Bot.jsx、OAuthCallback.jsx、NotFound.jsx
    │   ├── home/            ← 範例 chips、最近查證、Threads 說明卡、useSubmitAnalysis（送出查證）
    │   ├── result/          ← 結果頁各狀態的元件、useResultPolling、useReanalyze、resultState、buildThreadsIntent
    │   ├── trending/        ← TrendingCard、trendingModel、sourceOrgName、copy.js、HotList、hotModel
    │   └── knowledge/       ← KnowledgeCard、SearchBar、useKnowledgeList、knowledgeModel、copy.js
    ├── components/          ← 共用元件：Banner、Button、Card、Chip、ConfirmDialog、Disclosure、DotRow、EmptyState、
    │   │                      Icon、InputCard、SegmentedTabs、Skeleton、SourceRow、ThemeToggle、Toast、VerdictBlock
    │   └── shell/           ← AppShell、TopBar、TabBar、DesktopNav、Footer、navItems、useBackendStatus、useIsDesktop
    ├── lib/
    │   ├── api.js           ← 所有後端呼叫的唯一入口
    │   ├── fixtures.js      ← fixture 模式的路徑對應
    │   ├── verdict.js       ← 燈號色調與列表用的判定 chip
    │   ├── history.js       ← 最近查證（只存在瀏覽器 localStorage）
    │   ├── validateInput.js ← 首頁輸入驗證
    │   ├── httpUrl.js、theme.js、useDocumentTitle.js
    │   └── *.test.js        ← 單元測試（與被測檔放在一起）
    └── dev/fixtures/        ← fixture 模式的 JSON 與說明（README.md）
```

舊的 `App.jsx`、`App.css`、`mockData.js` 已經不存在。更早的單檔查核儀封存在 repo 根目錄的 `legacy/`。

---

## 🔌 API 串接

[`src/lib/api.js`](src/lib/api.js) 是所有後端呼叫的唯一入口，元件不直接用 `fetch`。

| 函式 | 端點 |
|------|------|
| `analyzeText`、`analyzeUrl` | `POST /api/analyze/text`、`POST /api/analyze/url` |
| `analyzeImage` | `POST /api/analyze/image`（multipart；介面尚未開放） |
| `getResult`、`pollResult` | `GET /api/result/{id}` |
| `getTrending` | `GET /api/trending?limit=&risk_type=` |
| `getKnowledge`、`getKnowledgeStats` | `GET /api/knowledge?q=&risk_type=&limit=&offset=`、`GET /api/knowledge/stats` |
| `getKnowledgeHot` | `GET /api/knowledge/hot?limit=`（熱門頁「本站熱門查證」） |
| `getHealth` | `GET /api/health` |
| `getThreadsStatus`、`getThreadsReplies` | `GET /api/threads/status`、`GET /api/threads/replies` |

- **查證流程**：首頁送出 → 後端回 `result_id` → 導到 `/r/<id>` → 結果頁每 2 秒讀一次 `/api/result/{id}`，最多 90 秒；逾時後顯示「稍後再打開這個連結」，可以重新開始輪詢。
- **逾時**：GET 15 秒、POST 30 秒、圖片 60 秒。
- **錯誤**：一律轉成 `ApiError`（`kind` 為 `network`／`timeout`／`http`，另有 `status`、`code`、`retryAfter`）。後端的錯誤格式是 `{detail, code}`；429 會帶 `Retry-After`。
- **連不上後端**：任何請求遇到網路錯誤、逾時或 5xx，`AppShell` 就在頂欄下方顯示「暫時連不上伺服器」橫幅，並每 10 秒自動重試 `/api/health`，成功後橫幅自己消失。雲端免費主機休眠後第一次喚醒約 1 分鐘，使用者不用手動重新整理。
- **最近查證**：只存在瀏覽器 `localStorage`（key `fcc_history_v1`，最多 50 筆），沒有伺服器副本，也沒有登入。

---

## 🚦 判定顯示規則

- 結果頁的燈號**只讀後端給的 `frame_type`／`frame_label`**，前端不從 `risk_type` 重算顏色。熱門牆、知識庫與最近查證的列表項目沒有 `frame_type`，才由 `lib/verdict.js` 的 `listVerdict` 依 `risk_type` 決定 chip。
- 「AI 暫時無法使用」只看 `ai_unavailable` 這個布林值。`api.js` 的 `FALLBACK_PREFIX`（「AI 分析暫時無法使用」）只用來相容舊資料；這段字樣與後端的 fallback 契約綁在一起，要改必須兩邊一起改。
- 結果沒有已證實的來源時（`verification_status` 為 `unverified`），紅燈與黃燈的結果頁都會顯示「尚無查核機構證實」提示（`pages/result/NoVerifiedSourceBanner.jsx`）；這個元件不會改變燈號本身。
- `sources` 只會有 Tier 1／2 的來源；Tier 3 在 `related_discussions`，以「相關討論」另外呈現。

### 結果頁的載入進度只會往前

`pages/result/ResultLoading.jsx` 的三步指示「檢查快取 → 讀取內容 → AI 判讀」是依時間前進的動畫：每 2 秒前進一步，**只往前、不回頭**，到最後一步「AI 判讀」就停住，直到結果回來（真正的分析時間大多花在這一步）。系統設定了「減少動態效果」時停在第一步。邏輯在 `pages/result/resultState.js` 的 `loadingStep`，有單元測試。

---

## 🎨 設計 token 與主題

[`src/index.css`](src/index.css) 定義全部的設計 token（CSS 變數），再用 Tailwind 4 的 `@theme inline` 對應成工具類（`bg-surface`、`text-ink`、`border-line`、`text-red`…）。

- **淺色是預設**（`:root`），深色覆寫在 `:root[data-theme="dark"]`。
- 主題來源：`localStorage` 的 `fcc_theme` → 沒有時跟隨系統的 `prefers-color-scheme`。`index.html` 的 inline script 在首繪前設定 `data-theme`；切換邏輯在 `lib/theme.js`，按鈕是 `components/ThemeToggle.jsx`。
- 黑白為底，強調色只有 `--c-accent` 一個 token。**紅黃綠只用在判定**（燈號區塊、判定 chip、燈號點）。

| 類別 | token |
|------|-------|
| 底色與文字 | `--c-bg`、`--c-surface`、`--c-ink`、`--c-ink-2`、`--c-ink-3`、`--c-ink-inverse`、`--c-line` |
| 強調色 | `--c-accent`、`--c-accent-soft` |
| 判定色 | `--c-red`、`--c-yellow`、`--c-green`、`--c-grey`，各有對應的 `-soft` 底色 |
| 形狀與陰影 | `--radius-card`、`--radius-btn`、`--radius-chip`、`--shadow-card`、`--c-backdrop` |
| 字體 | `--font-stack`；字級類別 `.t-h1`、`.t-h2`、`.t-body`、`.t-sub`、`.t-chip`、`.t-caption`（最小 13px） |

兩個主題的文字對比由 `src/lib/contrast.test.js` 讀 `index.css` 計算並驗證，改 token 之後要跑單元測試。

---

## 🈶 文案表（i18n）

使用者看得到的文字都集中在 [`src/i18n.js`](src/i18n.js)，元件裡不寫死中文。

- `STRINGS`：照規格書 §8.7 逐字的文案；`EXTRA`：規格沒有定義、但畫面需要的字串。
- `t(key, params)` 取字串並置換佔位符：`{name}` 由參數帶入，`{BRAND}`、`{BOT_HANDLE}` 自動帶入；`{summary≤80}` 這種寫法表示超過 80 字時截成 79 字再補「…」。開發模式下找不到 key 會在 console 警告。
- `src/pages/knowledge/copy.js` 與 `src/pages/trending/copy.js` 還放著少數幾個頁面專用字串（檔內標了 TODO，之後要搬進 `i18n.js` 的 `EXTRA`）。

---

## 🧪 Fixture 模式（不啟動後端也能看每個畫面狀態）

`VITE_FIXTURES=1` 時，`api.js` 的 `request()` **不發任何 fetch**，改讀 `src/dev/fixtures/*.json`。用途是重現每個畫面狀態（截圖、對照 mockup），不必啟動後端，也不花 AI 額度。只在 dev server 生效，`npm run build` 的產物不含任何 fixture。

PowerShell：

```powershell
cd code\frontend
$env:VITE_FIXTURES="1"; npm run dev
```

macOS／Linux：

```bash
VITE_FIXTURES=1 npm run dev
```

用瀏覽器網址列的 `?fixture=` 參數切換狀態，例如：

| 網址 | 讀到的 fixture |
|------|----------------|
| `http://localhost:5173/r/fx-pending` | `result_fx-pending.json`（載入中） |
| `http://localhost:5173/r/fx-red-misinfo` | `result_fx-red-misinfo.json` |
| `http://localhost:5173/r/fx-green-cache-vector` | `result_fx-green-cache-vector.json`（向量快取命中） |
| `http://localhost:5173/r/fx-ai-unavailable` | `result_fx-ai-unavailable.json` |
| `http://localhost:5173/trending?fixture=empty` | `trending_empty.json` |
| `http://localhost:5173/knowledge?fixture=empty` | `knowledge_empty.json` |
| `http://localhost:5173/trending?tab=hot&fixture=empty` | `knowledge_hot_empty.json` |
| `http://localhost:5173/?fixture=analyze_rate_limited` | 送出查證時回 `analyze_rate_limited.json`（429） |

- fixture JSON 的頂層可以帶 `_status`（HTTP 狀態碼）與 `_headers`（例如 `Retry-After`）來模擬錯誤，走與真實回應相同的錯誤處理。
- 對應規則裡有、但檔案不存在的 fixture 會回 404。
- 完整的路徑對應規則與約定見 [`src/dev/fixtures/README.md`](src/dev/fixtures/README.md)；規則本身在 `src/lib/fixtures.js`，改規則時兩邊一起改。

---

## ✅ 測試、lint、build

```powershell
cd code\frontend
npm run test:unit   # 單元測試：Node 內建 test runner（node --test），390 個，離線
npm run lint        # ESLint 9（設定在 eslint.config.js）
npm run build       # 產出 dist/
npm run preview     # 在本機預覽 build 結果
```

- 單元測試檔是 `src/**/*.test.js`，與被測的檔案放在一起，涵蓋 `api`、`fixtures`、`verdict`、`history`、`validateInput`、`httpUrl`、`theme`、對比度、`i18n`、送出查證、結果頁狀態、Threads 分享連結、熱門牆與知識庫的資料模型、後端狀態橫幅。純邏輯抽成不含 JSX 的模組，`node --test` 才能直接 import。
- GitHub Actions（`.github/workflows/ci.yml` 的 `frontend` job）在每次 push／PR 到 `main` 時用 Node 20 跑 `npm ci` → `npm run build` → `npm run test:unit`。
- 如果專案資料夾搬過位置後 `npm run lint` 或 `npm run build` 出現 `Cannot find module`，代表 `node_modules` 不完整，重新執行 `npm ci` 即可。

---

## 🐳 Docker（選用，不是正式部署路徑）

`Dockerfile` 與 `nginx.conf`（nginx 提供靜態檔並把 `/api` 反向代理到名為 `backend` 的容器）還留在這個目錄，給想自架的人參考。正式環境用的是 Vercel。
