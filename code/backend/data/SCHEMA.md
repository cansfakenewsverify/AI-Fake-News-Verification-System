# 資料庫 Schema

系統使用兩個並行的儲存層，本文件描述兩者的欄位定義。

---

## 1. `knowledge_base.parquet`（Parquet）— 三層快取知識庫

供 `pandas_task_processor` 使用，存放查詢過的內容與向量，加速後續相同/相似查詢。

### 欄位

| 欄位 | 型別 | 說明 |
|------|------|------|
| `id` | string (UUID) | 主鍵 |
| `data_type` | string | `URL` / `TEXT` / `IMAGE` / `VIDEO` |
| `source_url` | string \| None | 原始 URL（**Layer 0** 快取查詢用） |
| `raw_content` | string | 文字模式存**使用者原文**（與向量語意一致）；URL 模式存爬取後的文章內容 |
| `data_hash` | string | SHA-256（**Layer 1** 完全比對用，對原始輸入計算） |
| `content_vector` | list[float] (1536) | Embedding 向量（**Layer 2** 語義比對用；text-embedding-3-small） |
| `is_risk` | bool | 是否為風險訊息 |
| `risk_type` | string | `SCAM` / `MISINFO` / `SAFE` / `UNKNOWN` |
| `category` | string | 細分類，例：`Investment`、`Health_Rumor` |
| `confidence_score` | float | 0.0 – 1.0 |
| `summary` | string | AI 摘要 |
| `explanation` | string | 白話解釋 |
| `sources` | list[dict] | 參考來源 `[{title, url}, ...]` |
| `ai_analysis` | dict | 完整 AI 結果（含上述欄位） |
| `created_at` | datetime | 建立時間 |
| `last_accessed_at` | datetime | 最後一次命中快取的時間 |
| `hit_count` | int | 累計命中次數（不分時間；熱門頁「本站熱門查證」改用查證紀錄 `tasks.kb_id` 的時間衰減分數，見 `app/services/hot_claims.py`） |
| `label_source` | string | 判定來源：`ai`（AI 判讀）／`rule`（查核機構文章的確定性標記）／`gold`（評測題庫）／`admin`（管理者覆寫） |
| `origin` | string | 寫入途徑：`web`、`threads` 等查證來源；`factcheck_batch` = `scripts/ingest_factchecks.py` 批次入庫（`rollback` 以此撤回） |
| `verified` | bool | 已證實（有 Tier 1／2 來源或確定性標記）；只有 `true` 的列參與語意命中、出現在知識庫頁 |
| `source_tier` | int \| None | 來源中的最高等級（1 查核機構、2 媒體查核報導；只有 Tier 3 或沒有來源時為空） |

### 三層快取流程（文字輸入以使用者原文比對、不爬取；2026-09-22 加查核結果回補）

```
文字輸入 ──► Layer 1: data_hash 比對 ──► 命中？回傳（命中未證實列時先做「查核結果回補」）
                        │ miss
                        ▼
            Layer 2: 原文向量相似度比對（只比 verified 列，門檻 0.75 實測校準）──► 命中？回傳
                        │ miss
                        ▼
            Layer 3: AI 分析使用者原文，存入快取

網址輸入 ──► Layer 0: source_url 比對 ──► Layer 1: hash ──► 爬蟲 ──►
            Layer 2: 內文向量比對 ──► Layer 3: AI 分析，存入快取
```

**查核結果回補**：Layer 0／1 不過濾 `verified`，一字不差的重複查詢會拿到當初的結果。命中的是
`verified=false` 列時，先以該列的向量（沒有就以 `raw_content` 算一次）到向量層**只比對
`label_source` 為 rule／gold／admin 的列**；達門檻就改回那一筆（`cache_layer="vector"`）。
查核機構之後發布的結論（熱門牆抓取時以 `rule` 寫入）因此不會被舊的「尚無查核機構證實」擋住。

API 回應的 `cache_layer` 欄位（url / hash / vector / null）標示命中層。

---

## 2. `factcheck.db` / `fact_check_records`（SQLite）— 熱門趨勢資料

供 `news_fetcher` + `/api/trending` 使用，存放從查核機構 RSS（MyGoPen、台灣事實查核中心）與 Cofacts 抓回的記錄（Google News 轉址已於 2026-09 移除）。

