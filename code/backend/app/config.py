"""
應用程式配置管理
"""
from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    """應用程式設定"""
    
    # 應用基本設定
    APP_NAME: str = "Fact Check System"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    
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
    STT_MODEL: str = "whisper-1"    # 影片語音轉文字（無字幕時的後備）

    # CGU AIR Gateway（OpenAI 相容 Responses API）：新增選項，不取代 myai168。
    CGU_API_KEY: str = ""
    CGU_BASE_URL: str = "https://air.cgu.edu.tw/cgullmapi/v1"
    CGU_MODEL: str = "gpt-5.4-mini"
    CGU_REASONING_EFFORT: str = "medium"
    CGU_STT_MODEL: str = "gpt-4o-mini-transcribe"

    # 向量 embedding：CGU LLM Gateway（OpenAI 相容，有 embeddings 端點，與 myai168 不同把金鑰）
    EMBED_RELAY_URL: str = "https://air.cgu.edu.tw/cgullmapi/v1"
    EMBED_API_KEY: str = ""
    EMBED_MODEL: str = "text-embedding-3-small"

    # 備援 embedding：Gemini（選用；CGU 失敗且有此金鑰時才用）
    GOOGLE_API_KEY: str = ""

    # CORS 設定
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:5173"

    # 向量資料庫設定（text-embedding-3-small 原生維度 1536）
    VECTOR_DIMENSION: int = 1536
    # 0.88：讓「換句話說的相同謠言」也能命中事實查核快取（0.95 過嚴只抓近乎一字不差）
    SIMILARITY_THRESHOLD: float = 0.88
    
    # 爬蟲設定
    CRAWLER_TIMEOUT: int = 30
    MAX_CONTENT_LENGTH: int = 100000
    # F1.4 截圖能力保留但預設關閉：截圖目前無下游使用者，
    # 開著會讓每次 URL 分析多啟動數次 Chromium（主文 + 相似新聞各一次）
    CRAWL_WITH_SCREENSHOT: bool = False
    SEARCH_RESULTS_LIMIT: int = 5  # 關鍵字搜尋時爬取的相似新聞數量

    # Gemini embedding 備援模型（generate_embedding 的最後備援）
    EMBEDDING_MODEL: str = "text-embedding-004"  # no "models/" prefix for new SDK

    # SQLite database (for trending records)
    SQLITE_URL: str = "sqlite:///./data/factcheck.db"

    # Search API (optional - leave empty to use free googlesearch-python)
    SERPER_API_KEY: str = ""

    # Trending fetch interval in hours
    TRENDING_FETCH_INTERVAL_HOURS: int = 6

    # 自動抓新聞排程：預設「關閉」以免背景持續燒點數。
    # 想要 24h 自動查證時，才在 .env 設 ENABLE_SCHEDULER=true。
    ENABLE_SCHEDULER: bool = False

    # 是否在分析時呼叫 web_search 即時佐證。
    # True 準確但每次貴 3~7 倍；點數吃緊時設 False（仍可正常判斷，只是少了即時引用）。
    USE_WEB_SEARCH: bool = True

    # ── Threads 查核機器人（延伸功能，預設關）──────────────────
    # 使用者在 Threads 上 @機器人帳號 回覆可疑貼文 → 機器人抓原貼文
    # 跑三層快取+AI 分析 → 自動回覆紅黃綠判定與查核來源。
    # token 申請見 CLAUDE.md 第 11 節；沒設 token 時所有功能自動停用。
    ENABLE_THREADS_BOT: bool = False
    THREADS_ACCESS_TOKEN: str = ""      # Meta 開發者後台的長效 access token（60 天）
    THREADS_USER_ID: str = ""           # 機器人帳號的 Threads user id
    THREADS_POLL_MINUTES: int = 5       # 輪詢 mentions 的間隔（分鐘）
    THREADS_BASE_URL: str = "https://graph.threads.net/v1.0"

    # Demo mode (True = return mock results, no real API calls)
    # Default False: run REAL analysis. Only set True via .env for
    # offline presentations where no API key / network is available.
    DEMO_MODE: bool = False
    
    @property
    def cors_origins_list(self) -> List[str]:
        """將 CORS 字串轉換為列表"""
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",")]
    
    class Config:
        env_file = ".env"
        # .env 有中文註解，明確指定 UTF-8（不指定會用系統編碼 cp950 讀，可能炸）
        env_file_encoding = "utf-8"
        case_sensitive = True
        # .env 裡多出的舊變數（如已移除的 DATABASE_URL）直接忽略，不要讓啟動炸掉
        extra = "ignore"


settings = Settings()
