# CLAUDE.md — 給 Claude Code 的專案說明

> **這份檔案是給 AI 助理（Claude Code）看的專案地圖。**
> **⚠️ 重要規則：每次對專案做出有意義的變更（新功能、改架構、換 API、調設定），都要同步更新這份檔案。**
> 讓任何一台機器上的 Claude Code 打開專案就能快速進入狀況。

**現況（2026-09-19）**
- 系統已經是**線上網站**：<https://fakenewsverify.vercel.app>。Vercel（React 靜態檔）把 `/api/*` 同源代理到 Render 後端
  `https://fakenewsverify-api.onrender.com`（FastAPI），資料在 Supabase Postgres + pgvector。架構與操作見第 12 節。
- AI 只用學校 **CGU AIR 閘道的 `gpt-5.4-mini`**（embedding `text-embedding-3-small`），沒有備援；myai168 已停用（第 2 節）。
- 進度報告資料都在 `presentations/2026-09_進度報告/`（簡報影片網址、投影片、報告內容說明、測試計畫書 PDF、分工表；
  先看該資料夾的 README）。**報告當天播的是 5 分鐘簡報影片**（老師 2026-09-20 的新規定）：
  <https://fakenewsverify.vercel.app/demo/presentation_v1.mp4>（4 分 38 秒，原始碼 `video/hf-presentation/`，
  規格 `docs/demo/presentation_video_brief.md`，製作紀錄 `docs/demo/footage_log.md`）。
  舊的 demo 影片 v0.4.0：<https://fakenewsverify.vercel.app/demo/demo_v0.4.0.mp4>（`video/hf-demo/`）。
- **日常實作照 `docs/rebuild/03_tickets.md` 的票做**。上游文件：`00_consensus.md`（共識）→ `01_spec.md`（規格 v1.3）；
  測試項目、實測結果與未結缺陷在 `docs/test/TP-FNV-2026-01.md`（v1.5；6.5 為 2026-09-19～20 重測）。

---

## 1. 這個專案是什麼

**全民查證公社 — AI 假訊息與詐騙查證系統**（學生專題 / 論文；GitHub repo 是公開的）。
使用者到網站貼上**文字或網址**，系統判定 **詐騙(SCAM) / 假訊息(MISINFO) / 安全(SAFE)**（查不了 = `UNVERIFIABLE`），
以紅黃綠燈呈現並附上**已做出判定的查核來源**；每筆結果有可分享的獨立網址 `/r/{id}`。
另有熱門頁（「查核機構最新」＝MyGoPen／TFC RSS＋Cofacts；「本站熱門查證」＝最近 7 天大家查最多的已證實內容）、知識庫搜尋、
三層快取＋向量檢索、Threads 查核機器人（目前用模擬模式）。

- **使用方式**：直接開線上網站。`start.bat` / `start.sh` 只供**本機開發**（後端 8000 + React dev server 5173，用本機資料）。
- **輸入**：網頁 UI 只開放文字與網址。圖片端點 `/api/analyze/image` 後端已有（檔頭檢查、10 MB 上限），上傳 UI 尚未開放。
  影片與 Facebook／Instagram 連結不支援（回 `UNVERIFIABLE`，請使用者改貼文字）。
- **前端**：React 是唯一介面（`code/frontend`：React 19 + Vite 8.3.0 + Tailwind 4 + react-router，不加 UI 套件）。
  舊單檔查核儀封存在 `legacy/`，不再維護；啟動腳本不會開啟它。
- **後端**：FastAPI + Uvicorn（`code/backend`；2026-07 已從 `factcheck_system` 子目錄攤平）。
- **資料**：本機預設 `STORAGE_BACKEND=local` = SQLite（熱門、每日 AI 次數）+ Parquet（知識庫／任務／回饋）；
  雲端 `STORAGE_BACKEND=supabase` = Supabase Postgres + pgvector。

---

## 2. AI 引擎（CGU AIR 為唯一 provider，不直連官方）

**現行只有學校 CGU AIR 閘道**（OpenAI 相容 Responses API）：`AI_PROVIDER=cgu`，provider 鏈實際是 `['cgu']`，**沒有備援**。

| 用途 | base_url | 模型 | 設定鍵 |
|------|----------|------|--------|
| 分析（文字／網址／圖片） | `https://air.cgu.edu.tw/cgullmapi/v1` | `gpt-5.4-mini` | `CGU_API_KEY` / `CGU_BASE_URL` / `CGU_MODEL` / `CGU_REASONING_EFFORT`（預設 `medium`） |
| 向量 embedding | 同上 | `text-embedding-3-small`（1536 維） | `EMBED_RELAY_URL` / `EMBED_MODEL` / `EMBED_API_KEY`（空時退用 `CGU_API_KEY`） |

- **額度**：新學期金鑰，OpenAI 成本額度 **USD 10**＋本地模型 1,000 萬 tokens（共識 §4）。用量查 `GET {CGU_BASE_URL}/me/usage`
  （寫法見 `scripts/batch_verify_pending.py` 的 `cgu_cost_usd()`）。閘道教學頁：`https://air.cgu.edu.tw/workspace4/LLMAPI/api_call.html`。
- **myai168（OpenAI／Claude 中繼）已停用**：`.env.example` 把它註解在「已停用」區，雲端只設 CGU 金鑰。舊碼留著供日後切回
  （`ai_service.py` 的 `_openai_analyze`／`_claude_analyze`；`config.py` 的 `MYAI_API_KEY`、`OPENAI_*`、`CLAUDE_*`，且 `AI_PROVIDER`
  的程式預設值仍是 `openai`）。`AIService` 只把金鑰與 base_url 都有設的 provider 放進鏈，所以沒有 `MYAI_API_KEY` 時鏈裡只會有 `cgu`。
  切回前要知道的舊教訓：402 `insufficient_credits` = 點數用完；400 `no_pricing_info` = 模型在中繼下架；anthropic 中繼不支援
  hosted web_search（`_claude_analyze` 一律不帶）。沒有 Gemini。
- 2026-09 已移除、不要再引用：Serper、Google News 抓取、Playwright、yt-dlp、影片語音轉文字。
- **金鑰命名刻意避開標準名**（`CGU_API_KEY`、`MYAI_API_KEY`、`OPENAI_RELAY_URL`、`SUPABASE_DB_URL`…）：**不要**用 `OPENAI_API_KEY`／
  `ANTHROPIC_BASE_URL`／`DATABASE_URL`，系統或主機平台既有的同名環境變數會蓋掉 `.env`（pydantic 環境變數優先序高於 .env）。
- `DEMO_MODE=true` 會讓分析端點直接回固定的假結果（不呼叫 AI）；本機與雲端都應該是 `false`。

### 💰 額度與成本（最常踩雷）
- 量級（2026-09-16 實測，測試計畫書 PF-5）：每次未命中快取的查證約 **USD 0.0064**、150 筆評測約 USD 0.94。
  ⚠️ 後端 log 的 `usd` 欄低估約一半（DEF-06，第 8 節），對帳以 `/me/usage` 為準。
- `web_search` 工具讓每次呼叫**貴 3–7 倍**，由 `USE_WEB_SEARCH` 控制（`config.py` 與 `.env.example` 預設 true；**雲端設 false**；
  `evaluate.py` 固定不帶、`batch_verify_pending.py` 預設關）。CGU 閘道是否支援 `web_search` 尚未驗證（spec §12 R1）；
  帶了失敗時 `_run_analysis_chain` 會關掉 web_search 再試一次。
- ⚠️ **`minimal` 推理與 web_search 不相容**（gpt-5 系列帶了會 HTTP 400）：`_responses_analyze` 在 effort 為 `minimal` 時自動不帶。
  CGU 讀的是 `CGU_REASONING_EFFORT`；`OPENAI_REASONING_EFFORT` 只影響已停用的 myai168 OpenAI provider。
  第 6 節的評測數字是在 `medium` 量到的，改推理強度要重跑評測。
- 一次分析（含重試）共用 `AI_TIMEOUT_SECONDS=60` 的 wall-clock 預算（`ai_service._run_analysis`）。
- **每日 AI 次數上限** `DAILY_AI_CALL_CAP=300`（`app/services/ai_budget.py`；台灣時間 00:00 歸零）：達上限後沒查過的內容回
  429 `daily_cap_reached`，快取命中照常。評測與批次腳本不經過這個計數。
