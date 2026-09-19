"""
應用程式配置管理
"""
from pydantic import field_validator
from pydantic_settings import BaseSettings
from typing import List, Literal, Optional


class Settings(BaseSettings):
    """應用程式設定"""
    
    # 應用基本設定
    APP_NAME: str = "Fact Check System"
    
    # AI API Keys（請在 .env 設定，勿寫入程式碼）
    # 學校 myai168 中繼閘道：同一把開發者金鑰可呼叫 OpenAI / Claude 等多個中繼。
    # 注意：刻意「不」用 OPENAI_API_KEY / ANTHROPIC_BASE_URL 這類標準 SDK 名稱，
    # 以免被系統既有的同名環境變數覆寫（環境變數優先序高於 .env）。
    MYAI_API_KEY: str = ""          # 學校開發者金鑰（OpenAI 與 Claude 中繼共用）

    # 主分析引擎：openai / claude 走 myai168；cgu 走 CGU AIR Gateway。其他 provider 會自動備援。
    AI_PROVIDER: str = "openai"

    # Claude 中繼（Anthropic Messages API 規格）—— 備援/高品質用
    CLAUDE_RELAY_URL: str = "https://www.myai168.com/cgu/api/anthropic/v1"
    CLAUDE_MODEL: str = "claude-opus-4-8"

    # OpenAI 中繼（Responses API 規格）—— 主力
    OPENAI_RELAY_URL: str = "https://www.myai168.com/cgu/api/openai/v1"
    OPENAI_MODEL: str = "gpt-5-mini"
    # gpt-5 是推理模型，預設會花大量時間/token 思考。分類任務用 minimal/low 即可，
    # 大幅加速並省點數（minimal 最快；設空字串則不帶此參數）。
    OPENAI_REASONING_EFFORT: str = "low"

    # CGU AIR Gateway（OpenAI 相容 Responses API）：新增選項，不取代 myai168。
    CGU_API_KEY: str = ""
    CGU_BASE_URL: str = "https://air.cgu.edu.tw/cgullmapi/v1"
    CGU_MODEL: str = "gpt-5.4-mini"
    CGU_REASONING_EFFORT: str = "medium"

    # 向量 embedding：CGU LLM Gateway（OpenAI 相容，有 embeddings 端點，與 myai168 不同把金鑰）
    EMBED_RELAY_URL: str = "https://air.cgu.edu.tw/cgullmapi/v1"
    EMBED_API_KEY: str = ""
    EMBED_MODEL: str = "text-embedding-3-small"

    # AI 呼叫逾時（秒）：spec §9 可靠性 60 s（舊值 150 s 會讓使用者等太久）
    AI_TIMEOUT_SECONDS: int = 60

    # FR-19（P1，B-24 使用）：web_search 限定網域，逗號分隔；空字串 = 不帶 filters
    WEB_SEARCH_ALLOWED_DOMAINS: str = ""

    # ── 公開站台 / 品牌（spec §7.11）──────────────────────────
    PUBLIC_BASE_URL: str = ""           # 對外網址（分享連結、OG、Threads 回覆用），例：https://xxx.vercel.app
    ADMIN_TOKEN: str = ""               # 管理端點用的 token；空字串 = 管理功能停用
    BRAND_NAME: str = "全民查證公社"
    CONTACT_EMAIL: str = ""             # 隱私政策 / 資料刪除頁的聯絡信箱

    # CORS 設定（逗號分隔；空字串項目會被濾掉）
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:5173"

    # 向量資料庫設定（text-embedding-3-small 原生維度 1536）
    VECTOR_DIMENSION: int = 1536
    # 0.75：2026-07 實測校準（text-embedding-3-small、繁中謠言文本）——
    # 「換句話說的同一謠言」相似度實測 0.79~0.82（舊值 0.88 全部擋掉，向量層形同虛設）；
    # 「同類型但不同支的詐騙」最高 0.68；不同主題 ≤0.52。
    # 0.75 = 噪音帶(≤0.68)之上、改寫帶(≥0.79)之下。換 embedding 模型要重新量測。
    SIMILARITY_THRESHOLD: float = 0.75
    
    # 爬蟲設定
    CRAWLER_TIMEOUT: int = 30
    MAX_CONTENT_LENGTH: int = 100000

    # SQLite database (for trending records)
    SQLITE_URL: str = "sqlite:///./data/factcheck.db"

    # 雲端資料層（Supabase Postgres）。STORAGE_BACKEND=local 時完全不使用（預設，本機檔案 Parquet + SQLite）。
    # 刻意不叫 DATABASE_URL：主機平台常自動注入同名環境變數，會蓋掉 .env（見 CLAUDE.md 第 2 節命名慣例）。
    # 值用 Supabase 專案頁 Connect > Session pooler 的 URI（IPv4 可連；Direct connection 只有 IPv6）。
    SUPABASE_DB_URL: str = ""
    STORAGE_BACKEND: str = "local"      # local | supabase

    # Trending fetch interval in hours
    TRENDING_FETCH_INTERVAL_HOURS: int = 6

    # 自動抓新聞排程：預設「關閉」以免背景持續燒點數。
    # 想要 24h 自動查證時，才在 .env 設 ENABLE_SCHEDULER=true。
    ENABLE_SCHEDULER: bool = False

    # 是否在分析時呼叫 web_search 即時佐證。
    # True 準確但每次貴 3~7 倍；點數吃緊時設 False（仍可正常判斷，只是少了即時引用）。
    USE_WEB_SEARCH: bool = True

    # ── 公開上線護欄（FR-14、spec §5.7）──────────────────────────
    # 每日 AI 呼叫次數上限（app/services/ai_budget.py）：達上限後，未命中快取的查證回
    # 429 daily_cap_reached；快取命中不受影響。一天以 Asia/Taipei 00:00 為界；0 = 不限制。
    DAILY_AI_CALL_CAP: int = 300
    # 每個 IP 的查證請求上限（app/utils/rate_limit.py，429 rate_limited）；0 = 關閉該視窗。
    # 預設刻意寬鬆：同一間教室／校園 Wi-Fi 的所有人對外是同一個 IP。
    RATE_LIMIT_PER_MINUTE: int = 30
    RATE_LIMIT_PER_HOUR: int = 200

    # ── Threads 查核機器人（延伸功能，預設關）──────────────────
    # 使用者在 Threads 上 @機器人帳號 回覆可疑貼文 → 機器人抓原貼文
    # 跑三層快取+AI 分析 → 自動回覆紅黃綠判定與查核來源。
    # token 申請見 CLAUDE.md 第 11 節；沒設 token 時所有功能自動停用。
    # 模式（spec §7.1）：off / live / sim；None = 未設定（才能與「明確設 off」區分）。
    # 程式一律讀 settings.threads_mode_effective，不要直接讀 THREADS_MODE。
    THREADS_MODE: Optional[Literal["off", "live", "sim"]] = None
    # 舊鍵（已被 THREADS_MODE 取代）：只在 THREADS_MODE 未設定時，true 視為 live
    ENABLE_THREADS_BOT: bool = False
    THREADS_APP_ID: str = ""            # Threads use case 頁的 Threads App ID（不是 Meta App ID）
    THREADS_APP_SECRET: str = ""        # Threads use case 頁的 Threads App Secret
    THREADS_ACCESS_TOKEN: str = ""      # Meta 開發者後台的長效 access token（60 天）
    THREADS_USER_ID: str = ""           # 機器人帳號的 Threads user id
    THREADS_POLL_MINUTES: int = 5       # 輪詢 mentions 的間隔（分鐘）
    THREADS_BASE_URL: str = "https://graph.threads.net/v1.0"
    THREADS_MAX_REPLIES_PER_POLL: int = 5   # 單輪最多回覆則數
    THREADS_MAX_REPLIES_PER_DAY: int = 50   # 每日最多回覆則數
    BOT_HANDLE: str = "factcheck_tw_bot"    # 機器人 Threads 帳號 handle（不含 @）

    # Demo mode (True = return mock results, no real API calls)
    # Default False: run REAL analysis. Only set True via .env for
    # offline presentations where no API key / network is available.
    DEMO_MODE: bool = False
    
    @field_validator("THREADS_MODE", mode="before")
    @classmethod
    def _normalize_threads_mode(cls, v):
        """空字串（.env 寫 THREADS_MODE=）視為未設定；大小寫與空白容忍。"""
        if v is None:
            return None
        if isinstance(v, str):
            v = v.strip().lower()
            return v or None
        return v

    @property
    def threads_mode_effective(self) -> str:
        """實際生效的 Threads 模式：明確設定優先；否則舊鍵 ENABLE_THREADS_BOT=true → live；其餘 off。
        DEMO_MODE 不影響 Threads。"""
        if self.THREADS_MODE is not None:
            return self.THREADS_MODE
        return "live" if self.ENABLE_THREADS_BOT else "off"

    @property
    def use_supabase(self) -> bool:
        """雲端資料層是否生效：STORAGE_BACKEND=supabase「且」有 SUPABASE_DB_URL；其餘一律本機檔案。
        database_sql（engine）與 store_factory（三個 store）共用這個判斷，兩邊才不會一個上雲一個留本機。"""
        backend = (self.STORAGE_BACKEND or "").strip().lower()
        return backend == "supabase" and bool((self.SUPABASE_DB_URL or "").strip())

    @property
    def cors_origins_list(self) -> List[str]:
        """將 CORS 字串轉換為列表"""
        return [o.strip() for o in (self.CORS_ORIGINS or "").split(",") if o.strip()]
    
    class Config:
        env_file = ".env"
        # .env 有中文註解，明確指定 UTF-8（不指定會用系統編碼 cp950 讀，可能炸）
        env_file_encoding = "utf-8"
        case_sensitive = True
        # .env 裡多出的舊變數（如已移除的 DATABASE_URL）直接忽略，不要讓啟動炸掉
        extra = "ignore"


settings = Settings()
