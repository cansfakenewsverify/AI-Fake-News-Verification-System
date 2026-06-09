# CLAUDE.md — 給 Claude Code 的專案說明

> **這份檔案是給 AI 助理（Claude Code）看的專案地圖。**
> **⚠️ 重要規則：每次對專案做出有意義的變更（新功能、改架構、換 API、調設定），都要同步更新這份檔案。**
> 讓任何一台機器上的 Claude Code 打開專案就能快速進入狀況。

最後更新重點：AI 引擎保留 myai168 OpenAI/Claude，新增 CGU AIR Gateway provider；embedding 走 CGU、評測 96%；
熱門/資料庫誤標已修（只在確定不實才標假訊息）、卡片風格統一（InfoCard）、knowledge_base 已提交 178 筆 demo 種子。

---

## 1. 這個專案是什麼

**全民查證公社 — AI 假訊息與詐騙查證系統**（學生專題 / 論文）。
使用者貼上文字 / 網址 / 圖片 / 影片，系統用 AI 判定是 **詐騙(SCAM) / 假訊息(MISINFO) / 安全(SAFE)**，附上佐證來源。
另有「今日熱門」自動抓取查核新聞、三層快取、向量檢索。

- 前端：React 19 + Vite + Tailwind CSS（`code/frontend`）
- 後端：FastAPI + Uvicorn（`code/backend/factcheck_system`）
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
- **自動抓新聞排程預設關閉**（`ENABLE_SCHEDULER=false`），避免背景持續燒點數。要 24h 自動查證才開。

---

## 3. 三層快取（省最貴的 AI 呼叫）

```
輸入 → Layer 0: URL 快取 → Layer 1: 內容 Hash → Layer 2: 向量(餘弦相似) → Layer 3: AI 分析
                                                                              │
                                                       結果回填 knowledge_base ◄┘
```
- 實作：`app/workers/pandas_task_processor.py`（主流程）+ `app/services/pandas_store.py`（Parquet 存取）。
- Layer 2 門檻 `SIMILARITY_THRESHOLD=0.88`（讓換句話說的相同謠言也命中）。改門檻要改 config，`find_similar_by_vector` 已讀 `settings`。
- 沒設 `EMBED_API_KEY` 時 Layer 2 自動停用，URL/Hash 仍正常。

---

## 4. 主要檔案地圖

```
code/backend/factcheck_system/
├── app/
│   ├── main.py                 FastAPI 入口 + 排程器(opt-in)
│   ├── config.py               所有設定(pydantic Settings，讀 .env)
│   ├── api/analyze.py          /api/analyze/{text,url,sync,image,task}
│   ├── api/trending.py         /api/trending(熱門列表) /refresh
│   ├── api/knowledge.py        /api/knowledge(瀏覽/搜尋快取) /stats
│   ├── services/
│   │   ├── ai_service.py       ★多 provider AI(myai168 OpenAI/Claude + CGU AIR)、web_search、STT、embedding
│   │   ├── crawler.py          爬蟲 + 影片字幕/whisper 逐字稿
│   │   ├── pandas_store.py      三層快取 Parquet
│   │   ├── news_fetcher.py      熱門新聞兩階段流程
│   │   └── search_service.py    RSS/Cofacts 聚合
│   └── workers/pandas_task_processor.py  ★三層快取主流程
├── scripts/
│   ├── evaluate.py             ★評測(混淆矩陣/accuracy/FP/FN/--seed-db/--report-only)
│   ├── check_db.py             看資料庫內容
│   └── seed_data.py            灌範本
├── data/
│   ├── factcheck.db            SQLite(熱門記錄)  [本機 runtime，未提交]
│   ├── knowledge_base.parquet  三層快取知識庫     [★已提交 178 筆 demo 種子；
│   │                            是 runtime 快取，用過後會顯示 modified→那些變動不用 commit]
│   ├── eval_set.csv            150 筆標註資料(50/50/50)
│   ├── tasks.parquet           非同步任務狀態      [runtime]
│   └── eval_report.csv / eval_binary.csv / eval_errors.csv  評測結果
├── .env                        ★真實金鑰(在 factcheck_system 根目錄)，已 gitignore，勿提交
code/frontend/                  React + Vite + Tailwind
assets/                         PlantUML 圖(usecase/sequence/activity) + confusion_matrix.png
```

---

## 5. 常用指令

```powershell
# 一鍵啟動前後端（專案根目錄）
.\start.bat

# 後端（venv 在 code/backend/factcheck_system/venv）
cd code\backend\factcheck_system
.\venv\Scripts\python -m uvicorn app.main:app --reload --port 8000

# 看資料庫內容
.\venv\Scripts\python scripts\check_db.py

# 評測（會呼叫 AI、花點數）
.\venv\Scripts\python scripts\evaluate.py --seed-db --delay 0
# 只重算報告（不呼叫 AI、零點數）
.\venv\Scripts\python scripts\evaluate.py --report-only

# 低成本測試目前 AI provider
.\venv\Scripts\python scripts\test_ai_provider.py --provider cgu
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
- `.env` 已 gitignore（含真實金鑰）。改設定改 `.env`；範本改 `.env.example`。
- runtime 檔（`*.db`、`*.parquet`）已 gitignore，不要提交。
- commit 訊息結尾加 `Co-Authored-By: <model> <noreply@anthropic.com>`。
- 大檔（如報告影片 895MB）放雲端，不進 git（GitHub 單檔上限 100MB）。

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
- [ ] （選）擴充 eval_set 到 300 筆、做信心校準
- [ ] （選）前端加「評測數據」分頁顯示混淆矩陣/accuracy

## 9. 標記規則（重要，勿退回舊邏輯）
- **只有「確定不實」才標 MISINFO**：Cofacts 文章需有 `RUMOR` 回覆；MyGoPen/TFC
  標題需帶【錯誤/誤導/謠言/不實/易誤解/假】。其餘一律 `PENDING`（未查證），不要因為
  「來自查核網站」就整批標成假訊息（這是先前的 bug）。
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

---

*提醒：改完任何東西，回來更新本檔對應段落（特別是第 2、6、8、9 段）。*
