# Backend（FastAPI）

「全民查證公社」的後端：查證 API、三層快取、來源分級與紅黃綠判定、熱門牆與知識庫、上線護欄，以及 Threads 查核機器人（延伸功能）。

> 正式環境的後端跑在雲端：**https://fakenewsverify-api.onrender.com**（使用者經由 https://fakenewsverify.vercel.app 的 `/api/*` 代理連到它）。
> 本機啟動只有開發、跑測試、跑評測與資料腳本時才需要。

---

## ☁️ 雲端上跑的是什麼

```
https://fakenewsverify.vercel.app/api/*  ──(code/frontend/vercel.json rewrite)──►  Render web service（本目錄）
                                                                                   ├─ Supabase Postgres 17 + pgvector
                                                                                   └─ 學校 CGU AIR 閘道（gpt-5.4-mini、text-embedding-3-small）
```

| 項目 | 內容 |
|------|------|
| 主機 | Render 免費 web service，設定全部在 repo 根目錄的 [`render.yaml`](../../render.yaml)（Blueprint） |
| 範圍 | `rootDir: code/backend`：只有這個目錄會被部署，也只有這個目錄的 commit 會觸發自動部署（`main` 分支） |
| 安裝 | `pip install -r requirements-prod.txt`（只有執行期套件；評測與開發工具留在 `requirements.txt`） |
| 啟動 | `uvicorn app.main:app --host 0.0.0.0 --port $PORT`，Python 3.12.9，健康檢查 `/health` |
| 資料層 | `STORAGE_BACKEND=supabase` + `SUPABASE_DB_URL` → Supabase Postgres（知識庫、任務、回饋、熱門、每日 AI 計數） |
| AI | `AI_PROVIDER=cgu`（CGU AIR 閘道，`gpt-5.4-mini`） |
| 護欄 | `DAILY_AI_CALL_CAP=300`、`RATE_LIMIT_PER_MINUTE=30`、`RATE_LIMIT_PER_HOUR=200` |
| 刻意關閉 | `ENABLE_SCHEDULER=false`、`USE_WEB_SEARCH=false`、`THREADS_MODE=off` |
| 機密 | `CGU_API_KEY`、`EMBED_API_KEY`、`SUPABASE_DB_URL`、`ADMIN_TOKEN` 只在 Render 後台輸入（`render.yaml` 裡是 `sync: false`，沒有值） |

確認雲端真的接上資料庫：`/health`（或 `/api/health`）要回 `"storage_backend":"supabase"`。`SUPABASE_DB_URL` 沒設好時，後端會退回主機的暫時硬碟（看起來正常，但主機一休眠資料就消失）。同一個回應裡的 `daily_ai_calls` 是今天的 AI 用量。

新增 `app/` 會 import 的執行期套件時，`requirements.txt` 與 `requirements-prod.txt` **兩個檔都要加**；兩個檔都只能放 ASCII（Windows 上 pip 用 cp950 讀檔，中文註解會讓安裝失敗）。

上雲步驟、免費方案的限制（Render 15 分鐘沒流量休眠、Supabase 7 天沒活動暫停）與退回本機的方法：[`docs/rebuild/runbook_cloud_deploy.md`](../../docs/rebuild/runbook_cloud_deploy.md)。

仍然只在本機跑的東西：Threads 機器人（狀態檔是本機檔案）、自動抓新聞排程、評測與資料腳本、單元測試（本機與 GitHub Actions）。

---

## 💻 本機啟動

從專案根目錄一鍵啟動（後端 + React dev server）：`.\start.bat`（Windows）或 `./start.sh`（macOS／Linux）。

只啟動後端（PowerShell，在 `code\backend`）：

```powershell
# 第一次：建立虛擬環境、安裝套件、準備 .env
python -m venv venv
.\venv\Scripts\python -m pip install -r requirements.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }   # 已有 .env 就不會覆蓋；之後填入 CGU_API_KEY、EMBED_API_KEY（可以是同一把 CGU 金鑰）

# 啟動
.\venv\Scripts\python -m uvicorn app.main:app --reload --port 8000
```