- 排程預設關閉（`ENABLE_SCHEDULER=false`，雲端也關），避免背景持續燒額度。`scripts/batch_verify_pending.py` 的 `--budget-cap`
  預設 18 美元是舊額度時代的值，現在額度只有 USD 10，跑批次要自己帶較小的值。

### 🚨 AI 壞掉時的排查（單一 provider，沒有備援）
**症狀**：結果頁出現灰色「AI 服務暫時無法使用」卡片；API 回 `ai_unavailable: true`（`risk_type=SAFE`、`confidence_score=0`、
`summary` 以「AI 分析暫時無法使用」開頭）。這種結果不寫知識庫、不提供分享、Threads 機器人不回覆也不標記。

1. `curl.exe -s https://fakenewsverify.vercel.app/api/health`（本機：`http://localhost:8000/api/health`）：
   - `"ai_available": false` → 後端沒讀到 `CGU_API_KEY`（雲端：Render 後台 Environment 頁；本機：`code/backend/.env`）。
     `true` 只代表金鑰有設，**不代表金鑰有效或額度還夠**。
   - `"daily_ai_calls": {"used": N, "cap": 300}`：`used` 到頂是每日上限用完（429 `daily_cap_reached`，不是 AI 壞掉），隔日自動恢復。
   - 逾時或 502／504 → Render 免費主機正在喚醒（約 1 分鐘）或部署中。
2. 後端 log 找 `[AI] cgu HTTP <碼>`（雲端：Render 服務頁的 Logs；本機：後端視窗）。401 = 金鑰錯或被重置；其餘對照
   `ai_service._classify_upstream_error`（402 → 額度、429／503 → 限流）。額度另查 `/me/usage`。
3. 本機低成本驗證（一次 AI 呼叫＋一次 embedding，印出 `risk_type` 或 HTTP 錯誤碼）：
   `cd code\backend` 後執行 `.\venv\Scripts\python scripts\test_ai_provider.py --provider cgu`。
   懷疑閘道擋校外主機時，手動觸發 GitHub Actions 的 `cgu-reachability`（不帶金鑰；回 401／403 = 連得到）。

**恢復**：金鑰或額度問題要找學校；拿到新值後**本機 `.env` 與 Render 後台兩邊都要更新**（Render：Environment → Save and deploy；
本機：重啟後端）。更多雲端症狀見 `docs/rebuild/runbook_cloud_deploy.md` 附錄 2。熱門、知識庫、快取命中都不呼叫 AI，不受影響。

> **fallback 契約（改字樣前先看）**：AI 失敗時端點仍回 **HTTP 200**。唯一產生處是 `ai_service._default_fallback_result()`
> （`ai_unavailable: true`＋`summary` 前綴「AI 分析暫時無法使用」）；後端唯一判斷點是 `app/utils/verdict.py` 的 `is_fallback()`；
> 前端畫面只讀 `ai_unavailable` 布林，前綴字串只定義在 `src/lib/api.js` 的 `FALLBACK_PREFIX`（舊資料相容用）。
> 封存的 `legacy/` 查核儀也靠這個前綴。

---

## 3. 三層快取（省最貴的 AI 呼叫）

```
文字輸入 → L1: 內容 Hash → L2: 向量（以「使用者原文」比對）→ L3: AI（分析對象就是使用者原文；不爬、不送搜尋引擎）
網址輸入 → L0: URL 快取 → L1: Hash → 爬蟲（爬不到 → UNVERIFIABLE，不呼叫 AI）→ L2: 向量（以爬到的內文比對）→ L3: AI
圖片輸入 → 沒有快取層，直接 L3（不寫知識庫）
L3 之後  → 剔除與被查網址同網域的來源 → 過濾死連結 → 來源分級 → 回填知識庫（AI 失敗的 fallback 不寫）
L0／L1 命中「未證實」列 → 查核結果回補：以該列向量到向量層只找 rule／gold／admin 列，對得上就改回那一筆（spec FR-20）
```
- 實作：`app/workers/pandas_task_processor.py`（主流程）。快取存取經 `store_factory.get_knowledge_store()`：本機
  `pandas_store.PandasStore`（Parquet、numpy 矩陣化 cosine），雲端 `pg_store.PgKnowledgeStore.find_similar_by_vector`（pgvector）。
- **文字輸入永不爬取、永不送搜尋引擎（FR-01）**：AI 分析的與向量層比對的都是使用者原文
  （2026-07 教訓：拿爬完的網頁全文比對，長文對短句過不了門檻，向量層形同虛設——勿改回）。
- **向量層只比對 `verified=true` 的列（FR-17）**；URL／Hash 層不過濾。知識庫頁 `/api/knowledge` 也只回 verified 列。
  寫入門檻見第 9 節。非 1536 維的向量不參與比對（本機只比同維度；雲端存成 NULL）。
- Layer 2 門檻 `SIMILARITY_THRESHOLD=0.75`：**實測校準**（text-embedding-3-small、繁中）
  改寫版同一謠言 0.79~0.82、不同支謠言 ≤0.68、不同主題 ≤0.52；舊值 0.88 會把改寫版全擋掉。
  換 embedding 模型要重新量測。改門檻改 config（兩個 store 都讀 `settings`）；不要為了讓 PF-2 過關而調低（第 8 節）。
- 回應帶 `cached` / `cache_layer`（url/hash/vector）：結果頁顯示「快取命中・相同網址／相同內容／語意相似」chip。
  快取命中不呼叫 AI、不耗每日 AI 次數。
- 實測：L1 命中 p50 213 ms、L2 向量命中 p50 3.06 s（2026-09-16 本機，測試計畫書 6.4）；
  線上新內容 AI 判讀 9–27 秒、語意快取命中約 3 秒（2026-09-19）。
- embedding 沒有可用金鑰或呼叫失敗時 Layer 2 自動停用，URL/Hash 仍正常。
- **查核結果回補（FR-20，2026-09-22）**：URL／Hash 層不過濾 verified，一字不差的重複查詢原本會一直拿到當初「尚無查核機構證實」。
  命中未證實列時，處理器以該列向量（Postgres 版沒載入向量時以原文算一次 embedding）呼叫
  `find_similar_by_vector(..., label_sources=DETERMINISTIC_LABEL_SOURCES)`，**只讓 rule／gold／admin 列取代舊結果**
  （一般 AI 判定＋來源的列可能只是長得像的另一則訊息）。查核機構的新結論靠熱門牆抓取以 `rule` 寫入：
  `POST /api/trending/refresh?analyze=false&per_feed=25&cofacts=false` 只抓 MyGoPen／TFC 的 RSS 與寫入結論、不呼叫判讀模型
  （Cofacts 的 RUMOR 文章常是對話片段，寫進知識庫前要另外審閱）。抓取時擋下徵才、闢謠 TOP10、小考題等非查核文章；
  `_cleanup_legacy_strings` 不再把 Cofacts 已查核的謠言退回未查證（它的判定來自回覆、標題沒有【錯誤】標籤）。
  盤點用 `scripts/recheck_unverified.py [--cloud]`（唯讀）：2026-09-22 正式資料 86 筆可比對、0 筆達 0.75。

---

## 4. 主要檔案地圖

