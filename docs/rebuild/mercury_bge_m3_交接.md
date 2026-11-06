# 交接：向量改用 Mercury 的 bge-m3（票 B-52，2026-11-05）

給在**負責人電腦**上執行的 Claude Code。開工前先讀 `AGENTS.md`、`CLAUDE.md`（第 2、3、7 節），以及票 B-48、B-49、O-38、B-52。
分支：`claude/github-project-relevance-gunvht`。推到 `main` 就是上線，要等負責人說「推」。

## 1. 發生了什麼

- 2026-11-03 起學校關閉舊閘道（`https://air.cgu.edu.tw/cgullmapi/v1`）的 embedding（DEF-13），語意比對停用，
  網站改走關鍵字比對備援（B-48），查核同步照常寫入、向量待補（B-49）。
- 2026-11-05 學校說「向量回來了」，**是新的服務 Mercury**：`https://air.cgu.edu.tw/mercuryapi/v1`，OpenAI 相容。
  負責人提供的截圖與範例：
  - 向量模型**只有 `bge-m3`**（`/v1/embeddings`）。沒有 `text-embedding-3-small`。
  - bge-m3 屬於「本地模型」：長庚自己的機器提供，**免費、不計入額度、不受每分鐘次數限制**；用 Mercury 的金鑰呼叫。
  - Mercury 也有 `gpt-5.6-luna` 等判讀模型。判讀目前走舊閘道仍正常，**這次不動判讀**。
  - 範例：`OpenAI(base_url="https://air.cgu.edu.tw/mercuryapi/v1", api_key=os.environ["MERCURY_API_KEY"])`、
    `client.embeddings.create(model="bge-m3", input=[...])`。
- 同日正式站 `factcheck-sync` 的 embedding 由 404 變成 401（Render 上還留著舊的 `EMBED_API_KEY`）。

## 2. 為什麼不能只換網址

- 知識庫（Supabase `knowledge_base.content_vector`）存的是 `text-embedding-3-small` 的 **1536 維**向量；bge-m3 是 **1024 維**（先實測確認），
  兩種模型的向量不能互相比，**全部要用 bge-m3 重算**（約 1.9 萬筆；`factcheck_batch` 列＋其他已證實列）。
- 1536 寫死在：`app/config.py` 的 `VECTOR_DIMENSION`、`app/services/pg_store.py` 的 `VECTOR_DIM` 與建表的 `vector(1536)`、
  `_vec_literal` 的維度檢查、`pandas_task_processor._stored_vector`、本機 `pandas_store` 的同維度比對、`scripts/reembed_vectors.py`。
- 相似度門檻 `SIMILARITY_THRESHOLD=0.75` 是用 text-embedding-3-small 實測校準的；證據信心的 0.65、相似查證的 0.60、
  話術差距 0.10 與 `data/claim_prototypes.npz`（1536 維）也是。**換模型要重新量，不能沿用**（CLAUDE.md 第 3 節）。

## 3. 要做的事（照順序；每一步做完跟負責人回報）

**步驟 0：確認金鑰與維度（只讀，免費）**
- 請負責人把 Mercury 金鑰自己貼進 `code/backend/.env`（**不要**請他貼到聊天，也不要讀或印出 `.env`）。
  先試現有的 `CGU_API_KEY` 能不能直接呼叫 Mercury（截圖寫「用同一把金鑰」）；能的話仍只要一把金鑰。
- 跑 `scripts/mercury_check.py`（只讀）確認 bge-m3 的維度與狀態碼。

**步驟 1：程式（離線測試全過才 commit，不推 main）**
1. 向量維度改成由 `settings.VECTOR_DIMENSION` 決定，所有寫死 1536 的地方改讀設定；預設值暫時保留 1536，
   上線時由 `render.yaml` 設 1024，這樣測試與舊資料不會一次全壞。