- API：http://localhost:8000　Swagger UI：http://localhost:8000/docs　健康檢查：http://localhost:8000/health
- 本機預設 `STORAGE_BACKEND=local`：資料存在 `data/factcheck.db`（SQLite）與 `data/*.parquet`，不需要資料庫服務。
- 指令一律用 `python -m pip`／`python -m uvicorn`／`python -m pytest` 的形式。專案資料夾搬過位置後，`venv\Scripts\` 裡的 `pip.exe`、`uvicorn.exe` 會失效（記著舊路徑）；`venv` 整個壞掉時，刪掉 `venv` 資料夾重建即可。
- `_run_backend.bat` 是 `start.bat` 用來開後端視窗的輔助檔。

---

## 🗂️ 模組結構

```
app/
├── main.py                 ← FastAPI 入口：lifespan（資料庫初始化、護欄、排程）、CORS、請求大小 middleware、
│                             錯誤格式 {detail, code}、/health 與 /api/health
├── config.py               ← 所有設定（pydantic Settings，讀 .env，UTF-8，多餘變數忽略）
├── database_sql.py         ← SQL engine：本機 SQLite；STORAGE_BACKEND=supabase 時為 Supabase Postgres（psycopg 3）
│
├── api/                    ← REST 路由
│   ├── analyze.py          ← /api/analyze/{text,url,sync,image,task/{id},task/{id}/status}
│   ├── result.py           ← /api/result/{id}（結果頁 /r/<id> 的資料）
│   ├── trending.py         ← /api/trending、/api/trending/refresh（管理；?analyze=false 不呼叫判讀模型）
│   ├── knowledge.py        ← /api/knowledge、/api/knowledge/stats、/api/knowledge/hot（只回已證實的資料列）
│   ├── feedback.py         ← /api/feedback/tasks/{id}
│   ├── admin.py            ← /api/admin/tasks/{id}/override（管理：人工覆寫判定）
│   └── threads.py          ← /api/threads/{status,replies,poll}
│
├── services/
│   ├── ai_service.py       ← AI 分析（CGU AIR 閘道；myai168 OpenAI／Claude 程式碼保留但已停用）、圖片判讀、embedding、
│   │                         fallback 結果（summary 以「AI 分析暫時無法使用」開頭）
│   ├── ai_budget.py        ← 每日 AI 呼叫次數上限（計數存 SQL 表 ai_usage_daily，原子扣額度）
│   ├── crawler.py          ← 網址內文擷取（safe_url 抓取 + trafilatura／BeautifulSoup）；影音與封閉平台回 unsupported_platform
│   ├── cache_service.py    ← 內容 SHA-256 指紋
│   ├── vector_service.py   ← embedding 包裝
│   ├── store_factory.py    ← 取得 store 的唯一入口：依 settings.use_supabase 回傳本機版或 Postgres 版
│   ├── pandas_store.py     ← 本機知識庫（Parquet）：URL／hash／向量三層查詢、寫入門檻（verified、source_tier）
│   ├── task_store.py       ← 本機任務與結果頁資料（Parquet，上限 5,000 筆）
│   ├── audit_store.py      ← 本機管理者覆寫與使用者回饋（Parquet）
│   ├── pg_store.py         ← 雲端版三個 store（Postgres + pgvector），公開方法與本機版相同
│   ├── search_service.py   ← 熱門來源：MyGoPen RSS、TFC RSS、Cofacts API（只取已有 RUMOR 判定的文章）
│   ├── news_fetcher.py     ← 熱門新聞兩階段流程與標記規則（規則說明見根目錄 CLAUDE.md 第 9 節）
│   ├── hot_claims.py       ← 本站熱門查證排行（查證紀錄 × 半衰期 3 小時的時間衰減）
│   ├── threads_service.py  ← Threads Graph API 客戶端
│   ├── threads_sim.py      ← 模擬模式 FakeThreadsService（THREADS_MODE=sim，讀寫 data/threads_sim/）
│   ├── threads_state.py    ← 機器人狀態與回覆紀錄（原子寫入）
│   └── threads_reply.py    ← Threads 回覆模板與長度計數
│
├── workers/
│   ├── pandas_task_processor.py  ← 查證主流程：三層快取 → AI → 來源分級 → 寫知識庫 → 組結果
│   ├── task_queue.py             ← 任務派送（同一個行程內以 asyncio task 執行，不需要 Redis）
│   └── threads_bot.py            ← Threads 機器人輪詢（mentions → 查證 → 回覆）
│
├── models/
│   └── fact_check_record.py      ← 熱門記錄（唯一的 SQLAlchemy model）
│
└── utils/
    ├── verdict.py          ← 紅黃綠判定 frame_of（單一權威）與 is_fallback
    ├── source_tier.py      ← 來源分級 Tier 1／2／3
    ├── url_validator.py    ← 檢查 AI 回傳的來源網址是否存活，剔除失效連結
    ├── safe_url.py         ← SSRF 防護：所有由使用者或 AI 決定的網址都經過這裡
    ├── rate_limit.py       ← 每 IP 限速（滑動視窗）
    ├── body_limit.py       ← 請求大小上限（JSON 1 MB／圖片 10 MB）
    ├── admin_auth.py       ← 管理端點授權（X-Admin-Token）
    ├── share.py            ← 分享文案
    ├── labels.py           ← category 中文對照
    └── parquet_io.py       ← Parquet 原子寫入與重試讀取

