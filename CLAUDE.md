# CLAUDE.md — 給 Claude Code 的專案說明

> **這份檔案是給 AI 助理（Claude Code）看的專案地圖。**
> **⚠️ 重要規則：每次對專案做出有意義的變更（新功能、改架構、換 API、調設定），都要同步更新這份檔案。**
> 讓任何一台機器上的 Claude Code 打開專案就能快速進入狀況。

最後更新重點：新增 **pytest 單元測試（tests/，29 個）+ GitHub Actions CI**；React 前端現代簡約化
（token 精修＋幾何記號取代 emoji，深淺色保留）。先前：Threads 查核機器人（第 11 節）、
修查核報導「同謠言兩種標籤」bug（第 9 節三道防線）、start.bat pip 修復、全專案優化、多 provider、評測 96%。

> ✅ **已恢復（2026-07-11）**：已切換 `AI_PROVIDER=cgu`（`CGU_API_KEY` 與 embedding 同一把 CGU 金鑰），
> 真 AI 分析恢復正常（實測 SCAM 判定 14s、信心 0.95）。**注意 CGU 是獨立 $20 預算**，用量可查 `/v1/me/usage`。
> myai168 仍然額度用盡＋`gpt-5-mini` 下架：備援順序 cgu→openai→claude 中，後兩個目前打了也會失敗（無害，只是 log 有錯誤）。
> myai168 儲值後可把 `AI_PROVIDER` 切回 `openai`。排查手冊見第 2 節「🚨 AI 全部壞掉時的排查與恢復」。

---

## 1. 這個專案是什麼

**全民查證公社 — AI 假訊息與詐騙查證系統**（學生專題 / 論文）。
使用者貼上文字 / 網址 / 圖片 / 影片，系統用 AI 判定是 **詐騙(SCAM) / 假訊息(MISINFO) / 安全(SAFE)**，附上佐證來源。
另有「今日熱門」自動抓取查核新聞、三層快取、向量檢索。

- 前端：**兩個並存、同一深色查核儀設計**——① React 19 + Vite + Tailwind（`code/frontend`，功能完整、接真後端）；
  ② 單檔 HTML 查核儀（根目錄 `fake-news-detector.html`，自包含可離線、靜態伺服器 8090）
- 後端：FastAPI + Uvicorn（`code/backend`，已從 `factcheck_system` 子目錄攤平）
- 資料：SQLite（熱門記錄）+ Parquet（三層快取知識庫）

---

## 2. AI 引擎（重要！支援多個學校 AI provider，不直連官方）

目前保留原本 myai168 方案，並新增 CGU AIR Gateway 選項。用 `.env` 的 `AI_PROVIDER` 選擇：

- `AI_PROVIDER=openai`：myai168 OpenAI Responses API（原本方案）
- `AI_PROVIDER=claude`：myai168 Anthropic Messages API（原本方案）
- `AI_PROVIDER=cgu`：CGU AIR Gateway OpenAI-compatible Responses API（新增方案）

| 用途 | 閘道 base_url | 模型 | .env 變數 |
|------|--------------|------|-----------|
| myai168 OpenAI 分析 | `https://www.myai168.com/cgu/api/openai/v1` | `gpt-5-mini` | `MYAI_API_KEY` / `OPENAI_RELAY_URL` / `OPENAI_MODEL` |
| myai168 Claude 分析 | `https://www.myai168.com/cgu/api/anthropic/v1` | `claude-opus-4-8` | `MYAI_API_KEY` / `CLAUDE_RELAY_URL` / `CLAUDE_MODEL` |
| CGU AIR 分析 | `https://air.cgu.edu.tw/cgullmapi/v1` | `gpt-5.4-mini` | `CGU_API_KEY` / `CGU_BASE_URL` / `CGU_MODEL` |
| 向量 embedding | `https://air.cgu.edu.tw/cgullmapi/v1` | `text-embedding-3-small`(1536維) | `EMBED_RELAY_URL` / `EMBED_API_KEY`，空時退用 `CGU_API_KEY` |
| 影片語音轉文字 | myai168 或 CGU AIR `/audio/transcriptions` | `whisper-1` / `gpt-4o-mini-transcribe` | `STT_MODEL` / `CGU_STT_MODEL` |

