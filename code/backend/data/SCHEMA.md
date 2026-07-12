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
| `hit_count` | int | 命中次數（熱門度） |

### 三層快取流程（2026-07 修正：文字輸入的向量比對在爬蟲之前、以原文比對）

```
文字輸入 ──► Layer 1: data_hash 比對 ──► 命中？回傳
                        │ miss
                        ▼
            Layer 2: 原文向量相似度比對(門檻 0.75 實測校準) ──► 命中？回傳(連爬蟲/AI 都省)
                        │ miss
                        ▼
            爬蟲(相關查核文章當參考脈絡) ──► Layer 3: AI 分析，存入快取

網址輸入 ──► Layer 0: source_url 比對 ──► Layer 1: hash ──► 爬蟲 ──►
            Layer 2: 內文向量比對 ──► Layer 3: AI 分析，存入快取
```

API 回應的 `cache_layer` 欄位（url / hash / vector / null）標示命中層。

---

## 2. `factcheck.db` / `fact_check_records`（SQLite）— 熱門趨勢資料

供 `news_fetcher` + `/api/trending` 使用，存放從 RSS / Cofacts / Google News 抓回的記錄。

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
| 為什麼 Embedding 用 1536 維？ | `text-embedding-3-small`（CGU AIR Gateway）原生維度；Gemini 備援時為 768 維，向量搜尋已做維度防呆（只比對同維度） |
| 相似度門檻為什麼是 0.75？ | 實測校準：改寫版同一謠言 0.79~0.82、不同支謠言 ≤0.68、不同主題 ≤0.52（詳見 CLAUDE.md 第 3 節） |
| 單機單寫者假設 | Parquet/SQLite 無跨行程鎖：**不要同時**跑 batch_verify_pending.py 與大量寫入的 API 請求（讀取不受影響） |