tests/                      ← pytest（見「測試」）
scripts/                    ← 工具腳本（見「工具腳本」）
data/                       ← 知識庫種子、評測資料與結果、SCHEMA.md
static/swagger-custom.css   ← Swagger UI 樣式
```

async 端點裡不要直接呼叫 requests 或大型檔案 IO（會卡住整個 event loop）；照 `pandas_task_processor.py` 的做法包 `asyncio.to_thread`。

---

## ⚙️ 環境變數

本機寫在 `code/backend/.env`（複製 `.env.example`；已 gitignore，不要提交）。雲端的非機密值在 `render.yaml`，機密值只在 Render 後台。變數名稱刻意避開 `OPENAI_API_KEY`、`DATABASE_URL` 這類標準名稱，因為主機或系統的同名環境變數會蓋掉 `.env`。

**AI 與 embedding**

| 變數 | 程式預設 | 說明 |
|------|----------|------|
| `AI_PROVIDER` | `openai` | 主要 provider。目前只使用 `cgu`（`.env.example` 與雲端都設 `cgu`）；只有填了金鑰的 provider 會進入備援鏈，所以實際的鏈是 `['cgu']` |
| `CGU_API_KEY` | 空（機密） | CGU AIR 閘道金鑰 |
| `CGU_BASE_URL` | `https://air.cgu.edu.tw/cgullmapi/v1` | CGU AIR 閘道位址 |
| `CGU_MODEL` | `gpt-5.4-mini` | 分析用模型 |
| `CGU_REASONING_EFFORT` | `medium` | 推理強度 |
| `EMBED_RELAY_URL` | `https://air.cgu.edu.tw/cgullmapi/v1` | embedding 端點 |
| `EMBED_API_KEY` | 空（機密） | embedding 金鑰；空的時候退用 `CGU_API_KEY`，都沒有則向量層自動停用 |
| `EMBED_MODEL` | `text-embedding-3-small` | 1536 維（`VECTOR_DIMENSION=1536`） |
| `AI_TIMEOUT_SECONDS` | `60` | 一次分析（含備援鏈）的總時限 |
| `USE_WEB_SEARCH` | `true` | 分析時是否帶 web_search；每次呼叫貴 3–7 倍，雲端與高量任務設 `false` |
| `WEB_SEARCH_ALLOWED_DOMAINS` | 空 | web_search 限定網域（逗號分隔） |
| `SIMILARITY_THRESHOLD` | `0.75` | 向量快取命中門檻 |

**資料層**

| 變數 | 程式預設 | 說明 |
|------|----------|------|
| `STORAGE_BACKEND` | `local` | `local`＝SQLite + Parquet；`supabase`＝Supabase Postgres |
| `SUPABASE_DB_URL` | 空（機密） | Supabase 專案頁 Connect > Session pooler 的 URI。`STORAGE_BACKEND=supabase` 但這個值是空的時候，會退回本機檔案並在 log 留警告 |
| `SQLITE_URL` | `sqlite:///./data/factcheck.db` | 本機 SQLite 位置 |

**公開站台與上線護欄**

| 變數 | 程式預設 | 說明 |
|------|----------|------|
| `PUBLIC_BASE_URL` | 空 | 對外網址，用在分享連結與 Threads 回覆（雲端設為網站網址） |
| `ADMIN_TOKEN` | 空（機密） | 管理端點的 token；空的時候管理端點回 403。`start.bat`／`start.sh` 會自動補上亂數值 |
| `DAILY_AI_CALL_CAP` | `300` | 每日 AI 呼叫次數上限（台灣時間 00:00 歸零；`0`＝不限制） |
| `RATE_LIMIT_PER_MINUTE` | `30` | 每個 IP 每分鐘的查證請求上限（`0`＝關閉） |
| `RATE_LIMIT_PER_HOUR` | `200` | 每個 IP 每小時的查證請求上限（`0`＝關閉） |
| `CORS_ORIGINS` | `http://localhost:3000,http://localhost:5173` | 逗號分隔；正式環境的 API 走 Vercel 同源代理，通常不需要加 |
| `BRAND_NAME`、`CONTACT_EMAIL` | `全民查證公社`、空 | 品牌名稱、隱私頁聯絡信箱 |