- **多 provider fallback**：`AI_PROVIDER=cgu` 時順序為 `cgu -> openai -> claude`；`openai` 時為 `openai -> claude -> cgu`；`claude` 時為 `claude -> openai -> cgu`。只有設定好 key/base 的 provider 會被加入。實作在 `app/services/ai_service.py` 的 `_run_analysis()`。
- **金鑰命名刻意避開標準名**：用 `MYAI_API_KEY`、`CLAUDE_RELAY_URL`、`OPENAI_RELAY_URL`，**不要**用 `OPENAI_API_KEY` / `ANTHROPIC_BASE_URL`，否則會被系統既有的同名環境變數覆寫（pydantic 環境變數優先序高於 .env）。
- myai168 與 CGU 是**兩個不同的閘道、不同金鑰、不同額度池**。CGU 有 `/v1/me/usage` 可查用量（$20 OpenAI 預算）。CGU 教學頁：`https://air.cgu.edu.tw/workspace4/LLMAPI/api_call.html`。

### 💰 點數/額度警告（最常踩雷）
- 學校點數**有限**。`api_anthropic`(Claude Opus) 每次 ~135–1143 點；`api_openai`(gpt-5) 便宜約 10 倍。
- `gpt-5` 是**推理模型**，預設思考很久（~20s/次、貴）。用 `gpt-5-mini` + `OPENAI_REASONING_EFFORT=minimal`（~6s/次、便宜）。
- `web_search` 工具讓每次呼叫**貴 3–7 倍**。由 `USE_WEB_SEARCH` 控制；高量任務（評測、排程）請關掉。
- ⚠️ **minimal 推理與 web_search 不相容**：gpt-5-mini 在 `OPENAI_REASONING_EFFORT=minimal` 下帶 web_search 會 HTTP 400。
  `ai_service._responses_analyze` 已自動在 minimal 時跳過 web_search（openai/cgu 共用此引擎），否則每次都失敗後 fallback 到貴 10 倍的 claude。
- ⚠️ **myai168 anthropic 中繼不支援 hosted web_search**：claude 帶 web_search 會 HTTP 400 (unsupported_tool)。
  `_claude_analyze` 已一律不帶 web_search；高量任務建議 `USE_WEB_SEARCH=false`。
- ⚠️ **點數會用盡**：claude 402 `insufficient_credits`(需儲值)、openai 400 `no_pricing_info`(模型下架/換 `OPENAI_MODEL`)
  代表 myai168 額度或模型出問題；此時 AI 回「AI 分析暫時無法使用」，前端(查核儀/React)會 fallback。可考慮改 `AI_PROVIDER=cgu`。
- **自動抓新聞排程預設關閉**（`ENABLE_SCHEDULER=false`），避免背景持續燒點數。要 24h 自動查證才開。

### 🚨 AI 全部壞掉時的排查與恢復（2026-07 實際遇到，下一個接手請照這做）
**症狀**：檢測/評測回「AI 分析暫時無法使用」(risk_type=SAFE、confidence=0)；後端 log 出現：
- `[AI] claude HTTP 402: insufficient_credits「You need to top up!」` → **myai168 點數燒完**（claude/openai 共用 `MYAI_API_KEY` 同一額度池）
- `[AI] openai HTTP 400: no_pricing_info「Please use other models!」` → **`OPENAI_MODEL`(gpt-5-mini) 在網關下架/沒定價**

