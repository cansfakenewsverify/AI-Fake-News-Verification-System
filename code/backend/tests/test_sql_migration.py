"""D-01：fact_check_records 冪等 ALTER、label_source 回填、/api/trending limit 驗證。
離線、零點數；全部用 tmp_path 的 SQLite 檔，不碰 data/factcheck.db。"""
import sqlite3

from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from app.database_sql import init_sql_db

_OLD_SCHEMA = """
CREATE TABLE fact_check_records (
    id VARCHAR(36) NOT NULL,
    source_url VARCHAR(500),
    news_title VARCHAR(300),
    content TEXT,
    ai_score FLOAT,
    ai_summary TEXT,
    risk_type VARCHAR(20),
    category VARCHAR(50),
    is_trending BOOLEAN,
    created_at DATETIME,
    updated_at DATETIME,
    PRIMARY KEY (id)
)
"""

_NEW_COLS = {"platform", "post_id", "label_source", "result_id", "verified", "source_tier"}


def _make_old_db(path):
    con = sqlite3.connect(path)
    con.execute(_OLD_SCHEMA)
    rows = [
        ("1", "https://www.mygopen.com/a", "MISINFO", "已查核假訊息"),
        ("2", "https://www.cdc.gov.tw/b", "SAFE", "官方衛教"),
        ("3", "https://www.gov.tw/c", "SAFE", "官方資訊"),
        ("4", "https://example.com/d", "SCAM", "詐騙"),
        ("5", "https://example.com/e", None, None),
    ]
    con.executemany(
        "INSERT INTO fact_check_records (id, source_url, risk_type, category, is_trending) "
        "VALUES (?, ?, ?, ?, 1)", rows,
    )
    con.commit()
    con.close()


def _columns(path):
    con = sqlite3.connect(path)
    try:
        return {r[1] for r in con.execute("PRAGMA table_info(fact_check_records)")}
    finally:
        con.close()


def _count(path):
    con = sqlite3.connect(path)
    try:
        return con.execute("SELECT COUNT(*) FROM fact_check_records").fetchone()[0]
    finally:
        con.close()


def test_alter_idempotent_on_old_schema(tmp_path):
    db = tmp_path / "old.db"
    _make_old_db(db)
    assert len(_columns(db)) == 11
    engine = create_engine(f"sqlite:///{db.as_posix()}")
    try:
        init_sql_db(bind=engine)
        cols_first = _columns(db)
        init_sql_db(bind=engine)
        cols_second = _columns(db)
    finally:
        engine.dispose()
    assert _NEW_COLS <= cols_first
    assert cols_first == cols_second
    assert len(cols_second) == 17
    assert _count(db) == 5


def test_label_source_backfill_by_category(tmp_path):
    db = tmp_path / "old.db"
    _make_old_db(db)
    engine = create_engine(f"sqlite:///{db.as_posix()}")
    try:
        init_sql_db(bind=engine)
        init_sql_db(bind=engine)
    finally:
        engine.dispose()
    con = sqlite3.connect(db)
    try:
        got = dict(con.execute("SELECT id, label_source FROM fact_check_records"))
        verified = {r[0] for r in con.execute(
            "SELECT verified FROM fact_check_records")}
    finally:
        con.close()
    assert got == {"1": "rule", "2": "rule", "3": "rule", "4": "ai", "5": None}
    # verified / source_tier 回填屬 FR-18 清洗腳本，不在啟動時做
    assert verified == {None}


def test_trending_limit_ge_1():
    from app.main import app
    client = TestClient(app)
    assert client.get("/api/trending?limit=0").status_code == 422
