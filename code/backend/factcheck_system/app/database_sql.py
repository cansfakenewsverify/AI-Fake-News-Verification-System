"""
SQLite / PostgreSQL database setup (SQLAlchemy).
Default: SQLite at data/factcheck.db (zero config).
Switch to PostgreSQL by setting SQLITE_URL in .env.
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from app.config import settings
import os

_url = getattr(settings, "SQLITE_URL", "sqlite:///./data/factcheck.db")

# SQLite needs check_same_thread=False for multi-threaded FastAPI
_connect_args = {"check_same_thread": False} if _url.startswith("sqlite") else {}

engine = create_engine(_url, connect_args=_connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_sql_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_sql_db():
    os.makedirs("data", exist_ok=True)
    Base.metadata.create_all(bind=engine)