**排程、模式與爬蟲**

| 變數 | 程式預設 | 說明 |
|------|----------|------|
| `ENABLE_SCHEDULER` | `false` | 背景自動抓熱門新聞（會持續花 AI 額度） |
| `TRENDING_FETCH_INTERVAL_HOURS` | `6` | 自動抓取間隔 |
| `DEMO_MODE` | `false` | `true` 時查證端點回傳假資料，不呼叫 AI |
| `CRAWLER_TIMEOUT`、`MAX_CONTENT_LENGTH` | `30`、`100000` | 網址抓取逾時（秒）、內文長度上限 |

**Threads 機器人（延伸功能）**

| 變數 | 程式預設 | 說明 |
|------|----------|------|
| `THREADS_MODE` | 未設定（等同 `off`） | `off`／`live`／`sim`。`sim` 是模擬模式，不打 Threads API |
| `THREADS_APP_ID`、`THREADS_APP_SECRET`（機密） | 空 | Meta App 的 Threads use case 設定頁上的值 |
| `THREADS_ACCESS_TOKEN`（機密）、`THREADS_USER_ID` | 空 | 長效 token（60 天）與機器人帳號 id |
| `THREADS_POLL_MINUTES` | `5` | 輪詢 mentions 的間隔 |
| `THREADS_MAX_REPLIES_PER_POLL`、`THREADS_MAX_REPLIES_PER_DAY` | `5`、`50` | 回覆上限 |
| `BOT_HANDLE`、`THREADS_BASE_URL` | `factcheck_tw_bot`、`https://graph.threads.net/v1.0` | 機器人帳號、Graph API 位址 |

**已停用（程式碼保留，沒有金鑰就不會啟用）**：`MYAI_API_KEY`、`OPENAI_RELAY_URL`、`OPENAI_MODEL`、`OPENAI_REASONING_EFFORT`、`CLAUDE_RELAY_URL`、`CLAUDE_MODEL`（myai168 的 OpenAI／Claude 中繼）；`ENABLE_THREADS_BOT`（舊鍵，已被 `THREADS_MODE` 取代）。

---

## 🗄️ 資料儲存

`app/services/store_factory.py` 依 `settings.use_supabase`（`STORAGE_BACKEND=supabase` 且有 `SUPABASE_DB_URL`）決定用哪一組，兩組的公開方法相同。

| 資料 | 本機（`local`） | 雲端（`supabase`） |
|------|-----------------|--------------------|
| 三層快取知識庫（含向量） | `data/knowledge_base.parquet`（repo 內附種子：218 筆，其中 128 筆已證實） | `knowledge_base` 表（`vector(1536)`） |
| 查證任務與結果頁資料 | `data/tasks.parquet`（上限 5,000 筆，只修剪最舊的已完成／失敗任務） | `tasks` 表 |
| 管理者覆寫、使用者回饋 | `data/admin_overrides.parquet`、`data/user_feedback.parquet` | `admin_overrides`、`user_feedback` 表 |
| 熱門記錄 | `data/factcheck.db`（SQLite）的 `fact_check_records` | `fact_check_records` 表 |
| 每日 AI 計數 | 同一個 SQLite 的 `ai_usage_daily` | `ai_usage_daily` 表 |

不進資料庫、只寫在主機硬碟上的檔案：`data/uploads/`（圖片暫存，分析完刪除）、`data/threads_state.json`、`data/threads_replies.jsonl`、`data/threads_token.json`、`data/threads_sim/`（Threads 機器人的狀態，這也是機器人只在本機跑的原因）。

- 欄位定義見 [`data/SCHEMA.md`](data/SCHEMA.md)。
- 本機檔案沒有跨行程鎖（單機單寫者）：跑批次腳本時，不要同時對後端做大量查證。
- 2026-09-16 資料清洗後：知識庫 218 筆（128 筆已證實）、熱門 24 筆全部已證實、Google News 項目歸零；2026-09-19 搬上 Supabase。審閱紀錄：[`docs/test/clean_sources_review.md`](../../docs/test/clean_sources_review.md)。

---

## ⚡ 三層快取