```
code/backend/
├── app/
│   ├── main.py                 FastAPI 入口；lifespan（資料層初始化、護欄、排程 opt-in）；/health = /api/health
│   ├── config.py               所有設定（pydantic Settings；.env 以 UTF-8 讀、extra=ignore）
│   ├── database_sql.py         SQL engine：本機 SQLite／雲端 Supabase Postgres（錯誤訊息遮蔽連線字串）
│   ├── api/analyze.py          /api/analyze/{text,url,sync,image}、task/{id}、task/{id}/status（限速→SSRF→每日上限→建任務）
│   ├── api/result.py           /api/result/{id} 結果頁資料（讀任務 store；含分享文案）
│   ├── api/knowledge.py        /api/knowledge、/stats、/hot（熱門查證；三者都只回 verified 列）
│   ├── api/trending.py         /api/trending（查核機構優先、Cofacts ≤3 筆排最後）；POST /refresh 需管理 token
│   │                            （?analyze=false 只抓查核文章寫入知識庫、不呼叫判讀模型；?per_feed=1..25；
│   │                            ?cofacts=false 只抓 MyGoPen／TFC）
│   ├── api/threads.py          /api/threads/{status,replies} 公開唯讀；POST /poll 需管理 token
│   ├── api/admin.py            /api/admin/tasks/{id}/override 管理者覆寫（X-Admin-Token；label_source=admin）
│   ├── api/feedback.py         /api/feedback/tasks/{id} 使用者回饋
│   ├── models/fact_check_record.py  熱門記錄（唯一的 SQLAlchemy model）
│   ├── services/
│   │   ├── ai_service.py       ★AI 呼叫、系統 prompt（含 FR-19 來源規則）、fallback 契約、embedding
│   │   ├── ai_budget.py        每日 AI 次數上限（FR-14；SQL 表 ai_usage_daily、原子扣額度）
│   │   ├── store_factory.py    ★取得 store 的唯一入口：依 settings.use_supabase 回傳本機檔案版或 Postgres 版
│   │   ├── pandas_store.py     本機知識庫 Parquet：三層快取查詢＋寫入門檻 compute_write_gate（雲端版共用）
│   │   ├── pg_store.py         ★雲端 store：PgKnowledgeStore／PgTaskStore／PgAuditStore（介面與行為對齊本機版）
│   │   ├── task_store.py       本機任務＝結果頁 Parquet（上限 5,000 筆，只修剪已結束的）
│   │   ├── audit_store.py      本機覆寫／回饋紀錄 Parquet
│   │   ├── crawler.py          網址爬取（safe_url + trafilatura）；影音與 FB／IG 回 unsupported_platform
│   │   ├── news_fetcher.py     熱門牆流程＋第 9 節標記規則；search_service.py = MyGoPen／TFC RSS＋Cofacts
│   │   ├── hot_claims.py       熱門查證排行：查證紀錄 tasks.kb_id × 半衰期 3 小時的時間衰減、7 天視窗（FR-21）
│   │   ├── cache_service.py / vector_service.py   內容 SHA-256 hash／embedding 包裝
│   │   ├── threads_service.py  Threads Graph API 客戶端（live）、ThreadsClient 介面、token 檔
│   │   └── threads_sim.py / threads_state.py / threads_reply.py   模擬模式／狀態與回覆紀錄（原子寫入）／回覆模板
│   ├── utils/
│   │   ├── verdict.py          ★紅黃綠單一權威 frame_of（8 列規則）＋ is_fallback（fallback 唯一判斷點）
│   │   ├── source_tier.py      ★來源分級 Tier 1/2/3（tier_of、grade_sources；offline 時不發請求）
│   │   ├── safe_url.py         SSRF 防護（check_url／safe_get）；url_validator.py 經它過濾 AI 幻覺出的死連結
│   │   ├── admin_auth.py       require_admin（X-Admin-Token；ADMIN_TOKEN 空字串 = 403 停用）
│   │   ├── rate_limit.py / body_limit.py   每 IP 限速（429）／請求大小上限（413；一般 1 MB、圖片 10 MB）
│   │   └── labels.py / share.py / parquet_io.py   分類中文化／分享文案與結果頁網址／Parquet 原子寫入＋行程內鎖
│   └── workers/
│       ├── pandas_task_processor.py  ★三層快取＋AI 主流程（阻塞呼叫一律 to_thread，不卡 event loop）
│       ├── task_queue.py        enqueue = 直接呼叫處理器（沒有外部佇列）
│       └── threads_bot.py       機器人輪詢（流程與防呆寫在檔頭 docstring）
├── scripts/
│   ├── evaluate.py             ★評測（--seed-db、--report-only、--resume、--limit）
│   ├── test_ai_provider.py     低成本測 AI＋embedding
│   ├── batch_verify_pending.py 批次查證熱門 PENDING（以 CGU 用量當護欄）
│   ├── check_db.py / check_supabase.py   本機資料分佈（唯讀）／Supabase 連線檢查（不印連線字串）
│   ├── migrate_to_supabase.py  本機 Parquet／SQLite → Supabase（預設 dry-run；--apply、--insert-only）
│   ├── clean_sources_2026_09.py  FR-18 資料清洗（預設 dry-run、冪等、--apply 前自動備份；2026-09-16 已套用）
│   ├── recheck_unverified.py   FR-20 唯讀盤點：未證實列 vs 已證實列／最新查核文章／Cofacts 新回覆（輸出含原文，gitignored）
│   ├── llm_second_opinion.py / fix_factcheck_labels.py   清洗審閱輔助（CGU 本地模型）／2026-07 一次性標籤修復
│   ├── ensure_admin_token.py   啟動腳本每次呼叫：.env 的 ADMIN_TOKEN 空就補亂數（不印出）
│   ├── threads_auth.py         Threads OAuth 取得／續期 token → data/threads_token.json
│   ├── test_threads_bot.py     機器人乾跑／--live／--reset-sim／--poll
│   └── threads_sim_mentions.example.json、threads_sim_seed.json   模擬模式的範例 mentions 與 gold 種子
├── tests/                      ★pytest **729 個**離線測試（零 AI 點數，CI 每次 push 跑）＋ test_pg_store.py **26 個** Postgres
│                                契約測試（要 RUN_PG_TESTS=1，平常略過）；conftest.py 預設關閉上線護欄。
│                                test_marking_rules 守第 9 節；test_verdict／test_ai_service_contract 守燈號與 fallback 契約
├── data/
│   ├── knowledge_base.parquet  ★已提交的種子（清洗後 218 筆、verified 128）。平常執行的變動不用 commit；**例外**：FR-18
│   │                            清洗後的版本提交過一次作新種子（commit db8c62d），以後重做清洗／重建種子才再提交
│   ├── eval_set.csv、eval_*.csv、eval_archive_gpt5mini_2026-06/   評測題庫、最新結果、前一版結果封存
│   ├── SCHEMA.md               資料結構說明
│   └── （runtime，已 gitignore）factcheck.db、tasks.parquet、回饋／覆寫 Parquet、threads_*、uploads/、*.bak-*、clean_sources_*
├── .env                        ★真實金鑰，已 gitignore；AI 助理不讀、不印、不提交。範本是 .env.example
├── requirements.txt / requirements-prod.txt   本機＋CI／雲端（Render）；app/ 新增 import 時兩個檔都要加
├── _run_backend.bat、Dockerfile、docker-compose.yml   本機啟動檔／2026-07 留下的容器設定（雲端不用，Render 走 render.yaml）
└── venv/（本機建立，不進 git）
code/frontend/                  React 19 + Vite 8.3.0 + Tailwind 4
├── vercel.json                 ★全專案唯一一份：/api/* 同源代理到 Render；其餘走 SPA fallback（排除 *.html）
├── vite.config.js              dev proxy：/api → http://localhost:8000
├── public/                     privacy.html、data-deletion.html、deauthorize.html（Meta Threads use case 要求的靜態頁）、og.png、
│                                demo/demo_v0.4.0.mp4（網站上可直接播放的 demo 影片）
└── src/
    ├── main.jsx、routes.jsx    路由：/、/r/:id、/trending、/knowledge、/bot（目前是佔位頁）、/oauth/callback、*（404）
    ├── i18n.js                 ★所有使用者看得到的文案（元件內不寫中文字串）
    ├── index.css               ★設計 token：淺色預設＋深色（data-theme）；紅黃綠只用於判定；強調色只有 --c-accent
    ├── pages/                  Home、Result、Trending、Knowledge、Bot、OAuthCallback、NotFound
    │                            ＋ home/ result/ trending/ knowledge/（各頁的子元件、hook、model）
    ├── components/             通用元件（InputCard、VerdictBlock、SourceRow、Banner…）＋ shell/（AppShell、導覽、useBackendStatus）
    ├── lib/                    api.js（★所有後端呼叫的唯一入口、FALLBACK_PREFIX）、fixtures.js、verdict.js、history.js、
    │                            validateInput.js、httpUrl.js、theme.js、useDocumentTitle.js
    ├── dev/fixtures/           開發用假回應（VITE_FIXTURES=1 才生效，production build 會剔除；用法看該資料夾 README）
    └── **/*.test.js            單元測試（node --test，**390 個**）
legacy/                         已封存、不再維護：舊單檔查核儀 fake-news-detector.html、_run_detector.bat、README.md
render.yaml                     Render Blueprint（後端雲端部署設定；金鑰只在 Render 後台輸入，檔案裡只有鍵名）
.github/workflows/ci.yml        push／PR：test（後端 pytest）＋ frontend（build、單元測試）
.github/workflows/keepalive.yml 每 10 分鐘叫醒 Render 後端＋讀一次資料庫（網址取自 repository variable BACKEND_BASE_URL）
.github/workflows/cgu-reachability.yml   手動觸發：確認校外雲端主機連不連得到 CGU 閘道（不帶金鑰）
start.bat / start.sh            本機開發用一鍵啟動：後端 8000 + React 5173（本機資料）；start-debug.bat 逐步診斷
docs/rebuild/                   ★2026-09 重做的文件：00_consensus、01_spec（v1.3）、02_mockup_brief＋mockup/（.dc.html 設計畫布）、
                                03_tickets（109 張票）、owner_decisions_day0、runbook_cloud_deploy、runbook_tunnel（退路）
docs/test/                      測試計畫書 TP-FNV-2026-01.md（v1.5）、results/（原始紀錄）、screens/（截圖）、ui_checklist.csv、
                                pf2_paraphrases.csv、clean_sources_review.md（清洗審閱紀錄）
docs/demo/                      demo 影片的分鏡、素材紀錄、貼文腳本與字幕（.srt）；mp4 原檔不進 git
video/hf-demo/                  demo 影片 v0.4.0 的 HyperFrames 專案原始碼（有自己的 CLAUDE.md；只在本機 render）。
                                video/ 其餘是未採用的 Remotion 試作，不進 git
presentations/                  簡報與報告資料；`2026-09_進度報告/` = 這次進度報告的全部檔案（投影片、報告內容說明、demo 影片網址、
                                測試計畫書 PDF、分工表），檔名用中文、前面有編號，組員一看就懂；先看該資料夾的 README。
                                影片檔在 code/frontend/public/demo/（網站上可直接播放；GitHub 網頁不能播 mp4，所以報告資料夾只放網址）。
                                負責人不要逐張講稿：只放「報告內容說明」，投影片的備忘稿已清空
assets/                         PlantUML 圖 + confusion_matrix.png（最新評測的混淆矩陣）
└── 期末專題文件/                OOSE 期末繳交文件(詞彙表/使用案例圖/情節/活動圖/類別圖+README)
```

