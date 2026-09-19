r"""
Copy the local data files into Supabase Postgres (one-off, idempotent).

    venv\Scripts\python scripts\migrate_to_supabase.py                 # dry-run (default): report only
    venv\Scripts\python scripts\migrate_to_supabase.py --apply         # create extension/tables, upsert rows
    venv\Scripts\python scripts\migrate_to_supabase.py --apply --insert-only

Sources (code/backend/data): knowledge_base.parquet, factcheck.db (fact_check_records),
tasks.parquet, admin_overrides.parquet, user_feedback.parquet (the last three only if present).
Target: settings.SUPABASE_DB_URL (from .env). STORAGE_BACKEND does not need to be "supabase".

- Dry-run only reads (local files + remote row ids); it creates nothing.
- --apply upserts by primary key "id": new rows are inserted, existing rows are updated only when
  their content differs, so a second run reports 0 inserted / 0 updated.
  Note: an upsert also resets cloud-side counters (hit_count, last_accessed_at) and admin overrides
  of rows that exist locally. Use --insert-only to leave every row already in the cloud untouched.
- Embeddings whose dimension is not 1536 are stored with a NULL vector (the row is kept).
- Console output is ASCII only (cp950 console) and never contains the connection string.
"""
import argparse
import os
import sqlite3
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

CHUNK_ROWS = 50
TABLE_ORDER = ("knowledge_base", "fact_check_records", "tasks", "admin_overrides", "user_feedback")


def say(message: str = "") -> None:
    sys.stdout.write(str(message).encode("ascii", "backslashreplace").decode("ascii") + "\n")
    sys.stdout.flush()


# -- local sources ---------------------------------------------------------
def load_knowledge(data_dir: Path) -> Tuple[Optional[List[Dict[str, Any]]], Dict[str, Any]]:
    from app.services.pandas_store import PandasStore
    from app.services.pg_store import VECTOR_DIM, kb_row_params

    if not (data_dir / "knowledge_base.parquet").exists():
        return None, {}
    df = PandasStore(data_dir=str(data_dir)).get_all_records()
    rows, dims = [], Counter()
    for record in df.to_dict("records"):
        params = kb_row_params(record)
        vector = record.get("content_vector")
        if vector is None or not hasattr(vector, "__len__"):
            dims["none"] += 1
        elif params["content_vector"] is None:
            dims[f"dim{len(vector)}" if len(vector) != VECTOR_DIM else "invalid"] += 1
        else:
            dims["kept"] += 1
        rows.append(params)
    stats = {
        "verified": sum(1 for r in rows if r["verified"]),
        "vector_kept": dims.pop("kept", 0),
        "vector_none": dims.pop("none", 0),
        "vector_dropped": sum(dims.values()),
        "vector_dropped_detail": ", ".join(f"{k}={v}" for k, v in sorted(dims.items())),
    }
    return rows, stats


def load_tasks(data_dir: Path) -> Optional[List[Dict[str, Any]]]:
    from app.services.pg_store import task_row_params
    from app.services.task_store import TaskStore

    if not (data_dir / "tasks.parquet").exists():
        return None
    df = TaskStore(data_dir=str(data_dir))._load_tasks()
    return [task_row_params(record) for record in df.to_dict("records")]


def load_audit(data_dir: Path, filename: str, columns: List[str]) -> Optional[List[Dict[str, Any]]]:
    import pandas as pd
    from app.services.pg_store import audit_row_params

    path = data_dir / filename
    if not path.exists():
        return None
    df = pd.read_parquet(path)
    return [audit_row_params(record, columns) for record in df.to_dict("records")]


def load_fact_checks(data_dir: Path) -> Optional[List[Dict[str, Any]]]:
    from app.services.pg_store import FACT_CHECK_COLUMNS, fact_check_row_params

    path = data_dir / "factcheck.db"
    if not path.exists():
        return None
    con = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)   # read-only
    try:
        con.row_factory = sqlite3.Row
        tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        if "fact_check_records" not in tables:
            return []
        existing = {r[1] for r in con.execute("PRAGMA table_info(fact_check_records)")}
        columns = [c for c in FACT_CHECK_COLUMNS if c in existing]   # old files lack the spec 6.3 columns
        cursor = con.execute(
            f"SELECT {', '.join(columns)} FROM fact_check_records ORDER BY created_at, id"
        )
        return [fact_check_row_params(dict(row)) for row in cursor]
    finally:
        con.close()


