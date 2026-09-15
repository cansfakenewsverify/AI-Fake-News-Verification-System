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


# spec 6.3: columns added after v1.0. Order matters only for readability.
_NEW_FACT_CHECK_COLUMNS = (
    ("platform", "VARCHAR(20)"),
    ("post_id", "VARCHAR(64)"),
    ("label_source", "VARCHAR(10)"),
    ("result_id", "VARCHAR(36)"),
    ("verified", "BOOLEAN"),
    ("source_tier", "INTEGER"),
)

# label_source backfill: these categories are only ever written by the
# deterministic marking rules in news_fetcher (CLAUDE.md section 9).
_RULE_CATEGORIES = ("已查核假訊息", "官方衛教", "官方資訊")


def _migrate_fact_check_records(bind) -> list:
    """
    Idempotent ALTER TABLE for old fact_check_records schemas (spec 6.3, OP-7).
    Checks PRAGMA table_info first, adds only missing columns. label_source is
    backfilled only in the run that adds the column (reads category/risk_type
    only; never calls marking-rule functions, never touches the network).
    verified/source_tier backfill belongs to the FR-18 cleanup script.
    Returns the list of added column names.
    """
    from sqlalchemy import inspect, text

    if not inspect(bind).has_table("fact_check_records"):
        return []
    added = []
    with bind.begin() as conn:
        rows = conn.execute(text("PRAGMA table_info(fact_check_records)")).fetchall()
        existing = {r[1] for r in rows}
        for name, col_type in _NEW_FACT_CHECK_COLUMNS:
            if name not in existing:
                conn.execute(text(f"ALTER TABLE fact_check_records ADD COLUMN {name} {col_type}"))
                added.append(name)
        if "label_source" in added:
            placeholders = ", ".join(f":c{i}" for i in range(len(_RULE_CATEGORIES)))
            params = {f"c{i}": c for i, c in enumerate(_RULE_CATEGORIES)}
            conn.execute(text(
                "UPDATE fact_check_records SET label_source = 'rule' "
                f"WHERE label_source IS NULL AND category IN ({placeholders})"
            ), params)
            conn.execute(text(
                "UPDATE fact_check_records SET label_source = 'ai' "
                "WHERE label_source IS NULL AND risk_type IS NOT NULL"
            ))
    return added


def init_sql_db(bind=None):
    os.makedirs("data", exist_ok=True)
    bind = bind if bind is not None else engine
    # make sure the model is registered on Base before create_all
    from app.models import fact_check_record  # noqa: F401
    Base.metadata.create_all(bind=bind)
    if bind.dialect.name == "sqlite":
        _migrate_fact_check_records(bind)