```
文字輸入 → L1 hash → L2 向量（以使用者原文比對）→ L3 AI（分析使用者原文）
網址輸入 → L0 網址 → L1 hash → 抓取內文 → L2 向量（以內文比對）→ L3 AI
                                                     └─ 結果寫回知識庫
```

- **文字輸入不爬網頁、不送任何搜尋引擎**，AI 分析的對象一律是使用者原文。
- L2 門檻 `SIMILARITY_THRESHOLD=0.75` 是實測校準值（text-embedding-3-small、繁中：改寫版的同一則謠言 0.79–0.82，不同謠言 ≤0.68）。換 embedding 模型要重新量測。
- **只有 `verified=true` 的資料列能在向量層命中**；網址層與 hash 層不過濾。
- 網址抓不到內文或平台不支援 → 直接回 `UNVERIFIABLE`，不呼叫 AI、不寫知識庫。圖片分析沒有快取層，也不寫知識庫。
- AI 失敗的 fallback 結果不寫進知識庫，也不會被當成快取命中。
- 回應的 `cached`／`cache_layer`（`url`／`hash`／`vector`）標示命中哪一層。快取命中不佔每日 AI 額度。線上實測：AI 判定約 9–27 秒，向量命中約 3 秒。
- 沒有 embedding 金鑰時向量層自動停用，其餘兩層照常運作。
- **查核結果回補**：網址層與 hash 層命中 `verified=false` 的列時，先以該列的向量到向量層只找 `label_source` 為 rule／gold／admin 的列（查核機構文章索引或人工確認）；對得上就改回那一筆（`cache_layer=vector`）。一般 AI 判定的列不能取代舊結果。查核機構的新結論由 `POST /api/trending/refresh?analyze=false` 寫入（只耗 embedding）；`scripts/recheck_unverified.py` 可唯讀盤點哪些未證實資料已有查核結果對得上。

---

## 🚦 來源分級與判定

`app/utils/source_tier.py`（只有已經有判定的來源才算查核來源）：

| Tier | 名稱 | 條件 |
|------|------|------|
| 1 | 查核機構 | `tfc-taiwan.org.tw`、`mygopen.com`、`gov.tw`、`who.int`、`cdc.gov`；Cofacts 文章必須已有 RUMOR／NOT_RUMOR 回覆 |
| 2 | 媒體查核報導 | 一般網域，但標題同時含查核語境詞與不實判定詞 |
| 3 | 相關討論（未查證） | 其餘一律；`news.google.com`、Threads、Facebook、LINE 網域固定是 Tier 3 |

回應的 `sources` 只放 Tier 1／2，Tier 3 放 `related_discussions`。知識庫寫入時，有 Tier 1／2 來源或確定性標記（`rule`／`gold`／`admin`）才算 `verified`。

`app/utils/verdict.py` 的 `frame_of` 是燈號的唯一來源（網頁與 Threads 回覆都只讀 `frame_type`／`frame_label`），先符合者勝：

1. `ai_unavailable` → 灰「AI 暫時無法使用」
2. `UNVERIFIABLE` → 黃「無法查證」
3. 有風險：`SCAM` → 紅「詐騙警告」；`MISINFO` → 紅「假訊息」；其他 → 紅「風險訊息」
4. `SAFE` 但 `verification_status` 不是 `verified`／`rule` → 黃「尚無查核機構證實」
5. `SAFE`、已證實且信心 ≥ 0.7 → 綠「查無異常」
6. 其餘 → 黃「尚待確認」

Fallback 契約：AI 失敗時 `summary` 以「AI 分析暫時無法使用」開頭、`ai_unavailable=true`；判斷一律用 `verdict.is_fallback()`。改這段字樣時，前端 `src/lib/api.js` 的 `FALLBACK_PREFIX` 要一起改。

---

## 🛡️ 上線護欄

| 護欄 | 檔案 | 行為 |
|------|------|------|
| 每日 AI 次數上限 | `app/services/ai_budget.py` | 計數存 SQL 表 `ai_usage_daily`，主機重啟不歸零。達上限後，沒查過的內容回 429 `daily_cap_reached`（帶 `Retry-After`）；快取命中照常放行 |
| 每 IP 限速 | `app/utils/rate_limit.py` | 行程內滑動視窗（每分鐘、每小時），超過回 429 `rate_limited` |
| 請求大小上限 | `app/utils/body_limit.py` | JSON 1 MB、圖片 10 MB，超過回 413 `payload_too_large` |
| SSRF 防護 | `app/utils/safe_url.py` | 只允許 http／https 與 port 80／443；DNS 解析後拒絕 loopback、私有與保留位址；轉址最多 3 次且每跳重新檢查；回應超過 2 MB 中止。被拒回 422 `blocked_url` |
| 管理端點授權 | `app/utils/admin_auth.py` | `X-Admin-Token` 與 `ADMIN_TOKEN` 以固定時間比對；缺或錯回 401，`ADMIN_TOKEN` 沒設定回 403 |