**恢復步驟**（擇一，改 `code/backend/.env` 後**重啟後端**才生效）：
1. **myai168 儲值** → claude/openai 立即恢復（同一額度池）。
2. **換 openai 模型**：把 `OPENAI_MODEL=gpt-5-mini` 改成網關還有定價的型號（去 myai168 後台查可用清單）。
3. **改用 CGU 網關**：`AI_PROVIDER=cgu`（獨立 $20 預算、不同金鑰池；用量查詢見本節上方）。

**驗證**（低成本，會印出 risk_type 或 HTTP 錯誤碼）：
```powershell
cd code\backend
.\venv\Scripts\python scripts\test_ai_provider.py --provider openai   # 或 cgu / claude
```
**前端不會因此崩**：查核儀 → fallback 前端啟發式並標「離線」；React → 顯示「分析失敗」卡片；
熱門/資料庫走 `/api/trending`、`/api/knowledge` 讀快取、**不呼叫 AI、不受影響**。
> 實作細節：AI 掛掉時 `/api/analyze/sync` 仍回 **HTTP 200** 的 fallback JSON（SAFE、confidence 0、
> summary 以「AI 分析暫時無法使用」開頭）。查核儀 `detectViaBackend` 與 React `normalizeAiResult`
> 都是靠這個 summary 前綴辨識，**改 fallback 字樣時三處要一起改**（`ai_service._default_fallback_result`）。

---

## 3. 三層快取（省最貴的 AI 呼叫）

```
文字輸入 → L0(skip) → L1: 內容 Hash → L2: 向量(以「使用者原文」比對，先於爬蟲!) → 爬蟲 → L3: AI
網址輸入 → L0: URL 快取 → L1: Hash → 爬蟲 → L2: 向量(以爬到的內文比對) → L3: AI
                                                          結果回填 knowledge_base ◄┘
```
- 實作：`app/workers/pandas_task_processor.py`（主流程）+ `app/services/pandas_store.py`（Parquet 存取）。
- **文字輸入的向量層在爬蟲之前、比對對象是使用者原文**（2026-07 修正：舊版拿爬完的
  網頁全文比對，長文對短句過不了門檻，向量層形同虛設——勿改回）。命中時連關鍵字
  搜尋與 AI 都省下（實測 6s vs 未命中 11-15s+AI 點數）。
- Layer 2 門檻 `SIMILARITY_THRESHOLD=0.75`：**實測校準**（text-embedding-3-small、繁中）
  改寫版同一謠言 0.79~0.82、不同支謠言 ≤0.68、不同主題 ≤0.52；舊值 0.88 會把改寫版全擋掉。
  換 embedding 模型要重新量測。改門檻改 config，`find_similar_by_vector` 已讀 `settings`。
- 回應帶 `cached` / `cache_layer`（url/hash/vector）：React 顯示「快取·語意相似」chip、
  查核儀在依據列顯示命中層——demo 三層快取的實據。
- 沒設 `EMBED_API_KEY` 時 Layer 2 自動停用，URL/Hash 仍正常。

---

## 4. 主要檔案地圖