### 欄位

| 欄位 | 型別 | 說明 |
|------|------|------|
| `id` | string (UUID) | 主鍵 |
| `source_url` | string | 文章 URL（unique） |
| `news_title` | string | 標題（從 RSS / 爬蟲取得） |
| `content` | text | 文章內容（最多 2000 字） |
| `ai_score` | float | AI 信心分數 |
| `ai_summary` | text | AI 摘要 |
| `risk_type` | string | `SCAM` / `MISINFO` / `SAFE` / `PENDING`(待查證) / `UNVERIFIABLE`(內容不足，終態不重試) / `UNKNOWN` |
| `category` | string | 細分類 |
| `is_trending` | bool | 是否為熱門記錄 |
| `created_at` | datetime | 建立時間 |
| `updated_at` | datetime | 最後更新時間 |

### 自動分類規則

```python
FACT_CHECK_SOURCES = {  # 標題帶不實標籤/Cofacts RUMOR 判定才 → MISINFO
    "mygopen.com", "tfc-taiwan.org.tw", "cofacts.tw",
}
SAFE_SOURCES = {        # → SAFE
    "cdc.gov.tw", "gov.tw",
}
# 主流媒體查核報導：標題同時含「查核語境詞 + 不實判定詞」→ MISINFO（確定性規則）
# 其他 URL → PENDING → 走 AI 分析（帶「判主張不判報導」指示）
# 內容太短/爬不到 → UNVERIFIABLE（終態，不再重試）
```

---

## 分類列表（`category`）

**SCAM（詐騙）**
- `Investment` 投資詐騙
- `Phishing` 釣魚連結
- `Impersonation` 假冒親友/公務員
- `E-Commerce` 網購/解除分期
- `Job` 求職詐騙
- `Romance` 愛情詐騙

**MISINFO（假訊息）**
- `Health_Rumor` 健康/食安謠言
- `Political_Rumor` 政治/政策謠言
- `Content_Farm` 內容農場/標題黨
- `Old_News` 舊聞重炒
- `Urban_Legend` 都市傳說
- `已查核假訊息` （RSS 來源自動分類）

**其他**
- `Safe` 安全且正確的資訊
- `官方衛教`、`官方資訊`
- `Irrelevant` 無關內容

---

## 工具

```powershell
# 一次檢視兩個資料庫
.\venv\Scripts\python scripts\check_db.py

# 灌入範例資料（測試用）
.\venv\Scripts\python scripts\seed_data.py
```

### 用 Python 讀取

```python
import pandas as pd
from app.database_sql import SessionLocal
from app.models.fact_check_record import FactCheckRecord

# Parquet 知識庫
df = pd.read_parquet("data/knowledge_base.parquet")
print(df[["risk_type", "category", "confidence_score", "summary"]])

# SQLite 熱門記錄
db = SessionLocal()
records = db.query(FactCheckRecord).order_by(FactCheckRecord.created_at.desc()).limit(20).all()
for r in records:
    print(r.risk_type, r.news_title)
db.close()
```

---

## 設計理由

| 為什麼 | 答案 |
|--------|------|
| 為什麼快取用 Parquet，趨勢用 SQLite？ | Parquet 適合大量向量 + numpy 批次運算；SQLite 適合結構化查詢 / 排序 |
| 為什麼不全部用 PostgreSQL + pgvector？ | 零安裝門檻，學生專題不用裝 Docker；資料量（數百~數千筆）遠未達需要專用向量資料庫的規模 |
| 為什麼 Embedding 用 1536 維？ | `text-embedding-3-small`（CGU AIR Gateway）原生維度；現行程式只產生 1536 維（沒有其他 embedding 備援）；知識庫裡早期留下的 768／3072 維舊向量不會被比對（測試計畫 DEF-05，待重算） |
| 相似度門檻為什麼是 0.75？ | 實測校準：改寫版同一謠言 0.79~0.82、不同支謠言 ≤0.68、不同主題 ≤0.52（詳見 CLAUDE.md 第 3 節） |
| 單機單寫者假設 | Parquet/SQLite 無跨行程鎖：**不要同時**跑 batch_verify_pending.py 與大量寫入的 API 請求（讀取不受影響） |