**設定鍵**都定義在 `app/config.py`（範本 `.env.example`；雲端的值寫在 `render.yaml`）。站台相關：`PUBLIC_BASE_URL`（分享連結、Threads
回覆、OAuth redirect 都用它；雲端 = `https://fakenewsverify.vercel.app`）、`ADMIN_TOKEN`（管理端點的 `X-Admin-Token`；空字串 =
管理功能停用）、`CORS_ORIGINS`；`BRAND_NAME`、`CONTACT_EMAIL` 目前程式沒有讀取（靜態頁的品牌名與信箱直接寫在 `public/*.html`）。
資料層與護欄見第 7、12 節；AI 見第 2 節；Threads（`THREADS_MODE`、`BOT_HANDLE`…）見第 11 節。

---

## 5. 常用指令

PowerShell 5.1 寫法；venv 一律用 `python -m ...`（理由見第 7 節）。

```powershell
# ── 線上網站 ──（PowerShell 5.1 的 curl 是 Invoke-WebRequest 的別名，要打 curl.exe）
curl.exe -s https://fakenewsverify.vercel.app/api/health
#   正常："storage_backend":"supabase"、"ai_available":true、"daily_ai_calls":{"used":N,"cap":300}
#   逾時或 502／504：Render 免費主機正在喚醒，等 1 分鐘再試

# ── 本機開發一鍵啟動（專案根目錄）：後端 8000 + React 5173，用的是本機資料 ──
.\start.bat

# ── 後端：以下都先 cd code\backend ──
.\venv\Scripts\python -m pip install -r requirements.txt
.\venv\Scripts\python -m uvicorn app.main:app --reload --port 8000    # API 文件 http://localhost:8000/docs
.\venv\Scripts\python -m pytest tests -q                              # 729 個，離線、零點數
.\venv\Scripts\python scripts\check_db.py                             # 本機知識庫／熱門的資料分佈（唯讀）
.\venv\Scripts\python scripts\test_ai_provider.py --provider cgu      # 低成本測 AI＋embedding（各一次呼叫）
.\venv\Scripts\python scripts\evaluate.py --report-only               # 只重算評測報告（不呼叫 AI、零點數）
.\venv\Scripts\python scripts\evaluate.py --timing --delay 0       # 150 筆＋逐筆延遲（PF-1／QA-2；約 13 分鐘、約 USD 1）
.\venv\Scripts\python scripts\reembed_vectors.py                     # 列出維度不對的向量；--apply [--target both] 才重算（DEF-05）
.\venv\Scripts\python scripts\evaluate.py --delay 0                   # 重跑 150 筆評測（約 USD 1）；加 --seed-db 會把判對的寫進知識庫
.\venv\Scripts\python scripts\clean_sources_2026_09.py                # 資料清洗 dry-run（預設）；--apply 要負責人核准
.\venv\Scripts\python scripts\recheck_unverified.py                   # 未證實資料能否由查核結果回補（唯讀；--cloud 讀正式資料）

# Threads 機器人（模式說明見第 11 節）
.\venv\Scripts\python scripts\test_threads_bot.py                # 乾跑：檢查設定＋產生範例回覆（免 token、零點數）
.\venv\Scripts\python scripts\test_threads_bot.py --reset-sim    # 模擬模式重播：清模擬回覆與游標、離線預熱快取
.\venv\Scripts\python scripts\test_threads_bot.py --poll         # 觸發一輪輪詢並印結果（live 模式會真的回覆、花額度）
.\venv\Scripts\python scripts\test_threads_bot.py --live         # 有 token 時驗證憑證＋讀 mentions 筆數
.\venv\Scripts\python scripts\threads_auth.py                    # Threads OAuth 取得 60 天 token；--refresh 續期

# 管理端點要帶 X-Admin-Token（值 = .env 的 ADMIN_TOKEN；不要貼進聊天、issue 或 commit）
curl.exe -s -X POST http://localhost:8000/api/trending/refresh -H "X-Admin-Token: <ADMIN_TOKEN>"    # 會抓 RSS 並呼叫 AI

# 雲端資料層：檢查連線／搬資料（預設 dry-run）／對真的 Supabase 跑契約測試（拋棄式 schema，不碰 public）
.\venv\Scripts\python scripts\check_supabase.py
.\venv\Scripts\python scripts\migrate_to_supabase.py            # 加 --apply 才真的寫；--insert-only 不覆寫雲端既有列
$env:RUN_PG_TESTS='1'; .\venv\Scripts\python -m pytest tests\test_pg_store.py -q; Remove-Item Env:RUN_PG_TESTS

# ── 前端：以下都先 cd code\frontend ──
npm ci                 # 依 package-lock.json 安裝
npm run dev            # http://localhost:5173，/api 由 vite 代理到 localhost:8000
npm run test:unit      # node --test，390 個
npm run lint
npm run build          # 輸出 dist\；CI 的 frontend job 跑 build＋test:unit
```

---

## 6. 評測現況（論文數據）

- 資料集 `data/eval_set.csv`：150 筆（SCAM/MISINFO/SAFE 各 50），含刻意設計的「像詐騙的合法官方訊息」當難題。
- **最新結果（2026-09-16，CGU `gpt-5.4-mini`、web_search 關）：accuracy 100%、macro-F1 1.000、FN=0、FP=0**
  （有效預測 150／150；95% CI 0.976–1.000）。結果檔在 `data/eval_*.csv` 與 `assets/confusion_matrix.png`。
- 前一版（2026-06，myai168 `gpt-5-mini`）：accuracy 96.0%、macro-F1 0.960、FN=0、FP=5（把反詐宣導、政府補助公告誤判成 SCAM）；
  封存在 `data/eval_archive_gpt5mini_2026-06/`。兩版判定不同的 6 筆全是「舊錯新對」。