# -- remote ----------------------------------------------------------------
def remote_ids(conn, table: str) -> Optional[set]:
    """ids already in the cloud table; None = the table does not exist yet."""
    from sqlalchemy import text

    exists = conn.execute(
        text("SELECT to_regclass(quote_ident(current_schema()) || '.' || :t) IS NOT NULL"), {"t": table}
    ).scalar()
    if not exists:
        return None
    return {r[0] for r in conn.execute(text(f"SELECT id FROM {table}"))}


def drop_url_conflicts(conn, rows: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], int]:
    """fact_check_records.source_url is UNIQUE: skip a local row whose URL the cloud already
    holds under a different id (fetched there after an earlier migration)."""
    from sqlalchemy import text

    owner = {r[1]: r[0] for r in conn.execute(
        text("SELECT id, source_url FROM fact_check_records WHERE source_url IS NOT NULL"))}
    kept = [r for r in rows if owner.get(r.get("source_url"), r["id"]) == r["id"]]
    return kept, len(rows) - len(kept)


def upsert(conn, table: str, rows: List[Dict[str, Any]], update_existing: bool) -> int:
    """Returns the number of rows actually inserted or updated."""
    from app.services.pg_store import upsert_statement

    statement = upsert_statement(table, update_existing=update_existing)
    affected = 0
    for start in range(0, len(rows), CHUNK_ROWS):
        result = conn.execute(statement, rows[start:start + CHUNK_ROWS])
        affected += max(result.rowcount or 0, 0)
    return affected