錯誤回應一律是 `{"detail": 繁中說明, "code": 機器碼}`。

---

## 🔌 API 路由

線上：`https://fakenewsverify.vercel.app/api/...`；Swagger UI：https://fakenewsverify-api.onrender.com/docs（本機：http://localhost:8000/docs）。

| 方法 | 路徑 | 說明 |
|------|------|------|
| POST | `/api/analyze/text` | 文字查證（非同步）：回 `task_id`／`result_id`，再讀 `/api/result/{id}`。內容 1–20,000 字 |
| POST | `/api/analyze/url` | 網址查證（非同步）：伺服器端驗證網址並做 SSRF 檢查 |
| POST | `/api/analyze/sync` | 文字或網址查證（同步），一次回傳結果，給自動化用（網頁前端走上面的非同步端點） |
| POST | `/api/analyze/image` | 圖片查證（multipart 欄位 `file`；以檔頭判斷 PNG／JPG／WEBP，10 MB 上限）。網頁尚未開放上傳介面 |
| GET | `/api/analyze/task/{id}`、`/api/analyze/task/{id}/status` | 舊端點，保留相容；處理中回 202 |
| GET | `/api/result/{id}` | 結果頁資料：`status`、`result`、`error`、`share`；找不到回 404 `result_not_found` |
| GET | `/api/knowledge` | 知識庫列表與搜尋：`q`、`risk_type`、`limit`（1–200，預設 30）、`offset`。只回已證實的資料列 |
| GET | `/api/knowledge/stats` | 知識庫統計 |
| GET | `/api/knowledge/hot` | 本站熱門查證：`limit`（1–50，預設 10）。最近 7 天被查證（含快取命中）的次數以半衰期 3 小時衰減排序；只回已證實的資料列，另帶 `recent_24h`、`recent_7d`、`last_seen_at` |
| GET | `/api/trending` | 熱門牆：`limit`（1–50，預設 10）、`risk_type` |
| POST | `/api/trending/refresh` | 手動觸發抓取熱門（管理端點）：`analyze`（預設 `true`；`false` 只抓查核文章並寫入知識庫、不呼叫判讀模型）、`per_feed`（1–25，預設 4）、`cofacts`（預設 `true`；`false` 只抓 MyGoPen／TFC）。一律擋下徵才、闢謠 TOP10、小考題等非查核文章 |
| POST | `/api/feedback/tasks/{id}` | 使用者回饋：`rating`、`comment`（選填） |
| POST | `/api/admin/tasks/{id}/override` | 人工覆寫判定（管理端點）：`risk_type`、`category`、`confidence_score`、`reason`、`admin_id` |
| GET | `/api/threads/status`、`/api/threads/replies` | Threads 機器人狀態與回覆紀錄（公開唯讀，不含 token） |
| POST | `/api/threads/poll` | 手動跑一輪輪詢（管理端點；`THREADS_MODE=off` 時回 `threads_disabled`） |
| GET | `/health`、`/api/health` | 健康檢查：`ai_available`、`threads_mode`、`scheduler`、`daily_ai_calls`、`storage_backend`。不呼叫任何付費 API |

管理端點都需要 `X-Admin-Token` 標頭。

---

## 🧰 工具腳本

都在 `code\backend` 目錄下執行。會呼叫 AI 的腳本會花額度，執行前先確認。

```powershell
# 檢視知識庫與熱門資料的分布（唯讀）
.\venv\Scripts\python scripts\check_db.py

# 低成本測試 AI provider 與 embedding
.\venv\Scripts\python scripts\test_ai_provider.py --provider cgu

# 評測（見「評測」）
.\venv\Scripts\python scripts\evaluate.py --report-only

# 批次查證熱門的 PENDING 記錄（會呼叫 AI；內建預算護欄，預設關閉 web_search）
.\venv\Scripts\python scripts\batch_verify_pending.py
.\venv\Scripts\python scripts\batch_verify_pending.py --skip-fetch

# 雲端資料層：檢查連線；把本機資料搬到 Supabase（預設 dry-run，加 --apply 才會寫入）
.\venv\Scripts\python scripts\check_supabase.py
.\venv\Scripts\python scripts\migrate_to_supabase.py
.\venv\Scripts\python scripts\migrate_to_supabase.py --apply --insert-only

# Threads：OAuth 取得／續期 token；機器人乾跑、驗憑證、重置模擬、跑一輪
.\venv\Scripts\python scripts\threads_auth.py
.\venv\Scripts\python scripts\threads_auth.py --refresh
.\venv\Scripts\python scripts\test_threads_bot.py
.\venv\Scripts\python scripts\test_threads_bot.py --live
.\venv\Scripts\python scripts\test_threads_bot.py --reset-sim
.\venv\Scripts\python scripts\test_threads_bot.py --poll
```