```
code/backend/
├── app/
│   ├── main.py                 FastAPI 入口 + 排程器(opt-in)
│   ├── config.py               所有設定(pydantic Settings，讀 .env；extra=ignore)
│   ├── database_sql.py         SQLite engine（熱門記錄用）
│   ├── api/analyze.py          /api/analyze/{text,url,sync,image,task}
│   ├── api/trending.py         /api/trending(熱門列表) /refresh
│   ├── api/knowledge.py        /api/knowledge(瀏覽/搜尋快取) /stats
│   ├── api/admin.py            /api/admin 管理者覆寫 AI 判定（寫 AuditStore）
│   ├── api/feedback.py         /api/feedback 使用者回饋（寫 AuditStore）
│   ├── api/threads.py          /api/threads/{status,poll} Threads 機器人狀態/手動觸發
│   ├── models/fact_check_record.py  SQLite 熱門記錄 model（唯一的 SQLAlchemy model）
│   ├── services/
│   │   ├── ai_service.py       ★多 provider AI(myai168 OpenAI/Claude + CGU AIR)、web_search、STT、embedding
│   │   ├── crawler.py          爬蟲 + 影片字幕/whisper 逐字稿（阻塞 IO 皆走 to_thread）
│   │   ├── pandas_store.py      三層快取 Parquet（向量搜尋已 numpy 矩陣化）
│   │   ├── task_store.py        非同步任務狀態 Parquet
│   │   ├── audit_store.py       覆寫/回饋紀錄 Parquet
│   │   ├── cache_service.py     內容 SHA-256 hash
│   │   ├── vector_service.py    embedding 包裝（實際搜尋在 pandas_store）
│   │   ├── news_fetcher.py      熱門新聞兩階段流程
│   │   ├── search_service.py    RSS/Cofacts 聚合
│   │   └── threads_service.py   Threads Graph API 客戶端 + 回覆格式化(500字上限)
│   ├── utils/url_validator.py  過濾 AI 幻覺出的死連結
│   └── workers/
│       ├── pandas_task_processor.py  ★三層快取主流程（AI/embedding 走 to_thread 不卡 event loop）
│       └── threads_bot.py       Threads 機器人輪詢（mentions→分析→回覆，已回覆 id 存 data/threads_state.json）
├── scripts/
│   ├── evaluate.py             ★評測(混淆矩陣/accuracy/FP/FN/--seed-db/--report-only)
│   ├── check_db.py             看資料庫內容
│   ├── test_ai_provider.py     低成本測試 AI provider
│   ├── test_threads_bot.py     Threads 機器人乾跑/憑證驗證(--live)/真跑一輪(--poll)
│   ├── fix_factcheck_labels.py 一次性資料修復(查核報導錯標+HTML entities，冪等/--dry-run)
│   └── seed_data.py            灌範本
├── tests/                      ★pytest 單元測試(29 tests、離線零點數；CI 每次 push 自動跑)
│   ├── test_cache_and_store.py   hash/三層快取/任務儲存
│   ├── test_marking_rules.py     標記規則守門(第9節邏輯，防退回舊 bug)
│   ├── test_ai_service_contract.py  JSON解析/fallback字樣契約/紅黃綠框/Threads回覆500字
│   ├── test_api.py               API 冒煙(health/knowledge/threads status)
│   └── test_url_validator.py     幻覺連結過濾
├── data/
│   ├── factcheck.db            SQLite(熱門記錄)  [本機 runtime，未提交]
│   ├── knowledge_base.parquet  三層快取知識庫     [★已提交 178 筆 demo 種子；
│   │                            是 runtime 快取，用過後會顯示 modified→那些變動不用 commit]
│   ├── eval_set.csv            150 筆標註資料(50/50/50)
│   ├── tasks.parquet           非同步任務狀態      [runtime]
│   └── eval_report.csv / eval_binary.csv / eval_errors.csv  評測結果
├── .env                        ★真實金鑰(在 backend 根目錄)，已 gitignore，勿提交
├── requirements.txt  .env.example  README.md  Dockerfile  docker-compose.yml
└── venv/（本機建立，不進 git）
code/frontend/                  React + Vite + Tailwind（深色查核儀設計：index.css token / mockData RISK_STYLES / App.jsx）
fake-news-detector.html         ★單檔查核儀(根目錄)：設計token+環形儀表盤+掃描動畫+三視圖(檢測/熱門/資料庫)
                                熱門/資料庫接 /api/trending、/api/knowledge(離線 fallback 範例)；
                                檢測接 /api/analyze/sync(真 AI)，後端掛/AI 掛時 fallback 前端啟發式並標離線
start.bat / _run_detector.bat   一鍵啟動：後端 + 查核儀靜態伺服器(8090)；start.sh 為 Linux/mac 版
assets/                         PlantUML 圖 + confusion_matrix.png
└── 期末專題文件/                OOSE 期末繳交文件(詞彙表/使用案例圖/情節/活動圖/類別圖+README)
```