- **誠實的限制**：150 筆全對代表這組題庫對新模型已經**飽和**（太簡單），分不出模型或設定之間的差異；題庫從 2026-06 起就公開在 repo，
  也無法排除新模型看過。所以 100% **不能解讀成「系統不會出錯」**，對外要連同這個限制一起講；下一步是擴充題庫再比（第 8 節）。
- 重跑評測會呼叫真實 AI；`--report-only` 只重算報告、零點數。

---

## 7. 慣例與注意事項

- **Windows 主控台是 cp950**：`print()` **不要放 emoji / ✓✗**（會 `UnicodeEncodeError` 崩潰）。中文可以（Big5）。要輸出給人看的結果，寫成 UTF-8 檔再讀。
- **給負責人的指令一律 PowerShell 5.1 相容**：不用 `&&`／`||`（用 `;` 或 `if ($?) { ... }`）、打 `curl.exe` 不打 `curl`、
  環境變數用 `$env:NAME='值'`、路徑用 `.\venv\Scripts\python`。
- **`requirements.txt` 與 `requirements-prod.txt` 都只能放 ASCII**：pip 讀 requirements 用系統編碼（cp950），
  放中文註解會讓 `pip install -r` 直接 UnicodeDecodeError（start.bat 就炸在這，2026-07 踩過）。
  `.env` 可以有中文，因為 config 已指定 `env_file_encoding="utf-8"`。
- **repo 是公開的，金鑰只存在兩個地方**：本機 `code/backend/.env`（已 gitignore）與 Render 後台的 Environment 頁。
  不要把金鑰寫進任何檔案、commit、issue、聊天或截圖；AI 助理不要讀取或印出 `.env`。改設定改 `.env`；範本改 `.env.example`。
  Settings 已設 `extra="ignore"`：.env 有多餘舊變數不會炸，但也**不會警告拼錯的變數名**。
- **專案資料夾搬家後**（2026-09-19 發生過）：venv 的 `.exe` 啟動器（`pip.exe`、`uvicorn.exe`、`activate`）寫死建立時的路徑會失效，
  所以一律 `python -m pip`／`python -m uvicorn`／`python -m pytest`（啟動腳本已這樣寫）。複製過來的 `venv/`、`node_modules/` 可能缺檔
  （症狀：`import pandas` 失敗、`npm run lint` 找不到模組），而 `pip install -r` 會以為都裝好了 → 刪掉重建
  （`python -m venv venv` 再 `python -m pip install -r requirements.txt`；前端 `npm ci`）。
- **async 端點內不要直接呼叫 requests / 檔案或資料庫 IO**：會卡死整個 event loop（AI 呼叫最長 `AI_TIMEOUT_SECONDS`＝60 秒）。
  照 `pandas_task_processor.py` 的做法包 `asyncio.to_thread`；store 的方法（Parquet 與 Postgres 版）都是阻塞 IO。
- **使用者或 AI 給的網址，對外請求一律走 `app/utils/safe_url.py`**（SSRF 防護），不要直接 `requests.get`。
- **燈號與文案各只有一個來源**：燈號只讀 `frame_type`／`frame_label`（`verdict.frame_of`），前端與 Threads 回覆不自行由
  `risk_type` 推顏色；前端使用者看得到的字一律放 `src/i18n.js`。
- **runtime 資料不要提交**（`factcheck.db`、`tasks.parquet`、`data/threads_*`… 已 gitignore）。`knowledge_base.parquet` 是已提交的種子，
  平常執行造成的變動不用 commit；例外只有 FR-18 清洗後提交過一次的新種子（第 4 節）。
- commit 訊息結尾加 `Co-Authored-By: <model> <noreply@anthropic.com>`。
- 大檔不進 git（GitHub 單檔上限 100MB）：`docs/demo/*.mp4` 原檔、plantuml jar、舊報告影片（895MB，放雲端硬碟）；
  網站播放用的 12 MB demo 影片例外，放在 `code/frontend/public/demo/`。
- **資料層有兩種後端**（2026-09）：預設 `STORAGE_BACKEND=local` = SQLite（熱門）+ Parquet（快取/任務/回饋）；
  `STORAGE_BACKEND=supabase` 且有 `SUPABASE_DB_URL` = Supabase Postgres + pgvector（`app/services/pg_store.py`）。
  **取得 store 一律走 `app/services/store_factory.py`**，不要在新程式直接 `PandasStore()`／`TaskStore()`；
  改 store 行為時本機版與 Postgres 版要一起改（`tests/test_pg_store.py` 是兩邊行為一致的契約測試）。
  本機預設讀寫的是本機檔案，**不是線上那一份**；本機 `.env` 設成 supabase 就是直接讀寫線上正式資料（小心）。
  2026-07 移除的舊 PG 死碼（`app/database.py`、舊 PG models）與現在的 pg_store 無關，不要復活它們。
- **新增公開端點時要想到上線護欄**：會花 AI 點數的走 `ai_budget`、會寫資料庫的加欄位長度上限與
  `rate_limited_response(request, scope)`；測試中護欄預設關閉（`tests/conftest.py`）。
- **單機單寫者假設（只限本機檔案版）**：`parquet_io` 的原子寫入與鎖只保護同一個行程；Parquet/SQLite 沒有跨行程鎖。
  batch_verify_pending.py 與後端伺服器同時「寫入」有機率互相蓋掉（讀取無妨）。跑批次或評測 `--seed-db` 時避免同時做大量查證。

---

## 8. 待辦 / 進行中（更新時請維護這段）

### 未完成（現況）
- [ ] 雲端知識庫補 demo 用的 gold 列：`scripts/threads_sim_seed.json` 的「健保卡即日起停用」不在搬上雲的資料裡
      （本機測試還原時被蓋掉）；上線驗證時另外產生了 3 筆未證實的測試列（含同 hash 的那一則），
      要先刪掉再以 STORAGE_BACKEND=supabase 執行預熱，否則 hash 層會先命中未證實的那筆
- [ ] Threads 真帳號串接（**進度報告後**；票 O-07、O-09、T-12～T-16、O-27）：Meta App + Threads Tester + 60 天 token；
      要公開給陌生人用必須通過 Meta App Review（＋企業驗證）。FN-4 的三項行為（HTTP 429 → `backoff_until`、未知 4xx →
      標 failed 不回覆、container `FINISHED` 才 publish／`ERROR` 重建一次）已於 2026-09-20 實作並以模擬與 mock 測過（T-12／T-13）；
      回應格式尚未對真的 Threads API 驗證（票 T-17）。state 檔新增 `backoff_until`／`backoff_n`／`transient_n`、`failed`、`pending_publish`
- [ ] PF-2 向量快取命中率 **65%（13／20）< 準則 70%**：以組員（姚睿）審定的改寫句題組重測（票 O-11）。DEF-05 已於 2026-09-19 修正
      （`scripts/reembed_vectors.py`，13 筆重算、本機與 Supabase 同步），但離線複查顯示那 20 句的原文向量本來就正常，未命中是相似度真的不夠；
      **不以調低 0.75 門檻來過關**（那是實測校準值，調低會提高誤命中）
- [ ] 測試計畫書 6.3 的未結缺陷（完整原文在 `docs/test/TP-FNV-2026-01.md`）：
      DEF-03 知識庫頁同一主張出現兩張卡且標籤不同（同一 Cofacts 文章分別以 TEXT 與 URL 入庫、各自判定）；
      DEF-04 部分已證實列的「主張」其實是查核機構文章標題卻被標為假訊息（待負責人逐筆人工確認）；
      DEF-05 128 筆已證實列中 11 筆向量維度是 768（5 筆）／3072（6 筆），實際可參與語意命中的是 **102 筆**（不是 113）
      → 用 `text-embedding-3-small` 重算，**已於 2026-09-19 完成**（`scripts/reembed_vectors.py --apply --target both`）；
      DEF-06 `MODEL_PRICING_PER_1M["gpt-5.4-mini"]`（0.75／4.50）是 CGU 閘道實際計價（1.5／9）的一半，log 的 `usd` 欄低估約 50%；
      DEF-07 寫入知識庫時 `pandas_store.py` 的 `pd.concat` 印「全 NA 欄 dtype」FutureWarning；
      DEF-08 `backend_down` 橫幅與首頁 inline 驗證紅字用了判定色 token，與 spec §8.1「紅黃綠只用於判定」字面衝突（待 6.4 審查裁定）
