"""
SQL database setup (SQLAlchemy).

Default (STORAGE_BACKEND=local): SQLite at data/factcheck.db (zero config).
Cloud (STORAGE_BACKEND=supabase + SUPABASE_DB_URL): Supabase Postgres through psycopg 3.
The same engine then also serves the Postgres stores in app/services/pg_store.py.

create_engine() never connects: importing this module does not need a database, the
first query opens the first connection. The connection string holds the password, so
nothing here logs or raises it (see describe_db_error).
"""
import os
import re
import threading
from typing import List, Optional
from urllib.parse import unquote, urlparse

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import sessionmaker, declarative_base
from app.config import settings

PG_DEFAULT_SCHEMA = "public"
PG_CONNECT_TIMEOUT_SECONDS = 15
_SCHEMA_NAME_RE = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")


def _db_secrets(raw_url: str) -> List[str]:
    """Strings that must never reach a log line: the raw URL and its password (both encodings)."""
    raw_url = (raw_url or "").strip()
    secrets_found = [raw_url] if raw_url else []
    try:
        password = urlparse(raw_url).password
    except ValueError:
        password = None
    if password:
        secrets_found += [password, unquote(password)]
    return [s for s in secrets_found if s]


def describe_db_error(exc: BaseException, raw_url: Optional[str] = None) -> str:
    """One-line, credential-free description of a database error (safe to print / log)."""
    text_ = str(exc)
    message = text_.splitlines()[0][:200] if text_ else ""
    for secret in _db_secrets(raw_url if raw_url is not None else settings.SUPABASE_DB_URL):
        message = message.replace(secret, "***")
    return f"{type(exc).__name__}: {message}".rstrip(": ")


def _search_path_sql(schema: str) -> str:
    # Supabase installs extensions (pgvector) into the "extensions" schema. The schema name is
    # validated against _SCHEMA_NAME_RE before it gets here (it cannot be bound as a parameter).
    parts = [schema, "extensions", "public"]
    ordered = [p for i, p in enumerate(parts) if p not in parts[:i]]
    return "SET search_path TO " + ", ".join(f'"{p}"' for p in ordered)


def build_pg_engine(url: Optional[str] = None, schema: str = PG_DEFAULT_SCHEMA) -> Engine:
    """
    Postgres engine for Supabase (Session pooler URI). Lazy: no connection is opened here.

    search_path is set by a "connect" hook (SET search_path TO <schema>, extensions, public)
    instead of the libpq "options" startup parameter, which the Supabase pooler may reject.
    Tests pass a throwaway schema; the application uses "public".
    """
    raw = (url if url is not None else settings.SUPABASE_DB_URL or "").strip()
    if not raw:
        raise RuntimeError("SUPABASE_DB_URL is empty (see .env.example: Supabase > Connect > Session pooler)")
    if not _SCHEMA_NAME_RE.match(schema or ""):
        raise ValueError("invalid Postgres schema name")
    try:
        sa_url = make_url(raw)
        if not sa_url.drivername.startswith(("postgresql", "postgres")):
            raise ValueError("not a postgres URL")
        sa_url = sa_url.set(drivername="postgresql+psycopg")
    except Exception:
        # "from None": SQLAlchemy's parse error quotes the whole string, password included
        raise RuntimeError("SUPABASE_DB_URL is not a valid postgresql:// URI") from None

    pg_engine = create_engine(
        sa_url,
        pool_pre_ping=True,
        pool_size=3,
        max_overflow=2,
        pool_recycle=300,
        connect_args={
            "connect_timeout": PG_CONNECT_TIMEOUT_SECONDS,
            # no server-side prepared statements: they break behind transaction-mode poolers
            "prepare_threshold": None,
        },
    )
    search_path_sql = _search_path_sql(schema)

    @event.listens_for(pg_engine, "connect", insert=True)
    def _set_search_path(dbapi_connection, _connection_record):
        # autocommit for this one statement: a SET inside a transaction would be undone by the
        # pool's rollback-on-return
        previous = dbapi_connection.autocommit
        dbapi_connection.autocommit = True
        try:
            with dbapi_connection.cursor() as cursor:
                cursor.execute(search_path_sql)
        finally:
            dbapi_connection.autocommit = previous

    return pg_engine


_url = getattr(settings, "SQLITE_URL", "sqlite:///./data/factcheck.db")

# SQLite needs check_same_thread=False for multi-threaded FastAPI
_connect_args = {"check_same_thread": False} if _url.startswith("sqlite") else {}

if settings.use_supabase:
    engine = build_pg_engine()
else:
    engine = create_engine(_url, connect_args=_connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

_pg_engine: Optional[Engine] = None
_pg_engine_lock = threading.Lock()


def get_pg_engine() -> Engine:
    """
    Engine for the Postgres stores: the module engine when it already targets Postgres,
    otherwise one built lazily from settings.SUPABASE_DB_URL (scripts/migrate_to_supabase.py
    runs with the default local backend and still needs to reach Supabase).
    """
    global _pg_engine
    if engine.dialect.name == "postgresql":
        return engine
    with _pg_engine_lock:
        if _pg_engine is None:
            _pg_engine = build_pg_engine()
        return _pg_engine


def reset_pg_engine() -> None:
    """Drop the lazily built Postgres engine (tests that switch SUPABASE_DB_URL)."""
    global _pg_engine
    with _pg_engine_lock:
        if _pg_engine is not None:
            _pg_engine.dispose()
        _pg_engine = None


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
    if bind.dialect.name == "postgresql":
        # pgvector extension + knowledge_base / tasks / audit tables + fact_check_records,
        # all idempotent (the SQLite-only column migration below does not apply)
        from app.services.pg_store import ensure_pg_schema
        ensure_pg_schema(bind, force=True)
        return
    Base.metadata.create_all(bind=bind)
    if bind.dialect.name == "sqlite":
        _migrate_fact_check_records(bind)