---

## 5. 常用指令

```powershell
# 一鍵啟動：後端 + 單檔查核儀(8090)（專案根目錄）
.\start.bat

# 後端（venv 在 code/backend/venv）
cd code\backend
.\venv\Scripts\python -m uvicorn app.main:app --reload --port 8000

# React 深色前端（單獨跑，靠 vite proxy /api→8000）
cd code\frontend
npm run dev    # http://localhost:5173

# 看資料庫內容
.\venv\Scripts\python scripts\check_db.py

# 評測（會呼叫 AI、花點數）
.\venv\Scripts\python scripts\evaluate.py --seed-db --delay 0
# 只重算報告（不呼叫 AI、零點數）
.\venv\Scripts\python scripts\evaluate.py --report-only

# 低成本測試目前 AI provider
.\venv\Scripts\python scripts\test_ai_provider.py --provider cgu

# Threads 機器人：乾跑(免token) / 驗憑證 / 真跑一輪(會回覆、花點數)
.\venv\Scripts\python scripts\test_threads_bot.py
.\venv\Scripts\python scripts\test_threads_bot.py --live
.\venv\Scripts\python scripts\test_threads_bot.py --poll

# 單元測試（29 tests、離線、零點數；GitHub Actions 每次 push 也會自動跑）
.\venv\Scripts\python -m pytest tests -q
```

API 文件：http://localhost:8000/docs

---

## 6. 評測現況（論文數據）

- 資料集 `data/eval_set.csv`：150 筆（SCAM/MISINFO/SAFE 各 50），含刻意設計的「像詐騙的合法官方訊息」當難題。
- 最新結果（gpt-5-mini）：**accuracy 96.0%、macro-F1 0.960**。
- 二分類偽陽性/偽陰性：**FN=0（從不漏判風險）、FP=5（誤報合法警示/政策）**。
- 錯誤多為「模型對詐騙字眼過度反應」，把反詐宣導、政府補助公告誤判成 SCAM。

---

## 7. 慣例與注意事項

- **Windows 主控台是 cp950**：`print()` **不要放 emoji / ✓✗**（會 `UnicodeEncodeError` 崩潰）。中文可以（Big5）。要輸出給人看的結果，寫成 UTF-8 檔再讀。
- **`requirements.txt` 只能放 ASCII**：pip 讀 requirements 用系統編碼（cp950），
  放中文註解會讓 `pip install -r` 直接 UnicodeDecodeError（start.bat 就炸在這，2026-07 踩過）。
  `.env` 可以有中文，因為 config 已指定 `env_file_encoding="utf-8"`。
- `.env` 已 gitignore（含真實金鑰）。改設定改 `.env`；範本改 `.env.example`。
  Settings 已設 `extra="ignore"`：.env 有多餘舊變數不會炸，但也**不會警告拼錯的變數名**。
- **async 端點內不要直接呼叫 requests / 檔案大 IO**：會卡死整個 event loop
  （AI 呼叫 timeout 150s）。照 `pandas_task_processor.py` 的做法包 `asyncio.to_thread`。
- runtime 檔（`*.db`、`*.parquet`）已 gitignore，不要提交。
- commit 訊息結尾加 `Co-Authored-By: <model> <noreply@anthropic.com>`。
- 大檔（如報告影片 895MB、plantuml jar）放雲端或 gitignore，不進 git（GitHub 單檔上限 100MB）。
- PostgreSQL/Redis 死碼已全數移除（2026-07）：不要再引用 `app/database.py`、PG models、
  pgvector 方法——它們不存在了；資料層就是 SQLite（熱門）+ Parquet（快取/任務/回饋）。

---

## 8. 待辦 / 進行中（更新時請維護這段）

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
- [x] 單元測試 + CI：tests/ 29 個 pytest（快取/標記規則/fallback契約/API冒煙/URL過濾，
      離線零點數）＋ .github/workflows/ci.yml（push/PR 自動跑，對應專題「測試驗證/品質保證」）