- [ ] 首頁圖片上傳 UI（票 S-13，P1）：後端端點已有檔頭檢查與 10 MB 上限；票 B-26 的圖片 bytes hash 快取與寫知識庫尚未做
- [ ] `/bot` 機器人狀態頁（票 S-11）：目前是佔位頁（`src/pages/Bot.jsx`）；後端 `/api/threads/status`、`/replies` 已就緒
- [ ] （選）擴充 eval_set 到 300 筆、做信心校準（現有 150 筆已飽和，見第 6 節）
- [ ] （選）前端加「評測數據」分頁顯示混淆矩陣/accuracy
- [ ] 查核結論每日進庫（FR-20）：以 GitHub Actions 每日呼叫 `POST /api/trending/refresh?analyze=false&per_feed=25&cofacts=false`，
      需負責人把 `ADMIN_TOKEN` 加入 repository secret；在那之前是手動觸發。不呼叫判讀模型，只耗 embedding
- [ ] 提供查核機構的熱搜名單（FR-21 延伸）：`hot_claims.rank()` 已可用於未證實內容；還缺管理端點、電話／帳號／人名遮蔽、
      隱私政策增列「提供查核機構」用途（現行政策只寫「供後續相同或相似內容快速比對」）
- [ ] 熱門牆標記規則的缺口（第 9 節範圍，改規則需負責人決定）：MyGoPen 的【詐騙】標籤不算確定判定，詐騙警示文章不會寫進知識庫；
      TFC 近期 RSS 標題多半沒有判定標籤（2026-09-22 抽 10 篇只有 1 篇命中），查核結論進庫以 MyGoPen 與 Cofacts 為主

### 已完成（2026-09 重做與上雲）
- [x] 查核結果回補與本站熱門查證（2026-09-22，spec v1.4 FR-20／FR-21，票 D-06、B-27～B-29、S-15）：
      URL／hash 命中未證實列時只讓 rule／gold／admin 列取代；`/api/trending/refresh?analyze=false`；
      `recheck_unverified.py` 唯讀盤點；`GET /api/knowledge/hot` 與熱門頁「本站熱門查證」分頁。pytest 718、Postgres 契約 26、前端 390
- [x] 2026-09 重做流程啟動：`docs/rebuild/` 依序為 00_consensus（grill 共識）→ 01_spec（功能+UX v1.3）
      → 02_mockup_brief + mockup/（設計畫布 .dc.html）→ 03_tickets（109 張票，依賴/排程/驗收指令）。
      **之後的實作一律照 03_tickets.md 的票做**；來源分級規則見共識 §9（只有已判定的查核來源才算來源）
- [x] 票 P-01／B-01／B-12 完成：Vite 釘 8.3.0 穩定版＋plugin-react ^5.2.0（移除 overrides）；
      ai_service 系統 prompt 加 FR-19 來源規則；新增 `app/utils/source_tier.py`（Tier 1/2/3、
      Cofacts 回覆查詢、離線模式不發請求）＋ tests/test_source_tier.py；pytest 65 passed
- [x] 票第二批（B-04/05/07/08/10/11/13/14、T-07、P-02/03/04/05/06）：`app/utils/verdict.py`（紅黃綠 8 列
      單一權威 + `is_fallback` 唯一判斷點）；PandasStore 寫入門檻（verified/source_tier，向量層只比對
      verified=true）；news_fetcher 阻塞呼叫全改 to_thread；移除 Serper/Google News/Playwright/yt-dlp；
      tasks.parquet 擴欄＋上限 5000；threads_state 原子寫入；CI 加前端 job；`public/` 三個靜態頁；
      `vercel.json`；`src/i18n.js` 文案表；舊查核儀移到 `legacy/`。pytest 133、前端 unit 156 全過
      （當時的過渡狀態——種子全為 verified=false、SAFE 一律黃燈——已隨下一項 D-05 套用與票 B-15 完成而結束）
- [x] D-05 資料清洗已套用（2026-09-16，負責人核准）：知識庫 218 筆（verified 128，113 筆帶向量；其中可用的 1536 維是 102 筆，見 DEF-05）、
      熱門 24 筆全 verified；Google News 與徵才/小考題/TOP10/聊天碎片等髒資料已刪。
      向量快取恢復命中（只比對 verified=true）。審閱紀錄 `docs/test/clean_sources_review.md`
- [x] 後端上雲（2026-09-19）：Supabase 資料層（pg_store + store_factory + migrate_to_supabase，已搬
      knowledge_base 218／fact_check_records 24／tasks 37）；上線護欄（每日 AI 300 次、每 IP 30/分 200/時、
      請求 1 MB／圖片 10 MB、圖片檔頭檢查、回饋欄位長度上限）；Render Blueprint + keepalive + runbook；
      前端「連不到後端」橫幅自動重試。pytest 553 passed（另 24 個 Postgres 契約測試需 RUN_PG_TESTS=1）
- [x] 雲端正式上線（2026-09-19）：Render 服務 `https://fakenewsverify-api.onrender.com`（Blueprint）；
      `code/frontend/vercel.json` 的 /api 代理已指向它；`BACKEND_BASE_URL` 已設、keepalive 每 10 分鐘執行。
      實測：`/api/health` 回 `storage_backend=supabase`、AI 即時判讀 9–27 秒、語意快取命中 3 秒且不耗每日額度

### 已完成（2026-07 以前；歷史紀錄）
> 以下保留當時的原文。其中提到的單檔查核儀、myai168／多 provider、Google News、yt-dlp、`App.jsx`／`mockData`、深色預設等，
> 已在 2026-09 重做時移除、封存或取代——**現況以第 1～4 節為準**。
- [x] 評測系統 + 150 筆資料集 + FP/FN 分析（accuracy 96%、FN=0）
- [x] 改用學校中繼 API（gpt-5-mini 主 / Claude 備援）+ CGU embedding
- [x] 新增 CGU AIR Gateway provider（AI_PROVIDER=cgu），保留 myai168 OpenAI/Claude 舊方案
- [x] 前端：移除測試卡片、加「資料庫」分頁（瀏覽/搜尋/篩選快取內容）
- [x] 前端 CSS 美化（漸層導覽、柔和背景、風險色卡、空狀態）
- [x] 省點數開關（ENABLE_SCHEDULER 預設關、USE_WEB_SEARCH、gpt-5-mini+minimal）
- [x] 修正熱門/資料庫誤標：只在「確定不實」才標假訊息（Cofacts RUMOR 判定 /
      MyGoPen·TFC【錯誤/誤導/假】標籤）；Cofacts 改抓 RUMOR-verified；其餘標 PENDING
- [x] 統一卡片風格 InfoCard：今日熱門/資料庫同款卡片；PENDING 顯示「未查證」；
      /api/trending 已查證優先
- [x] 目錄攤平：`code/backend/factcheck_system/*` → `code/backend/`；刪死檔/alembic/inner pkg
- [x] 修正熱門「全是 Cofacts 個人對話」：`api/trending.py` 改真新聞(MyGoPen/TFC/Google)
      優先、Cofacts 個人投稿限量(≤3)排到最後，避免單一來源洗版
- [x] 新增單檔查核儀 `fake-news-detector.html`：設計token系統+環形儀表盤+掃描動畫+三視圖；
      熱門/資料庫接真後端、離線 fallback；分類中文化、198筆顯示前60；localStorage 歷史
- [x] React 前端深色化：改採查核儀設計語言(深色青綠+語意色)，改 index.css/mockData/App.jsx；邏輯不變
- [x] 一鍵啟動改版：`start.bat`/`start.sh` 路徑修正(攤平後 `code\backend`)、改啟動後端+查核儀；
      新增 `_run_detector.bat`(http.server 8090)