2. 新增遷移腳本（預設 dry-run，`--apply` 要負責人同意）：Postgres 把舊欄位改名保留
   （例：`content_vector` → `content_vector_te3s`），新增 `content_vector vector(1024)`。**舊向量留著，可以退回**。
   先查 Supabase 免費方案的容量（新欄位約 80 MB）；不夠就先跟負責人說，再決定刪不刪舊欄位。
3. `scripts/reembed_vectors.py` 支援 bge-m3：批次送（每次多筆）、可中斷續跑、只補缺的、印出筆數；
   本機 Parquet 與 Supabase 都支援（`--target local|cloud|both`），預設 dry-run。
4. `scripts/rotate_cgu_key.py` 現在會清空 `EMBED_API_KEY`：如果 Mercury 要另一把金鑰，改成不要清空（O-38 有寫）。
5. `pytest tests -q` 全過；`RUN_PG_TESTS=1` 的 Postgres 契約測試也要改到 1024 維並通過。

**步驟 2：校準（免費，不寫正式資料庫）**
- 用 bge-m3 重新量：
  - 改寫句命中帶：`docs/test/pf2_paraphrases.csv` 的改寫句對知識庫原文；
  - 噪音帶：不同謠言之間、評測題的安全訊息（`data/eval_set.csv` 的 SAFE）對知識庫最近鄰；
  - 參考 2026-07 校準 0.75 的方法：門檻要落在噪音帶之上、改寫帶之下。
- 用 `scripts/evidence_confidence_study.py` 以 bge-m3 重產話術原型（新的 `claim_prototypes` 檔，維度 1024），重估 0.65／0.60／0.10。
- 報告寫進 `docs/test/results/bge_m3_calibration_2026-11-05.md`（只放數字、網址、雜湊，**不放訊息原文**）。
  **不要為了讓 PF-2 過關而挑門檻**；把建議的新數字給負責人看，負責人同意才往下。

**步驟 3：重算正式資料庫的向量（負責人同意後）**
- 先 dry-run 印出要動的欄位與筆數 → 負責人同意 → `--apply` 遷移 → 用 bge-m3 重算全部已證實列。
- 這段時間網站照常運作：沒有向量時本來就會走關鍵字比對。

**步驟 4：上線（負責人說「推」才做）**
- `render.yaml`：`EMBED_RELAY_URL=https://air.cgu.edu.tw/mercuryapi/v1`、`EMBED_MODEL=bge-m3`、`VECTOR_DIMENSION=1024`、
  `SIMILARITY_THRESHOLD=<步驟 2 的新值>`（證據信心的數字若改成設定也一起放）。
- Render 後台的 `EMBED_API_KEY`：改成 Mercury 金鑰（或刪掉，如果 `CGU_API_KEY` 就能用 Mercury）。**一次只給負責人一步**。
- 驗證：`/api/health` 的 `embedding.ok` 是 true；拿一則知識庫裡有的謠言改寫句去查，命中 `vector` 層；手動觸發一次 `factcheck-sync` 轉綠。

**步驟 5：文件（同一次工作改完）**
- `CLAUDE.md`（第 2 節 AI 引擎表、第 3 節門檻與校準、現況）、`AGENTS.md`（「CGU 是唯一的 AI」那段補上 Mercury）、
  `docs/test/TP-FNV-2026-01.md` 與短版報告書（DEF-13 的處理；舊紀錄保持當時的樣子，加新的一筆）、票 B-52／O-38 的狀態、`.env.example`。

## 4. 規矩提醒

- 跟負責人說話用繁體中文；給他的指令要能在 PowerShell 5.1 跑；後台操作一次一步。
- 金鑰只存在 `.env`、Render、GitHub secrets；聊天、commit、log 只寫鍵名。
- 會寫正式資料庫的腳本預設 dry-run，`--apply` 前問負責人。研究與校準的報告不放訊息原文。
- commit 訊息用中文，說明為什麼改，最後加 `Co-Authored-By`。