def kb_summary(conn) -> str:
    from sqlalchemy import text

    row = conn.execute(text(
        "SELECT count(*), count(*) FILTER (WHERE verified), count(content_vector), "
        "count(*) FILTER (WHERE verified AND content_vector IS NOT NULL) FROM knowledge_base"
    )).one()
    return (f"knowledge_base: rows={row[0]} verified={row[1]} with_vector={row[2]} "
            f"null_vector={row[0] - row[2]} verified_with_vector={row[3]}")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Migrate local Parquet/SQLite data into Supabase Postgres.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="report only (default)")
    mode.add_argument("--apply", action="store_true", help="create extension/tables and upsert the rows")
    parser.add_argument("--insert-only", action="store_true",
                        help="with --apply: never update rows that already exist in the cloud")
    parser.add_argument("--data-dir", default=None, help="local data folder (default: code/backend/data)")
    parser.add_argument("--schema", default="public",
                        help="advanced/testing: target Postgres schema, must already exist (default: public)")
    args = parser.parse_args(argv)

    data_dir = Path(args.data_dir).resolve() if args.data_dir else ROOT / "data"
    os.chdir(ROOT)   # .env lives here; Settings reads it relative to the working directory

    from app.config import settings
    from app.database_sql import build_pg_engine, describe_db_error, init_sql_db
    from app.services.pg_store import FEEDBACK_COLUMNS, OVERRIDE_COLUMNS

    raw_url = (settings.SUPABASE_DB_URL or "").strip()
    if not raw_url:
        say("[migrate] SUPABASE_DB_URL is empty. Add it to code/backend/.env first.")
        return 2
    if "YOUR-PASSWORD" in raw_url:
        say("[migrate] SUPABASE_DB_URL still contains the [YOUR-PASSWORD] placeholder.")
        return 2
    if not data_dir.is_dir():
        say(f"[migrate] data folder not found: {data_dir.name}")
        return 2

    say(f"[migrate] mode: {'APPLY' if args.apply else 'DRY-RUN (nothing is written; use --apply to write)'}"
        + (" insert-only" if args.apply and args.insert_only else ""))
    try:
        parsed = urlparse(raw_url)
        say(f"[migrate] target: host={parsed.hostname} port={parsed.port} "
            f"db={(parsed.path or '/').lstrip('/')} schema={args.schema}")
    except ValueError:
        say("[migrate] target: (unparseable URL)")

    # 1. local sources
    knowledge, kb_stats = load_knowledge(data_dir)
    local: Dict[str, Optional[List[Dict[str, Any]]]] = {
        "knowledge_base": knowledge,
        "fact_check_records": load_fact_checks(data_dir),
        "tasks": load_tasks(data_dir),
        "admin_overrides": load_audit(data_dir, "admin_overrides.parquet", OVERRIDE_COLUMNS),
        "user_feedback": load_audit(data_dir, "user_feedback.parquet", FEEDBACK_COLUMNS),
    }
    say("[migrate] local sources:")
    for table in TABLE_ORDER:
        rows = local[table]
        say(f"  {table:<20} " + ("(file not present, skipped)" if rows is None else f"{len(rows)} rows"))
    if knowledge is not None:
        say(f"  knowledge_base detail: verified={kb_stats['verified']} "
            f"vectors kept(1536-dim)={kb_stats['vector_kept']} no_vector={kb_stats['vector_none']} "
            f"non-1536-dim stored as NULL={kb_stats['vector_dropped']}"
            + (f" ({kb_stats['vector_dropped_detail']})" if kb_stats["vector_dropped_detail"] else ""))
    for table, rows in local.items():
        ids = [r["id"] for r in rows or []]
        if len(ids) != len(set(ids)) or any(not i for i in ids):
            say(f"[migrate] {table}: local ids are missing or duplicated; aborting.")
            return 1

    # 2. remote
    started = time.perf_counter()
    try:
        engine = build_pg_engine(schema=args.schema)
    except ValueError:
        say("[migrate] invalid --schema (lower-case letters, digits and underscores only).")
        return 2
    except Exception as exc:
        say(f"[migrate] cannot build the database engine: {describe_db_error(exc, raw_url)}")
        return 2
    try:
        with engine.connect() as conn:
            from sqlalchemy import text
            version = conn.execute(text("SELECT version()")).scalar() or ""
            ext = conn.execute(text(
                "SELECT default_version, installed_version FROM pg_available_extensions WHERE name = 'vector'"
            )).first()
            say(f"[migrate] connected: {version.split(',')[0]}")
            # a missing schema silently falls through to the next search_path entry: refuse instead
            if conn.execute(text("SELECT current_schema()")).scalar() != args.schema:
                say(f"[migrate] schema '{args.schema}' does not exist on the server; aborting.")
                return 1
            if ext is None:
                say("[migrate] pgvector is NOT available on this server; aborting.")
                return 1
            say(f"[migrate] pgvector: available={ext[0]} installed={ext[1] or 'no'}"
                + ("" if ext[1] else "  -> --apply runs CREATE EXTENSION vector WITH SCHEMA extensions"))
            before = {table: remote_ids(conn, table) for table in TABLE_ORDER}

        say("[migrate] plan:")
        say(f"  {'table':<20} {'local':>6} {'cloud_before':>13} {'to_insert':>10} {'already_there':>14}")
        for table in TABLE_ORDER:
            rows, existing = local[table], before[table]
            cloud = "(no table)" if existing is None else str(len(existing))
            if rows is None:
                say(f"  {table:<20} {'-':>6} {cloud:>13} {'-':>10} {'-':>14}")
                continue
            ids = {r["id"] for r in rows}
            there = len(ids & (existing or set()))
            say(f"  {table:<20} {len(rows):>6} {cloud:>13} {len(ids) - there:>10} {there:>14}")

        if not args.apply:
            say("[migrate] dry-run finished: nothing was written. Rows already there would be updated "
                "only if their content differs (or left alone with --insert-only).")
            return 0

        # 3. apply
        init_sql_db(bind=engine)   # pgvector extension + all tables (idempotent)
        say("[migrate] schema ready (extension + tables).")
        say(f"  {'table':<20} {'before':>7} {'inserted':>9} {'updated':>8} {'unchanged':>10} {'skipped':>8} {'after':>6}")
        from sqlalchemy import text
        for table in TABLE_ORDER:
            rows = local[table]
            with engine.begin() as conn:
                existing = remote_ids(conn, table) or set()
                if rows is None:
                    say(f"  {table:<20} {len(existing):>7} {'-':>9} {'-':>8} {'-':>10} {'-':>8} {len(existing):>6}")
                    continue
                skipped = 0
                if table == "fact_check_records":
                    rows, skipped = drop_url_conflicts(conn, rows)
                ids = {r["id"] for r in rows}
                inserted = len(ids - existing)
                affected = upsert(conn, table, rows, update_existing=not args.insert_only) if rows else 0
                updated = max(affected - inserted, 0)
                after = conn.execute(text(f"SELECT count(*) FROM {table}")).scalar()
            say(f"  {table:<20} {len(existing):>7} {inserted:>9} {updated:>8} "
                f"{len(rows) - inserted - updated:>10} {skipped:>8} {after:>6}")
            if after != len(existing) + inserted:
                say(f"[migrate] WARNING {table}: expected {len(existing) + inserted} rows after the upsert, found {after}")

        with engine.connect() as conn:
            say("[migrate] " + kb_summary(conn))
        say(f"[migrate] done in {time.perf_counter() - started:.1f}s.")
        return 0
    except Exception as exc:   # never print the full exception: it may carry the connection string
        say(f"[migrate] FAILED: {describe_db_error(exc, raw_url)}")
        return 1
    finally:
        engine.dispose()


if __name__ == "__main__":
    sys.exit(main())