| 腳本 | 用途 |
|------|------|
| `evaluate.py` | 150 筆評測：混淆矩陣、accuracy、P／R／F1、FP／FN |
| `batch_verify_pending.py` | 抓一輪 RSS 並反覆查證 PENDING 記錄，直到清空、達預算或達回合上限 |
| `check_db.py` | 資料品質分布報告（`--out` 寫檔、`--list` 列出每筆熱門） |
| `check_supabase.py` | 檢查 Supabase 連線、pgvector 與資料表（不印連線字串） |
| `migrate_to_supabase.py` | 本機 Parquet／SQLite → Supabase，冪等；`--insert-only` 不覆寫雲端既有資料列 |
| `test_ai_provider.py` | 確認 AI provider 與 embedding 能正常呼叫 |
| `test_threads_bot.py`、`threads_auth.py` | Threads 機器人測試與 token 管理 |
| `threads_sim_mentions.example.json`、`threads_sim_seed.json` | 模擬模式的範例 mentions 與預熱用種子 |
| `ensure_admin_token.py` | 確保 `.env` 有非空的 `ADMIN_TOKEN`（`start.bat`／`start.sh` 每次啟動都會呼叫，不印出 token） |
| `clean_sources_2026_09.py` | 2026-09 來源清洗（一次性、冪等，預設 dry-run；已於 2026-09-16 套用） |
| `fix_factcheck_labels.py` | 一次性修復：查核報導錯標與 RSS 殘留的 HTML entities（冪等，支援 `--dry-run`） |
| `llm_second_opinion.py` | 清洗審閱輔助：用閘道的本地模型挑出「不是可查核主張」的資料列（只讀資料檔） |
| `reembed_vectors.py` | 列出維度不是 1536 的向量；`--apply [--target both]` 才以現行模型重算（DEF-05，2026-09-19 已套用） |
| `run_pf2.py` | PF-2 量測：對本機後端送出組員審定的改寫句，記錄命中層與延遲（執行前自動備份資料檔） |
| `pf2_similarity.py` | PF-2 診斷：算出每一句改寫句與知識庫的實際相似度（唯讀，不呼叫判讀模型） |
| `recheck_unverified.py` | 查核結果回補盤點：未證實列能否由已證實列、最新查核文章或 Cofacts 新回覆補上（唯讀；`--cloud` 讀正式資料；輸出含使用者原文，已 gitignore） |
| `ingest_factchecks.py` | 查核機構已證實資料批次入庫：`fetch`（MyGoPen、台灣事實查核中心、Cofacts）→ `embed` → `apply`（預設 dry-run；`--target cloud --apply` 寫正式資料庫）；`rollback` 撤回 |
| `evidence_confidence_study.py` | 證據信心研究：夾角與判定的關係、入庫後的誤命中檢查、話術原型；輸出報告到 `docs/test/results/` |

---

## 🧪 測試

```powershell
# 全部單元測試（離線、不呼叫 AI）
.\venv\Scripts\python -m pytest tests -q

# Postgres 契約測試（預設略過）：需要 RUN_PG_TESTS=1 與 .env 裡的 SUPABASE_DB_URL
$env:RUN_PG_TESTS='1'; .\venv\Scripts\python -m pytest tests\test_pg_store.py -q; Remove-Item Env:RUN_PG_TESTS
```

- **757 個通過**；另有 **29 個** Postgres 契約測試（`tests/test_pg_store.py`）預設略過。它們會連到真的 Supabase，但每次建立一個拋棄式 schema（`test_<8 位 hex>`），結束時整個刪掉，不碰 `public` 的正式資料，也不呼叫 AI。
- `tests/conftest.py` 在測試中預設關閉限速與每日上限，要測護欄的測試再自己打開。
- GitHub Actions（`.github/workflows/ci.yml` 的 `test` job）在每次 push／PR 到 `main` 時用 Python 3.12 跑 `python -m pytest tests -q`。