- [x] 一鍵啟動加 React：`start.bat`/`start.sh` 同時開後端 + 查核儀(8090) + React(5173)
- [x] 查核儀檢測接後端：改接 `/api/analyze/sync`(同步真 AI)、信心度→可信度換算、
      失敗自動 fallback 前端啟發式、標「即時 AI／離線」；後端 AI 額度用盡時仍不壞
- [x] 深/淺色主題切換：查核儀 + React 都加(data-theme + localStorage、深色預設)、
      新增 `--c-topbar-bg` token 讓頂欄跟著主題變
- [x] claude 引擎跳過 web_search（myai168 anthropic 中繼不支援 hosted 工具）
- [x] 修 bug：AI 額度用盡時 `/sync` 回 200 fallback，查核儀誤換算成「可信度 2/高風險/即時 AI」
      → 查核儀與 React 都改為辨識 fallback（summary 前綴）後轉離線/分析失敗顯示
- [x] 效能：阻塞呼叫（AI/embedding/爬蟲/來源驗證/yt-dlp）改 `asyncio.to_thread`；
      向量搜尋 numpy 矩陣化；`CRAWL_WITH_SCREENSHOT` 預設關（截圖無下游使用者）
- [x] 大掃除：刪 PG 死碼（app/database.py、4 個 PG models、pgvector 方法、5 個 emoji 舊 scripts）、
      requirements 刪 redis/rq/openai/aiohttp/Pillow、前端刪 axios、docker-compose 精簡為 backend-only、
      `.env.example` CORS 補 8090、`start-debug.bat` 修攤平後路徑
- [x] 修 start.bat pip 報錯：requirements.txt 中文註解 → cp950 UnicodeDecodeError；
      改純 ASCII + config 加 env_file_encoding="utf-8" + 清 venv 殘破 ~andas
- [x] Threads 查核機器人（延伸功能，模式 2）：threads_service + threads_bot + /api/threads；
      @機器人回覆可疑貼文 → 三層快取+AI 分析 → 自動回覆紅黃綠+來源；預設關、缺 token 全自動停用
- [x] 修「同一謠言兩種標籤」bug：查核報導判定對象統一為被查核的主張（見第 9 節三道防線）；
      RSS 標題 &nbsp; entities 清乾淨（_strip_html 解 entities + fix_factcheck_labels.py 修舊資料）
- [x] 單元測試 + CI：tests/ 當時 31 個 pytest（快取/標記規則/fallback契約/API冒煙/URL過濾，
      離線零點數；現在的數量見第 4 節）＋ .github/workflows/ci.yml（push/PR 自動跑，對應專題「測試驗證/品質保證」）
- [x] React 前端現代簡約化：token 精修（低對比邊框、主題感知陰影 --shadow-card/pop、
      柔和光暈）、裝飾 emoji 換幾何記號（✕/!/✓ 語意色）、標題列 accent bar；深淺色皆保留
- [x] 修「向量檢索沒真正發揮」：文字輸入改為先以原文查向量（舊版拿爬完全文比對，
      永遠過不了門檻）；門檻 0.88→0.75（實測校準，見第 3 節）；回應加 cached/cache_layer
      欄位＋雙前端顯示命中層；實測改寫版謠言命中 vector 層（6s、零 AI 點數）
- [x] 自主掃描優化第二輪（2026-07-12）：修「文字輸入分析對象被爬到的網頁偷換」
      （AI 一律分析使用者原文，爬到的頁面降級 similar_news；含 mock 回歸測試）；
      news_fetcher print 外部文字 cp950 崩潰 → _print 安全輸出；TaskStore 修剪(500筆)；
      /api/analyze 輸入驗證；README 全面更新
- [x] 批次查證腳本 batch_verify_pending.py（抓 RSS + 清 PENDING、CGU 預算護欄、
      預設關 web_search、零進展自動停）；跑完：熱門 63 筆 PENDING 歸零
      （MISINFO 30/SAFE 13/SCAM 8/UNVERIFIABLE 12）、知識庫 236 筆(200 帶向量)、
      三輪批次總花費 $0.127（CGU $20 額度）
- [x] 修 retry 空轉三連 bug：內容不足標 UNVERIFIABLE 終態（不再無限重試）；
      AI 暫時失敗與內容不足分開處理；`.in_([...,None])` 比不中 SQL NULL
      → 15 筆 NULL 記錄對 retry 隱形，改 or_(is_(None), in_([...]))
- [x] 前端整合決策：React 為唯一主介面（start.bat/start.sh 只開後端+React）；
      查核儀降級為離線備援（雙擊 = 純離線模式；_run_detector.bat = 接後端模式）
- [x] 文件一致性大掃描（2026-07-12）：根 README 全面重寫（原本還在講 factcheck_system
      路徑/PG+Redis 部署/0.88 門檻、結構樹有不存在的目錄）＋ CI/評測徽章；
      SCHEMA.md 修 768→1536 維、快取流程圖、UNVERIFIABLE 狀態、單寫者注意；
      前端 README 補 Knowledge/主題/token；React 補 UNVERIFIABLE 樣式（原誤顯示「待分析」）

## 9. 標記規則（重要，勿退回舊邏輯）
- **只有「確定不實」才標 MISINFO**：Cofacts 文章需有 `RUMOR` 回覆；MyGoPen/TFC
  標題需帶【錯誤/誤導/謠言/不實/易誤解/假】。其餘一律 `PENDING`（未查證），不要因為
  「來自查核網站」就整批標成假訊息（這是先前的 bug）。
- **主流媒體「查核報導」判定對象是被查核的主張，不是報導本身**（2026-07 修的 bug：
  同一 SIM 卡謠言，ETtoday 報導被標 MISINFO、華視報導被標 SAFE）。三道防線：
  ① `_title_indicates_debunk()`：標題同時含查核語境詞(查核/闢謠/澄清/網傳…)＋不實判定詞
  (不實/假的/過度誇大/打臉…) → 確定性標 MISINFO（可覆寫 AI 誤標的 SAFE，零 AI 成本）；
  ② AI 分析新聞時帶 `_NEWS_ANALYSIS_GUIDANCE` 補充指示（判主張不判報導）；
  ③ 既有資料修復：`scripts/fix_factcheck_labels.py`（冪等、支援 --dry-run，
  同時清 RSS 殘留的 &nbsp; 等 HTML entities；`_strip_html` 已改為會解 entities）。
- `_is_real_claim()`：純網址 / 無中文 / 標籤雲 / 太短 → 不索引進 knowledge_base。
- **來源分級三條規則**（共識 §9、FR-16／FR-17；負責人明確要求：還沒被查證的東西不能當來源，那是髒資料）：
  ① **Tier 定義**（`app/utils/source_tier.py`）：Tier 1「查核機構」= TFC、MyGoPen、`*.gov.tw`、WHO、CDC，以及**有 RUMOR／NOT_RUMOR
  回覆**的 Cofacts 文章；Tier 2「媒體查核報導」= 其他網域但標題命中 `_title_indicates_debunk`；Tier 3「相關討論（未查證）」= 其餘
  （含求證平台上還沒人回覆的貼文、Google News 轉址、社群平台）。網域一律精確尾綴比對（`gov.tw.evil.com` 是 Tier 3）。
  ② **只有 Tier 1／2 能顯示為「查核來源」**（結果頁、Threads 回覆、分享文案、知識庫頁皆同）；Tier 3 放 `related_discussions`。
  沒有任何 Tier 1／2 來源 → 顯示「尚無查核機構證實」，而且**不給綠燈**。
  ③ **知識庫寫入門檻**（`pandas_store.compute_write_gate`，雲端版共用）：`verified=true` 的條件是至少一個通過 `url_validator` 的
  Tier 1／2 來源，或確定性標記（`label_source` 為 rule／gold／admin）；否則以 `verified=false` 保存——不參與向量命中、不出現在知識庫頁。
- **紅黃綠燈號只有一個權威**：`app/utils/verdict.py` 的 `frame_of()`（8 列規則表寫在該檔開頭）。AI 的系統 prompt 也要求
  `sources` 只列已做出判定的來源、找不到就回 `[]`（FR-19，`ai_service.SYSTEM_PROMPT_V41`）。

## 10. 查證紀錄儲存 & 是否需要登入

