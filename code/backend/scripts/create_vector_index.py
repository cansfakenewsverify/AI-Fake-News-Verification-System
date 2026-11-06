r"""
建立知識庫的向量索引（票 B-50，DEF-11）。預設只看不改，加 --apply 才建。

knowledge_base.content_vector 沒有索引，向量查詢要掃約 1.9 萬筆、每筆解開 6 KB 的向量，
2026-11-04 正式站實測一次 10～14 秒，這就是 PF-7 未證實列過不了的原因。

在負責人電腦的 code\backend 執行（會寫正式資料庫，--apply 前要負責人同意）：

    .\venv\Scripts\python scripts\create_vector_index.py            # 只看：目前大小、索引在不在、建了大概多大
    .\venv\Scripts\python scripts\create_vector_index.py --apply    # 建（CONCURRENTLY，不擋查詢與寫入，約數分鐘）
    .\venv\Scripts\python scripts\create_vector_index.py --drop     # 拿掉，回到全表掃描

不放進 pg_store 的 _DDL_STATEMENTS：後端啟動時才建的話會擋住寫入，Render 也會等到逾時。
HNSW 是近似搜尋，查詢的寫法不用改（Incremental Sort 仍依距離、seq 排序）。連線字串不印。
"""
import argparse
import re
import sys
from pathlib import Path
from typing import Any, Callable, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

INDEX_NAME = "ix_knowledge_base_vector_hnsw"
CREATE_SQL = (
    f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {INDEX_NAME}"
    " ON knowledge_base USING hnsw (content_vector vector_cosine_ops)"
)
DROP_SQL = f"DROP INDEX CONCURRENTLY IF EXISTS {INDEX_NAME}"
BUILD_MEMORY = "128MB"          # 預設 32 MB 放不下圖，會改用磁碟、慢很多；正式站 shared_buffers 224 MB，128 MB 還撐得住
PAGE_BYTES = 8192               # 1536 維向量一筆就佔滿一頁；1024 維（bge-m3）約 4.3 KB，兩筆放不進一頁，估法一樣
DB_LIMIT_BYTES = 500 * 1024 * 1024      # Supabase 免費方案的資料庫上限
SAFE_RATIO = 0.9


def say(msg: str) -> None:
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        enc = getattr(sys.stdout, "encoding", None) or "ascii"
        print(msg.encode(enc, "replace").decode(enc, "replace"), flush=True)


def _mb(size: float) -> str:
    return f"{size / 1024 / 1024:.0f} MB"


def _connect() -> Any:
    import psycopg

    from app.config import settings

    if not (settings.SUPABASE_DB_URL or "").strip():
        raise SystemExit("找不到 SUPABASE_DB_URL：先確認 code\\backend\\.env")
    url = re.sub(r"^postgres(ql)?(\+\w+)?://", "postgresql://", settings.SUPABASE_DB_URL)
    return psycopg.connect(url, autocommit=True, connect_timeout=20)


def _one(conn: Any, sql: str) -> Any:
    return conn.execute(sql).fetchone()


def _index_state(conn: Any) -> Optional[bool]:
    """None = 沒有這個索引；True／False = 有，能不能用（CONCURRENTLY 中途失敗會留下不能用的索引）。"""
    row = conn.execute(
        "SELECT i.indisvalid FROM pg_index i JOIN pg_class c ON c.oid = i.indexrelid WHERE c.relname = %s", (INDEX_NAME,)
    ).fetchone()
    return None if row is None else bool(row[0])


def _report_plan(conn: Any) -> None:
    """用一筆存著的向量跑和 find_similar_by_vector 相同的排序，看有沒有用到索引、要多久。只讀。"""
    row = _one(conn, "SELECT CAST(content_vector AS text) FROM knowledge_base WHERE content_vector IS NOT NULL LIMIT 1")
    if not row:
        say("知識庫沒有向量，略過查詢測試")
        return
    plan: List[str] = [r[0] for r in conn.execute(
        "EXPLAIN (ANALYZE) SELECT id FROM knowledge_base WHERE verified AND content_vector IS NOT NULL"
        " AND label_source = ANY(%s) ORDER BY content_vector <=> %s::vector, seq LIMIT 1",
        (["rule", "gold", "admin"], row[0]),
    ).fetchall()]
    used = any(INDEX_NAME in line for line in plan)
    took = next((line for line in plan if line.startswith("Execution Time")), "")
    say(f"向量查詢{'有' if used else '沒有'}用到索引；{took}")


def main(argv: Optional[List[str]] = None, connect: Callable[[], Any] = _connect) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="really create the index")
    parser.add_argument("--drop", action="store_true", help="drop the index")
    args = parser.parse_args(argv)
    conn = connect()
    db_bytes = _one(conn, "SELECT pg_database_size(current_database())")[0]
    vectors = _one(conn, "SELECT count(content_vector) FROM knowledge_base")[0]
    estimate = vectors * PAGE_BYTES
    state = _index_state(conn)
    state_text = "沒有" if state is None else ("有，可以用" if state else "有，但不能用（上次沒建完，先 --drop）")
    say(f"目前資料庫 {_mb(db_bytes)}；有向量的列 {vectors} 筆；索引：{state_text}")

    if args.drop:
        conn.execute(DROP_SQL)
        say(f"已拿掉 {INDEX_NAME}")
        return 0
    if state is True:
        _report_plan(conn)
        return 0
    if state is False:
        say("索引沒建完。先跑 --drop 再 --apply。什麼都沒改。")
        return 1
    after = db_bytes + estimate
    say(f"建了之後約多 {_mb(estimate)}，資料庫約 {_mb(after)}（免費方案上限 {_mb(DB_LIMIT_BYTES)}）")
    if after > DB_LIMIT_BYTES * SAFE_RATIO:
        say("建了會太接近上限，什麼都沒改。")
        return 1
    if not args.apply:
        say("只看不改。要建的話加 --apply（會寫正式資料庫，先經負責人同意）。")
        return 0
    conn.execute("SET statement_timeout = 0")
    conn.execute(f"SET maintenance_work_mem = '{BUILD_MEMORY}'")
    say("開始建索引，不擋查詢與寫入，約數分鐘，這個視窗不要關……")
    conn.execute(CREATE_SQL)
    if _index_state(conn) is not True:
        say("索引沒有建成。跑 --drop 清掉，再看訊息。")
        return 1
    say(f"建好了。資料庫現在 {_mb(_one(conn, 'SELECT pg_database_size(current_database())')[0])}")
    _report_plan(conn)
    return 0


if __name__ == "__main__":
    sys.exit(main())