| 主題 | 測試檔 |
|------|--------|
| 快取與儲存 | `test_cache_and_store`、`test_kb_write_gate`、`test_task_store_schema`、`test_parquet_io`、`test_store_factory`、`test_sql_migration`、`test_pg_store`（需開關） |
| 判定、來源與 AI 契約 | `test_verdict`、`test_source_tier`、`test_marking_rules`、`test_url_validator`、`test_ai_service_contract`、`test_ai_prompt_rules`、`test_ai_timeout_budget` |
| API 與主流程 | `test_api`、`test_analyze_api`、`test_result_api`、`test_knowledge_api`、`test_health`、`test_processor_flow`、`test_keyword_search_missing`、`test_news_fetcher_async` |
| 上線護欄與安全 | `test_launch_guards`、`test_rate_limit`、`test_ai_budget`、`test_safe_url`、`test_admin_auth`、`test_ensure_admin_token` |
| Threads 機器人 | `test_threads_api`、`test_threads_auth`、`test_threads_bot_sim`、`test_threads_config`、`test_threads_reply_format`、`test_threads_state`、`test_threads_token` |
| 資料清洗 | `test_clean_sources` |

---

## 📊 評測

資料集 `data/eval_set.csv`：150 筆人工標註（SCAM／MISINFO／SAFE 各 50 筆）。

| 指標 | `gpt-5.4-mini`（2026-09-16，現行） | `gpt-5-mini`（2026-06，前一版） |
|------|-----------------------------------|--------------------------------|
| Accuracy | **100%** | 96.0% |
| Macro-F1 | 1.000 | 0.960 |
| 偽陰性 FN | **0** | 0 |
| 偽陽性 FP | 0 | 5 |

前一版的結果封存在 `data/eval_archive_gpt5mini_2026-06/`。150 筆全對，代表這組題目對現行模型已經太簡單；數字只說明在這份資料集上的表現。

```powershell
.\venv\Scripts\python scripts\evaluate.py --report-only   # 只用現有 eval_predictions.csv 重算指標，不呼叫 AI
.\venv\Scripts\python scripts\evaluate.py --limit 10      # 先試 10 筆（會呼叫 AI）
.\venv\Scripts\python scripts\evaluate.py                 # 全部 150 筆（會呼叫 AI）
.\venv\Scripts\python scripts\evaluate.py --resume        # 中斷後續跑
.\venv\Scripts\python scripts\evaluate.py --seed-db       # 判對的案例回填知識庫
```

| 產出 | 內容 |
|------|------|
| `data/eval_predictions.csv` | 每筆的 gold／pred／confidence／是否正確 |
| `data/eval_report.csv` | 各類 precision／recall／f1、accuracy、macro-F1 |
| `data/eval_binary.csv` | 二分類（有風險／安全）的 FP／FN |
| `data/eval_errors.csv` | 判錯的案例（現行結果為 0 筆） |
| `../../assets/confusion_matrix.png` | 混淆矩陣圖 |

`confidence_score` 是模型自評，沒有經過機率校準，前端只顯示「高／中／低」。系統效能請以評測結果為準。

---

## 🤖 Threads 查核機器人（延伸功能）

使用者在 Threads 上 @機器人，機器人讀取被回覆的貼文，走與 `/api/analyze/sync` 相同的查證流程，再回覆判定、摘要、查核來源與結果頁連結。

- `THREADS_MODE=sim`：模擬模式（`FakeThreadsService`，讀寫 `data/threads_sim/`），不需要網路與 token，demo 用的就是這個模式。
- `THREADS_MODE=live`：真的讀 mentions 並回覆。需要 Meta App Review，排在進度報告之後。
- 只在負責人電腦上跑，雲端固定 `off`：狀態檔是本機檔案，雲端主機重啟後會忘記回覆過誰。
- AI 失敗的 fallback 不回覆、不標記，額度恢復後下一輪會補回。
- 申請步驟與防呆設計見根目錄 [`CLAUDE.md`](../../CLAUDE.md) 第 11 節。

---

## 🐳 Docker（選用，不是正式部署路徑）

`Dockerfile` 與 `docker-compose.yml`（只有後端一個容器、本機檔案儲存）還留在這個目錄。正式環境用的是 Render + Supabase；compose 檔的環境變數清單還是舊的，使用前要自己補上 `STORAGE_BACKEND` 等新變數。