| 資料 | 本機（`STORAGE_BACKEND=local`） | 雲端（Supabase） | 說明 |
|------|------|------|------|
| 查證任務＝結果頁 `/r/{id}` | `tasks.parquet` | `tasks` 表 | ✅ 持久、匿名；上限 5,000 筆，只修剪已結束的任務；知道網址的人都能看（分享用） |
| AI 判定快取（知識庫） | `knowledge_base.parquet` | `knowledge_base` 表（pgvector） | ✅ 持久，**全站共用、匿名**（非個人歷史） |
| 熱門牆 | `factcheck.db`（SQLite） | `fact_check_records` 表 | ✅ 持久 |
| 每日 AI 次數 | `factcheck.db` 的 `ai_usage_daily` | `ai_usage_daily` 表 | ✅ 重啟不歸零 |
| 管理者覆寫／使用者回饋 | `admin_overrides.parquet`／`user_feedback.parquet` | 同名資料表 | ✅ 持久 |
| 個人查證歷史（首頁「最近查證」） | 瀏覽器 `localStorage`（key `fcc_history_v1`） | 同左 | 只存在那台瀏覽器、沒有伺服器副本；最多 50 筆、首頁顯示最近 5 筆（`src/lib/history.js`） |
| Threads 機器人狀態 | `data/threads_*` 本機檔案 | 不上雲 | 見第 11 節 |
| 每 IP 限速計數 | 行程內記憶體 | 同左 | 重啟歸零（守預算的是每日 AI 次數） |

- **沒有使用者帳號 / 登入系統**，也不做（共識 §2；過度設計、牽涉帳密安全）。「重整後還看得到自己查過什麼」已用 `localStorage` 解決；
  `/history` 全頁是 P2、未排（票 S-14）。只有要「跨裝置看個人歷史」才需要會員系統。

## 11. Threads 查核機器人（延伸功能，預設關；目前 demo 用模擬模式）

**功能**：使用者在 Threads 上「回覆一則可疑貼文並 @機器人」（或直接 @機器人貼可疑文字）→ 機器人讀原貼文 → 走與網站相同的
三層快取＋AI 管線 → 回覆燈號＋摘要＋查核來源（只列 Tier 1／2，沒有就寫「尚無查核機構證實」）＋結果頁連結 `{PUBLIC_BASE_URL}/r/{id}`
＋「AI 自動判讀，請自行查證。」（≤500 字，模板在 `threads_reply.py`）。機器人帳號：`BOT_HANDLE=factcheck_tw_bot`。

**三種模式**：`THREADS_MODE=off | live | sim`（程式一律讀 `settings.threads_mode_effective`；舊的布林開關鍵已被它取代）。
- `off`（預設；**雲端固定 off**）：排程不啟動，`POST /api/threads/poll` 回 `threads_disabled`。
- `sim`（**進度報告與 demo 影片用的就是這個**）：`FakeThreadsService` 不打 Threads API、不需要 token——讀 `data/threads_sim/mentions.json`
  （格式範例 `scripts/threads_sim_mentions.example.json`）、回覆寫到 `data/threads_sim/replies.jsonl`。
  `test_threads_bot.py --reset-sim` 會清模擬紀錄，並用 `scripts/threads_sim_seed.json` 以 `label_source="gold"` 預熱知識庫，
  poll 時 L1 hash 命中、不呼叫 AI、斷網也能回覆。
- `live`：真的讀 mentions 並回覆，**排在進度報告之後**（第 8 節）。需要 Meta App（Threads use case）的四個權限：
  `threads_basic`、`threads_content_publish`、`threads_manage_replies`、`threads_manage_mentions`。
  通過 **Meta App Review（＋企業驗證）** 之前是開發模式：只收得到被加為 Threads Tester 的帳號的提及，不能公開給陌生人用。
  token：`scripts/threads_auth.py`（需 `THREADS_APP_ID`／`THREADS_APP_SECRET`／`PUBLIC_BASE_URL`；授權後導回網站的 `/oauth/callback` 顯示 code）
  → 寫出 `data/threads_token.json`（60 天，`--refresh` 續期；存在時優先於 `.env` 的 `THREADS_ACCESS_TOKEN`／`THREADS_USER_ID`）。
  驗證：`test_threads_bot.py --live`（只驗憑證）→ `--poll`（會真的回覆貼文、花額度）。

**只在負責人的電腦上跑，不上雲**：狀態都是本機檔案——`data/threads_state.json`（已回覆 id／游標／每日計數）、`data/threads_replies.jsonl`
（回覆紀錄）、`data/threads_token.json`、`data/threads_sim/`、`data/threads_poll.lock`，全部 gitignored。雲端硬碟是暫時的，重啟就忘記
回過誰；雲端和本機同時開 live 會重複回覆同一則貼文。

**端點**：`GET /api/threads/status`、`GET /api/threads/replies`（公開唯讀、不含 token）；`POST /api/threads/poll`（需 `X-Admin-Token`；
202 背景執行，已有一輪在跑回 409）。排程間隔 `THREADS_POLL_MINUTES`（預設 5）；上限 `THREADS_MAX_REPLIES_PER_POLL=5`、
`THREADS_MAX_REPLIES_PER_DAY=50`。

**防呆設計（改 code 前先看 `app/workers/threads_bot.py` 檔頭的 docstring）**：回覆成功後先原子寫 state 再寫 jsonl，不重複回；
不回機器人自己的貼文；只有圖片／影片、讀不到、太短 → 回固定文案、不經 AI；**AI 不可用（fallback）時不回覆、不標記**，下輪自動補回；
token 不進 log（`redact_token`）。Threads API 端點如有改版只需改 `threads_service.py`
（依 2026-01 官方文件：https://developers.facebook.com/docs/threads）。

---

## 12. 雲端部署（Render + Supabase + Vercel）

```
瀏覽器 → https://fakenewsverify.vercel.app（Vercel：React 靜態檔）
           └─ /api/* 由 vercel.json rewrite 同源代理 → Render 免費 web service（FastAPI，render.yaml）
                                                         ├─ Supabase Postgres + pgvector（資料）
                                                         └─ CGU AIR 閘道（AI / embedding）
GitHub Actions keepalive（每 10 分鐘）→ Render /health + /api/knowledge/stats
```

- **金鑰只存在兩個地方**：本機 `code/backend/.env` 與 Render 後台的 Environment 頁
  （`CGU_API_KEY`、`EMBED_API_KEY`、`SUPABASE_DB_URL`、`ADMIN_TOKEN`）。repo 是公開的，`render.yaml` 只有鍵名。
  Supabase 只當資料庫用；不把 AI 金鑰放在 Supabase。
- **操作手冊**：`docs/rebuild/runbook_cloud_deploy.md`（負責人 Part A、驗證 Part B、免費方案限制、退回本機 + tunnel 的方法）。
- **確認雲端真的接上資料庫**：`/health` 的 `"storage_backend":"supabase"`。`SUPABASE_DB_URL` 沒設時後端會
  默默退回暫時硬碟上的本機檔案（看起來正常，但主機一休眠資料就消失）。
- **免費方案行為**：Render 15 分鐘沒流量休眠、喚醒約 1 分鐘（前端橫幅會自動重試）；硬碟是暫時的；
  Supabase 免費專案 7 天沒活動會被暫停（keepalive 會讀資料庫）。
- **上線護欄數值寫在 `render.yaml`**（後台手動改的值，下次 Blueprint 同步會被檔案蓋回去）：
  `DAILY_AI_CALL_CAP=300`、`RATE_LIMIT_PER_MINUTE=30`、`RATE_LIMIT_PER_HOUR=200`；用量看 `/health.daily_ai_calls`。
- **雲端刻意關閉**：`ENABLE_SCHEDULER=false`、`USE_WEB_SEARCH=false`、`THREADS_MODE=off`
  （Threads 機器人的狀態檔還是本機檔案，雲端重啟會忘記回過誰 → 只在本機跑）。
- 只有 `code/backend` 底下的變更會觸發 Render 自動部署（`rootDir`）。
- Render 出問題時的退路：負責人電腦 + cloudflared tunnel，見 `docs/rebuild/runbook_tunnel.md` 與雲端 runbook 的 C2。

---

*提醒：改完任何東西，回來更新本檔對應段落（特別是第 2、6、8、9、12 段）。*