- [x] React 前端現代簡約化：token 精修（低對比邊框、主題感知陰影 --shadow-card/pop、
      柔和光暈）、裝飾 emoji 換幾何記號（✕/!/✓ 語意色）、標題列 accent bar；深淺色皆保留
- [x] 修「向量檢索沒真正發揮」：文字輸入改為先以原文查向量（舊版拿爬完全文比對，
      永遠過不了門檻）；門檻 0.88→0.75（實測校準，見第 3 節）；回應加 cached/cache_layer
      欄位＋雙前端顯示命中層；實測改寫版謠言命中 vector 層（6s、零 AI 點數）
- [ ] Threads 機器人 live 測試：待申請 Meta App + token（乾跑/端點已驗證）
- [ ] （選）擴充 eval_set 到 300 筆、做信心校準
- [ ] （選）前端加「評測數據」分頁顯示混淆矩陣/accuracy

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

## 10. 查證紀錄儲存 & 是否需要登入

| 資料 | 存在哪 | 是否持久 / 分使用者 |
|------|--------|---------------------|
| 使用者送出的查證（動態牆 posts） | 前端 React state（記憶體） | ❌ 重整就消失、不分使用者 |
| AI 判定結果（快取） | `knowledge_base.parquet` | ✅ 持久，但**全站共用、匿名**（非個人歷史） |
| 今日熱門 | `factcheck.db`（SQLite） | ✅ 持久 |
| 非同步任務狀態 | `tasks.parquet` | 暫時 |

- **目前沒有使用者帳號 / 登入系統**，也沒有「個人查證歷史」。這是公開查證工具的合理設計。
- **thesis 不建議加登入**（過度設計、牽涉帳密安全）。若要「重整後動態牆還在」→ 用瀏覽器
  `localStorage`（方案 A，不用登入、不用改後端）。只有要「跨裝置看個人歷史」才需要會員系統（方案 B）。

## 11. Threads 查核機器人（延伸功能，預設關）

**模式**：使用者在 Threads 上「回覆一則可疑貼文並 @機器人帳號」（或直接 @機器人貼可疑文字）→
機器人抓原貼文文字 → 走與 `/api/analyze/sync` 完全相同的三層快取+AI 管線 → 自動回覆
紅黃綠判定＋查核來源（≤500 字，AI 產出的幻覺連結已被 url_validator 過濾）。

**啟用步驟**：
1. Meta 開發者後台（developers.facebook.com）建立 App，use case 選 **Threads API**，
   綁定機器人用的 Threads 帳號，申請權限：`threads_basic`、`threads_content_publish`、
   `threads_read_replies`、`threads_manage_replies`（mentions 權限名以官方文件為準；
   開發模式用自己帳號測試**不用送審**，公開給其他人用才要 app review）。
2. 取得**長效 access token（60 天，要記得換）**與帳號 user id，填入 `.env`：
   `THREADS_ACCESS_TOKEN` / `THREADS_USER_ID`、`ENABLE_THREADS_BOT=true`，重啟後端。
3. 驗證：`venv\Scripts\python scripts\test_threads_bot.py --live`（驗憑證，零成本）→
   `POST /api/threads/poll` 手動跑一輪（會真的回覆貼文、花 AI 點數）。

**防呆設計（改code前先看）**：已回覆 id 存 `data/threads_state.json`（gitignored）不重複回；
不回機器人自己的貼文；**AI 額度用盡的 fallback 不回覆、不標記**（額度恢復後下輪自動補回）；
沒設 token 時排程與端點全部自動停用。Threads API 端點如有改版只需改 `threads_service.py`。
API 實作依 2026-01 官方文件：https://developers.facebook.com/docs/threads

---

*提醒：改完任何東西，回來更新本檔對應段落（特別是第 2、6、8、9 段）。*
