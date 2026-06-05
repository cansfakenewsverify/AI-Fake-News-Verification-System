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
    
    # 資料庫設定
    DATABASE_URL: str = "postgresql+psycopg://user:password@localhost:5432/factcheck_db"
    POSTGRES_USER: str = "user"
    POSTGRES_PASSWORD: str = "password"
    POSTGRES_DB: str = "factcheck_db"
    
    # Redis 設定
    REDIS_URL: str = "redis://localhost:6379/0"
    
    # AI API Keys（請在 .env 設定 GOOGLE_API_KEY，勿寫入程式碼）
    GOOGLE_API_KEY: str = ""
    OPENAI_API_KEY: str = ""
    
    # CORS 設定
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:5173"
    
    # 向量資料庫設定
    VECTOR_DIMENSION: int = 768
    SIMILARITY_THRESHOLD: float = 0.95
    
    # 爬蟲設定
    CRAWLER_TIMEOUT: int = 30
    MAX_CONTENT_LENGTH: int = 100000
    CRAWL_WITH_SCREENSHOT: bool = True  # F1.4: 對爬取新聞擷取原始截圖
    SEARCH_RESULTS_LIMIT: int = 5  # 關鍵字搜尋時爬取的相似新聞數量
    
    # AI models
    GEMINI_MODEL: str = "gemini-2.5-flash"
    GEMINI_MODEL_FALLBACK: str = "gemini-2.5-flash"
    EMBEDDING_MODEL: str = "text-embedding-004"  # no "models/" prefix for new SDK
    
    # Task queue
    QUEUE_NAME: str = "factcheck_tasks"

    # SQLite database (for trending records)
    SQLITE_URL: str = "sqlite:///./data/factcheck.db"

    # Search API (optional - leave empty to use free googlesearch-python)
    SERPER_API_KEY: str = ""

    # Trending fetch interval in hours
    TRENDING_FETCH_INTERVAL_HOURS: int = 6

    # Demo mode (True = return mock results, no real API calls)
    # Default False: run REAL Gemini analysis. Only set True via .env for
    # offline presentations where no API key / network is available.
    DEMO_MODE: bool = False
    
    @property
    def cors_origins_list(self) -> List[str]:
        """將 CORS 字串轉換為列表"""
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",")]
    
    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()

