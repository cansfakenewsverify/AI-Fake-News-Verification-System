# AI-Driven Fake News and Scam Verification System

[![CI](https://github.com/cansfakenewsverify/AI-Fake-News-Verification-System/actions/workflows/ci.yml/badge.svg)](https://github.com/cansfakenewsverify/AI-Fake-News-Verification-System/actions/workflows/ci.yml)
[![Live site](https://img.shields.io/badge/Live-fakenewsverify.vercel.app-000000?logo=vercel&logoColor=white)](https://fakenewsverify.vercel.app)
![Python 3.12](https://img.shields.io/badge/Python-3.12-blue)
![React 19](https://img.shields.io/badge/Frontend-React%2019-61DAFB?logo=react&logoColor=white)
![FastAPI](https://img.shields.io/badge/Backend-FastAPI-009688?logo=fastapi&logoColor=white)
![Supabase Postgres + pgvector](https://img.shields.io/badge/Storage-Supabase%20Postgres%20%2B%20pgvector-3FCF8E?logo=supabase&logoColor=white)
![Tests](https://img.shields.io/badge/Tests-pytest%20700%20%7C%20frontend%20380-success)
![Eval](https://img.shields.io/badge/Eval%20150%20items-accuracy%20100%25%20%2F%20FN%3D0-success)

**全民查證公社**：AI 假訊息與詐騙查證系統（學生專題）。貼上一段文字或一個網址，系統判定它是詐騙、假訊息、尚待確認，還是查無異常，並附上查核機構的來源。

> **系統已經上線，開網站就能用，不需要安裝或啟動任何東西。**
> `start.bat`／`start.sh` 只有改程式時才需要，說明在後面的[本機開發](#local-dev)。

---

## 🌐 線上網站（直接使用）

### 👉 https://fakenewsverify.vercel.app

| 你可以做什麼 | 位置 |
|--------------|------|
| 貼上文字或網址，取得紅／黃／綠判定、摘要、白話說明與查核來源 | 首頁 [`/`](https://fakenewsverify.vercel.app/) |
| 每一筆查證都有自己的結果頁，可以複製連結或分享到 Threads | `/r/<id>` |
| 熱門牆：最近的查核結果（來源為 MyGoPen、台灣事實查核中心、Cofacts） | [`/trending`](https://fakenewsverify.vercel.app/trending) |
| 本站熱門查證：最近 7 天大家查最多的已證實內容，越近的查證權重越高 | [`/trending?tab=hot`](https://fakenewsverify.vercel.app/trending?tab=hot) |
| 知識庫：用關鍵字搜尋、依判定篩選已證實的查證內容 | [`/knowledge`](https://fakenewsverify.vercel.app/knowledge) |

**簡報影片**（4 分 38 秒，旁白＋音效＋字幕，整套功能與操作的完整導覽，瀏覽器直接播放）：
https://fakenewsverify.vercel.app/demo/presentation_v1.mp4

**舊版 demo 影片**（2 分 37 秒）：
https://fakenewsverify.vercel.app/demo/demo_v0.4.0.mp4

使用前先知道這幾件事：

- **第一次打開可能要等約 1 分鐘。** 後端在 Render 免費方案上，15 分鐘沒有流量就會休眠。休眠時頁面會顯示「暫時連不上伺服器」，並每 10 秒自動重試；後端醒來後內容會自己載入，不用手動重新整理。
- **查證時間**：沒查過的內容由 AI 判定，實測約 9–27 秒；查過的內容（包含換句話說的同一則謠言）直接命中快取，實測約 3 秒，也不佔每日 AI 額度。
- **額度**：全站每天最多 300 次 AI 判定（台灣時間 00:00 歸零）；每個 IP 每分鐘 30 次、每小時 200 次。額度用完後，查過的內容仍可查到結果。
- **輸入方式**：網頁目前開放文字與網址。圖片查證的後端端點已完成，上傳介面尚未開放。
- **不需要登入**。「最近查證」紀錄只存在你自己的瀏覽器，不會上傳。隱私政策：https://fakenewsverify.vercel.app/privacy.html

燈號的意思（由後端 `app/utils/verdict.py` 統一決定，網頁與 Threads 回覆共用）：

| 燈號 | 標籤 | 什麼時候出現 |
|------|------|--------------|
| 🔴 紅 | 詐騙警告／假訊息／風險訊息 | AI 判定有風險 |
| 🟡 黃 | 尚無查核機構證實 | AI 判定安全，但找不到已有判定的查核來源 |
| 🟡 黃 | 尚待確認／無法查證 | 信心不足；或網址讀不到內容、平台不支援 |
| 🟢 綠 | 查無異常 | AI 判定安全、有已證實的來源，且信心 ≥ 0.7 |
| ⚪ 灰 | AI 暫時無法使用 | 呼叫 AI 閘道失敗（這種結果不會寫進快取，也不提供分享） |

紅燈或黃燈的結果如果沒有已證實的來源，結果頁會另外顯示「尚無查核機構證實」的提示。

---

## 🏗️ 系統架構

```
瀏覽器 → https://fakenewsverify.vercel.app（Vercel：React 靜態檔）
           └─ /api/* 由 code/frontend/vercel.json rewrite 同源代理 → https://fakenewsverify-api.onrender.com（Render 免費 web service，FastAPI，render.yaml）
                                                                   ├─ Supabase Postgres 17 + pgvector（東京；知識庫／任務／回饋／熱門／每日 AI 計數）
                                                                   └─ 學校 CGU AIR 閘道（AI gpt-5.4-mini、embedding text-embedding-3-small 1536 維）
GitHub Actions keepalive（每 10 分鐘）→ Render /health + /api/knowledge/stats
```

- 金鑰只存在兩個地方：負責人本機的 `code/backend/.env` 與 Render 後台。這個 repo 是公開的，`render.yaml` 只有變數名稱，沒有值。
- 雲端刻意關閉三樣東西：自動抓新聞排程、AI 的 web_search、Threads 機器人（設定見 `render.yaml`）。
- Render 出問題時的退路是「負責人電腦 + cloudflared tunnel」，見 [`docs/rebuild/runbook_tunnel.md`](docs/rebuild/runbook_tunnel.md)。

---

## ✨ 功能

| 功能 | 說明 |
|------|------|
| **文字／網址查證** | 文字輸入只分析使用者原文：不爬網頁、不送任何搜尋引擎。網址輸入由後端抓取內文後分析；Facebook、Instagram、YouTube、TikTok 這類封閉或影音平台不支援，直接回「無法查證」，不呼叫 AI。 |
| **三層快取** | L0 相同網址 → L1 相同內容（SHA-256）→ L2 語意相似（embedding 向量，門檻 0.75，只比對已證實的資料列）→ L3 AI。換句話說的同一則謠言也能命中，不再呼叫 AI。 |
| **來源品質規則** | 只有「已經有判定」的來源才算查核來源。Tier 1：查核機構與官方網域（TFC、MyGoPen、`gov.tw`、WHO、CDC；Cofacts 文章必須已有 RUMOR／NOT_RUMOR 回覆）。Tier 2：媒體的查核報導。其餘（Tier 3）只列在「相關討論」，不當作證據。 |
| **沒有證據就不給綠燈** | 沒有已證實來源的結果顯示「尚無查核機構證實」，不會出現綠燈。 |
| **可分享的結果頁** | 每筆查證的網址是 `/r/<id>`，任何人打開都看得到同一份結果；可複製連結或分享到 Threads。 |
| **熱門牆與知識庫** | 熱門牆來自 MyGoPen、TFC 的 RSS 與 Cofacts（只取已有 RUMOR 判定的文章）。知識庫只顯示已證實的資料列。「本站熱門查證」依查證紀錄排序（半衰期 3 小時的時間衰減、7 天視窗），同樣只列已證實內容。三者都不呼叫 AI。 |
| **查核結果回補** | 一字不差的重複查詢若命中「尚無查核機構證實」的舊資料，而查核機構之後的結論已寫進知識庫且語意對得上，就改回查核結論；只有查核機構或人工確認的結論能取代舊結果。 |
| **防止 AI 編造連結** | 系統 prompt 規定找不到來源就回空陣列；後端再逐一檢查 AI 回傳的來源網址，失效的剔除。 |
| **上線護欄** | 每日 AI 次數上限、每 IP 限速、請求大小上限（JSON 1 MB／圖片 10 MB）、SSRF 防護（拒絕內部與保留位址，每次轉址重新檢查）、管理端點需要 `X-Admin-Token`。 |
| **AI 失效時的降級** | AI 閘道失敗時結果頁顯示灰色「AI 暫時無法使用」，失敗結果不寫進快取；熱門牆與知識庫不受影響。 |
| **圖片查證（後端）** | 端點已完成（以檔頭判斷 PNG／JPG／WEBP、10 MB 上限），網頁上傳介面尚未開放。 |
| **Threads 查核機器人（延伸功能）** | 在 Threads 上 @機器人，自動回覆判定與來源。目前 demo 用模擬模式（`THREADS_MODE=sim`）；實機串接需要 Meta App Review，排在進度報告之後。只在負責人電腦上跑，雲端關閉。 |

---

## 🛠️ 技術堆疊

**後端**：Python 3.12、FastAPI + Uvicorn、SQLAlchemy + psycopg 3、pandas + pyarrow、numpy、APScheduler（排程，預設關閉）、trafilatura + BeautifulSoup4 + requests（網址內文擷取）

**AI**：學校 CGU AIR 閘道（OpenAI 相容 Responses API），模型 `gpt-5.4-mini`；embedding `text-embedding-3-small`（1536 維）

**資料**：雲端用 Supabase Postgres 17 + pgvector；本機開發預設用 SQLite + Parquet（`STORAGE_BACKEND` 切換，兩邊介面相同）

**前端**：React 19 + Vite 8.3.0 + Tailwind CSS 4 + React Router 7；單元測試用 Node 內建 test runner；ESLint 9

**部署與自動化**：Vercel（前端）、Render（後端）、Supabase（資料庫）、GitHub Actions（`ci.yml` 測試、`keepalive.yml` 保持後端與資料庫清醒）

---

## 📁 專案結構

```
AI-Fake-News-Verification-System/
├── README.md                    ← 本檔
├── CLAUDE.md                    ← 專案完整技術地圖（給 AI 助理與接手的人）
├── render.yaml                  ← Render Blueprint：後端雲端部署設定（只有變數名稱，沒有金鑰）
├── start.bat / start.sh         ← 本機開發用一鍵啟動（後端 + React dev server）
├── start-debug.bat              ← 本機啟動失敗時的逐步診斷
│
├── code/
│   ├── backend/                 ← FastAPI 後端（Render 的 rootDir）→ 見 code/backend/README.md
│   │   ├── app/                 ← api / services / workers / models / utils、config.py、database_sql.py、main.py
│   │   ├── tests/               ← pytest
│   │   ├── scripts/             ← 評測、批次查證、資料清洗、搬資料到 Supabase、Threads 工具
│   │   ├── data/                ← 知識庫種子、評測資料與結果、SCHEMA.md
│   │   ├── requirements.txt     ← 本機與 CI 用（含評測與開發工具）
│   │   ├── requirements-prod.txt← Render 用（只有執行期套件）
│   │   └── .env.example         ← 環境變數範本
│   │
│   └── frontend/                ← React 前端（Vercel 的 Root Directory）→ 見 code/frontend/README.md
│       ├── src/                 ← pages / components / lib / dev/fixtures、i18n.js、index.css、routes.jsx
│       ├── public/              ← privacy.html、data-deletion.html、deauthorize.html、og.png、demo/（簡報影片與 demo 影片）
│       └── vercel.json          ← /api/* 代理到 Render + SPA fallback
│
├── .github/workflows/           ← ci.yml、keepalive.yml、cgu-reachability.yml
├── docs/
│   ├── rebuild/                 ← 2026-09 重做文件：00_consensus、01_spec、02_mockup_brief + mockup/、03_tickets、
│   │                              owner_decisions_day0、runbook_cloud_deploy、runbook_tunnel
│   ├── test/                    ← 測試計畫書 TP-FNV-2026-01.md、results/、screens/、ui_checklist.csv
│   └── demo/                    ← 簡報影片規格、分鏡、素材紀錄、字幕
├── presentations/               ← 2026-09_進度報告/ 與前兩次報告的簡報
├── video/hf-presentation/       ← 5 分鐘簡報影片原始碼（presentation_v1.1）
├── video/hf-demo/               ← 舊版 demo 影片原始碼（v0.4.0）
├── assets/                      ← PlantUML 圖、confusion_matrix.png、期末專題文件/（OOSE 文件）
└── legacy/                      ← 已封存、不再維護的舊版單檔查核儀
```

---

## 📊 評測

150 筆人工標註資料集 `code/backend/data/eval_set.csv`（SCAM／MISINFO／SAFE 各 50 筆，含刻意設計的「看起來像詐騙的合法官方訊息」）。

| 指標 | `gpt-5.4-mini`（2026-09-16，現行） | `gpt-5-mini`（2026-06，前一版） |
|------|-----------------------------------|--------------------------------|
| Accuracy | **100%** | 96.0% |
| Macro-F1 | 1.000 | 0.960 |
| 偽陰性 FN（漏判風險） | **0** | 0 |
| 偽陽性 FP（誤報） | 0 | 5 |

- 現行結果在 `code/backend/data/eval_report.csv`、`eval_binary.csv`；前一版封存在 `code/backend/data/eval_archive_gpt5mini_2026-06/`；混淆矩陣圖在 `assets/confusion_matrix.png`。
- 150 筆全對，代表這組題目對現行模型已經太簡單，數字只說明在這份資料集上的表現；下一步是擴充題庫再比。
- 重跑方式見 [`code/backend/README.md`](code/backend/README.md)。

---

## 🧪 測試

| 項目 | 數量 | 怎麼跑 |
|------|------|--------|
| 後端 pytest | 732 個通過；另有 29 個 Postgres 契約測試預設略過（需要 `RUN_PG_TESTS=1` 與 `SUPABASE_DB_URL`） | 在 `code\backend` 執行 `.\venv\Scripts\python -m pytest tests -q` |
| 前端單元測試 | 394 個通過 | 在 `code\frontend` 執行 `npm run test:unit` |

- 兩邊的測試都離線執行，不呼叫 AI、不花額度。
- CI（`.github/workflows/ci.yml`）在每次 push／PR 到 `main` 時跑兩個 job：`test`（後端 pytest）與 `frontend`（`npm ci` → `npm run build` → `npm run test:unit`）。
- 測試計畫書：[`docs/test/TP-FNV-2026-01.md`](docs/test/TP-FNV-2026-01.md) v1.5，分操作、功能、介面、績效、品質五類共 46 項。2026-09-16 這一輪指定執行 34 項：通過 24、通過（待補驗）2、未通過 3、未執行 4；明細與缺陷清單在計畫書第 6 節。

---

## 🔌 公開 API

Base URL：`https://fakenewsverify.vercel.app/api/...`（由 Vercel 同源代理到 Render）。
Swagger UI：https://fakenewsverify-api.onrender.com/docs

> 這是學生專題的免費額度：全站每天最多 300 次 AI 判定，每個 IP 每分鐘 30 次、每小時 200 次，超過回 HTTP 429。請不要用程式大量呼叫。

| 方法 | 路徑 | 說明 |
|------|------|------|
| POST | `/api/analyze/text`、`/api/analyze/url` | 非同步查證：回 `task_id`／`result_id`，再讀 `/api/result/{id}` |
| POST | `/api/analyze/sync` | 同步查證（文字或網址），一次回傳結果 |
| GET | `/api/result/{id}` | 結果頁資料（`status` 為 `completed` 或 `failed` 時停止輪詢） |
| GET | `/api/trending?limit=&risk_type=` | 熱門牆 |
| GET | `/api/knowledge?q=&risk_type=&limit=&offset=`、`/api/knowledge/stats` | 知識庫與統計 |
| GET | `/api/knowledge/hot?limit=` | 本站熱門查證（最近 7 天、只列已證實內容） |
| GET | `/api/health` | 健康檢查（資料層、AI 是否可用、今日 AI 用量） |

完整路由（圖片、回饋、Threads、管理端點）見 [`code/backend/README.md`](code/backend/README.md)。

macOS／Linux：

```bash
curl --max-time 120 -X POST https://fakenewsverify.vercel.app/api/analyze/sync \
  -H "Content-Type: application/json" \
  -d '{"content":"網傳吃香蕉配優格會中毒"}'

curl "https://fakenewsverify.vercel.app/api/trending?limit=10"
curl -G "https://fakenewsverify.vercel.app/api/knowledge" --data-urlencode "q=詐騙" --data-urlencode "limit=20"
curl "https://fakenewsverify.vercel.app/api/health"
```

Windows PowerShell 5.1（回應是 UTF-8，要自己解碼，否則中文會變亂碼）：

```powershell
# GET
$resp = Invoke-WebRequest -UseBasicParsing -Uri "https://fakenewsverify.vercel.app/api/trending?limit=10"
[System.Text.Encoding]::UTF8.GetString($resp.RawContentStream.ToArray()) | ConvertFrom-Json

# POST（同步查證）
$json  = @{ content = "網傳吃香蕉配優格會中毒" } | ConvertTo-Json
$bytes = [System.Text.Encoding]::UTF8.GetBytes($json)
$resp  = Invoke-WebRequest -UseBasicParsing -Method Post -Uri "https://fakenewsverify.vercel.app/api/analyze/sync" -ContentType "application/json; charset=utf-8" -Body $bytes
[System.Text.Encoding]::UTF8.GetString($resp.RawContentStream.ToArray()) | ConvertFrom-Json
```

回應的主要欄位：`frame_type`／`frame_label`（燈號與標籤）、`risk_type`、`summary`、`explanation`、`sources`（只含 Tier 1／2，每項帶 `tier`）、`related_discussions`（Tier 3）、`verification_status`、`cached`／`cache_layer`（`url`／`hash`／`vector`）、`result_id`、`ai_unavailable`。

---

<a name="local-dev"></a>

## 💻 本機開發（不是使用系統的必要步驟）

只有要改程式、跑測試或跑評測時才需要。需要 Python 3.12（CI 與雲端用的版本）與 Node.js 20.19 以上（Vite 8.3.0 的要求）。

**Windows**：雙擊 `start.bat`，或在 PowerShell 執行：

```powershell
.\start.bat
```

**macOS／Linux**：

```bash
chmod +x start.sh
./start.sh
```

腳本會依序：檢查 Python 與 Node → 第一次執行時把 `code/backend/.env.example` 複製成 `.env` → 確保 `ADMIN_TOKEN` 有值（自動產生亂數，不會印出來）→ 建立 `code/backend/venv` 並安裝 `requirements.txt` → 第一次執行時安裝前端 npm 套件 → 開兩個視窗（後端、React dev server）→ 打開瀏覽器。

| 服務 | 本機網址 |
|------|----------|
| React 主介面（Vite dev server，`/api` 代理到 8000） | http://localhost:5173 |
| 後端 API | http://localhost:8000 |
| Swagger UI | http://localhost:8000/docs |

- **第一次啟動前**：在 `code/backend/.env` 填入 `CGU_API_KEY` 與 `EMBED_API_KEY`（兩者可以是同一把 CGU 金鑰；`.env.example` 已設好 `AI_PROVIDER=cgu`）。沒有金鑰時，查證會顯示「AI 暫時無法使用」，熱門牆與知識庫仍可瀏覽。
- **本機預設的資料層是 SQLite + Parquet**（`STORAGE_BACKEND=local`）：`code/backend/data/factcheck.db` 與 `data/*.parquet`，不需要任何資料庫服務。repo 內附的 `knowledge_base.parquet` 是種子資料（218 筆，其中 128 筆已證實）。
- 本機的 API 範例把 base URL 換成 `http://localhost:8000` 即可，例如 `http://localhost:8000/api/health`。
- 分開啟動後端或前端、跑腳本的指令，見 [`code/backend/README.md`](code/backend/README.md) 與 [`code/frontend/README.md`](code/frontend/README.md)。
- 如果整個專案資料夾搬過位置，`code\backend\venv` 會失效（裡面記著舊路徑）。刪掉 `code\backend\venv` 再跑一次 `start.bat` 就會重建。前端如果出現 `Cannot find module`，到 `code\frontend` 執行 `npm ci` 重裝套件。

---

## ⚙️ 環境變數（`code/backend/.env`）

本機寫在 `code/backend/.env`（已 gitignore）；雲端的非機密值寫在 `render.yaml`，機密值只在 Render 後台輸入。下表只列最常用的，完整清單見 [`code/backend/README.md`](code/backend/README.md) 與 [`code/backend/.env.example`](code/backend/.env.example)。

| 變數 | 程式預設 | 說明 |
|------|----------|------|
| `AI_PROVIDER` | `openai` | 主要 AI provider。目前只使用 `cgu`（`.env.example` 與雲端都設 `cgu`）；只有填了金鑰的 provider 會進入備援鏈 |
| `CGU_API_KEY` | 空（機密） | CGU AIR 閘道金鑰 |
| `CGU_MODEL` | `gpt-5.4-mini` | 分析用模型 |
| `EMBED_API_KEY` | 空（機密） | embedding 金鑰；空的時候退用 `CGU_API_KEY`，兩者都沒有則向量層自動停用 |
| `SIMILARITY_THRESHOLD` | `0.75` | 向量快取命中門檻（實測校準值，換 embedding 模型要重新量測） |
| `USE_WEB_SEARCH` | `true` | 分析時是否帶 web_search；每次呼叫貴 3–7 倍，雲端設 `false` |
| `STORAGE_BACKEND` | `local` | `local`＝SQLite + Parquet；`supabase`＝Supabase Postgres（還要有 `SUPABASE_DB_URL` 才會生效） |
| `SUPABASE_DB_URL` | 空（機密） | Supabase 的 Session pooler 連線字串 |
| `DAILY_AI_CALL_CAP` | `300` | 每日 AI 呼叫次數上限（台灣時間 00:00 歸零；`0`＝不限制） |
| `RATE_LIMIT_PER_MINUTE` | `30` | 每個 IP 每分鐘的查證請求上限（`0`＝關閉） |
| `RATE_LIMIT_PER_HOUR` | `200` | 每個 IP 每小時的查證請求上限（`0`＝關閉） |
| `THREADS_MODE` | 未設定（等同 `off`） | Threads 機器人：`off`／`live`／`sim`（模擬模式，不打 Threads API） |
| `PUBLIC_BASE_URL` | 空 | 對外網址，用在分享連結與 Threads 回覆 |
| `ADMIN_TOKEN` | 空（機密） | 管理端點的 token；空的時候管理功能停用 |
| `ENABLE_SCHEDULER` | `false` | 背景自動抓熱門新聞（會持續花 AI 額度） |
| `DEMO_MODE` | `false` | `true` 時查證端點回傳假資料，不呼叫 AI |

`MYAI_API_KEY`、`OPENAI_*`、`CLAUDE_*` 屬於已停用的舊 provider（myai168）：程式碼保留，沒有金鑰就不會啟用。

---

## ☁️ 部署

正式環境是 **Vercel + Render + Supabase**：

- **前端**：Vercel，Root Directory 設為 `code/frontend`；`vercel.json` 把 `/api/*` 代理到 Render，其餘路徑回 `index.html`。
- **後端**：Render 免費 web service，設定全部在 [`render.yaml`](render.yaml)（`rootDir: code/backend`、`pip install -r requirements-prod.txt`、健康檢查 `/health`）。`main` 分支有動到 `code/backend` 的 commit 會自動部署。
- **資料庫**：Supabase Postgres + pgvector，後端以 `STORAGE_BACKEND=supabase` 連線。本機資料用 `scripts/migrate_to_supabase.py` 搬上去（2026-09-19 搬移時：知識庫 218 筆、熱門 24 筆）。
- **保持清醒**：`keepalive.yml` 每 10 分鐘打一次 `/health` 與 `/api/knowledge/stats`（Render 免費方案會休眠；Supabase 免費專案 7 天沒活動會被暫停）。

完整步驟、免費方案的限制與退回本機的方法：[`docs/rebuild/runbook_cloud_deploy.md`](docs/rebuild/runbook_cloud_deploy.md)。

（選用）repo 裡還留著自架用的 `code/backend/Dockerfile`、`code/backend/docker-compose.yml`（只有後端容器、本機檔案儲存）與 `code/frontend/Dockerfile` + `nginx.conf`，但這不是正式部署路徑；compose 檔的環境變數清單還是舊的，使用前要自己補上新變數。

---

## 📚 文件

| 文件 | 內容 |
|------|------|
| [`presentations/2026-09_進度報告/`](presentations/2026-09_進度報告/) | 2026-09 進度報告的全部資料：投影片、報告內容說明、demo 影片網址、測試計畫書 PDF、分工表 |
| [`docs/rebuild/runbook_cloud_deploy.md`](docs/rebuild/runbook_cloud_deploy.md) | 上雲操作手冊（Render + Supabase + Vercel） |
| [`docs/test/TP-FNV-2026-01.md`](docs/test/TP-FNV-2026-01.md) | 測試計畫書 v1.5：2026-09-16 第一輪實測與 2026-09-19～20 第二輪重測 |
| [`CLAUDE.md`](CLAUDE.md) | 專案完整技術地圖：AI 引擎、三層快取、標記規則、雲端部署、待辦 |
| [`docs/rebuild/`](docs/rebuild/) | 2026-09 重做的共識、規格（`01_spec.md` v1.3）、mockup、實作票 |
| [`code/backend/README.md`](code/backend/README.md)、[`code/frontend/README.md`](code/frontend/README.md) | 後端與前端各自的說明 |

---

## 👥 團隊

| 姓名 | 角色 |
|------|------|
| **廖晢勛**（負責人） | 系統架構與實作；測試負責人／操作者 |
| **石岱勳** | 介面測試 |
| **姚睿** | 績效與品質數據 |
| **張宇宏** | 文件與審查 |
| **廖育翔** | 影片與簡報 |

分工細節見 [`presentations/2026-09_進度報告/05_分工表.md`](presentations/2026-09_進度報告/05_分工表.md)。

## 📄 License

學術用途；引用請註明來源。
