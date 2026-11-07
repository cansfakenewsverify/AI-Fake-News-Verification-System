r"""
建立知識庫的向量索引（票 B-50，DEF-11）。預設只看不改，加 --apply 才建。

knowledge_base.content_vector 沒有索引，向量查詢要掃約 1.9 萬筆、每筆解開 4～6 KB 的向量，
2026-11-04 正式站實測一次 10～14 秒，這就是 PF-7 未證實列過不了的原因（2026-11-08 bge-m3 後 p50 5.81 秒，仍未達 5 秒）。

索引是半精度（halfvec）HNSW、只收已證實列（向量查詢只比對這些）：完整精度一筆就佔滿一頁，
1.9 萬筆約 148 MB，會超過 Supabase 免費方案 500 MB 的 90% 護欄；半精度一頁放 3 筆，約 50 MB，
不用先清掉舊向量欄位 content_vector_te3s。需要 pgvector 0.7 以上（正式站 0.8.2）。
相似度仍用完整精度算（pg_store.find_similar_by_vector），半精度只用在排序找近鄰。

在負責人電腦的 code\backend 執行（會寫正式資料庫，--apply 前要負責人同意）：

    .\venv\Scripts\python scripts\create_vector_index.py            # 只看：目前大小、索引在不在、建了大概多大
    .\venv\Scripts\python scripts\create_vector_index.py --apply    # 建（CONCURRENTLY，不擋查詢與寫入，約數分鐘）
    .\venv\Scripts\python scripts\create_vector_index.py --drop     # 拿掉，回到全表掃描

建好後要重新部署（或重啟）後端一次：後端啟動時才偵測索引（pg_store._has_half_index），偵測到才改用索引的排序式。
不放進 pg_store 的 _DDL_STATEMENTS：後端啟動時才建的話會擋住寫入，Render 也會等到逾時。連線字串不印。
"""
import argparse
import re
import sys
from pathlib import Path
from typing import Any, Callable, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import settings  # noqa: E402
from app.services.pg_store import VECTOR_INDEX_NAME, distance_sql, half_index_expression  # noqa: E402

INDEX_NAME = VECTOR_INDEX_NAME
DROP_SQL = f"DROP INDEX CONCURRENTLY IF EXISTS {INDEX_NAME}"
BUILD_MEMORY = "128MB"          # 預設 32 MB 放不下圖，會改用磁碟、慢很多；正式站 shared_buffers 224 MB，128 MB 還撐得住
PAGE_BYTES = 8192
ELEMENT_OVERHEAD = 512          # 每筆除了向量本身（半精度 2 bytes／維）之外：tuple 標頭、heap 位置、近鄰清單（m=16）
DB_LIMIT_BYTES = 500 * 1024 * 1024      # Supabase 免費方案的資料庫上限
SAFE_RATIO = 0.9
MIN_PGVECTOR = (0, 7)           # halfvec 從 pgvector 0.7.0 開始


def create_sql(dim: int) -> str:
    return (
        f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {INDEX_NAME}"
        f" ON knowledge_base USING hnsw (({half_index_expression(dim)}) halfvec_cosine_ops)"
        " WHERE verified"
    )


def estimate_bytes(vectors: int, dim: int) -> int:
    """索引大約多大：一頁放得下幾筆就幾筆一頁（1024 維 3 筆、1536 維 2 筆）。"""
    per_page = max(1, PAGE_BYTES // (2 * int(dim) + ELEMENT_OVERHEAD))
    pages = -(-int(vectors) // per_page)
    return pages * PAGE_BYTES


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

    if not (settings.SUPABASE_DB_URL or "").strip():
        raise SystemExit("找不到 SUPABASE_DB_URL：先確認 code\\backend\\.env")
    url = re.sub(r"^postgres(ql)?(\+\w+)?://", "postgresql://", settings.SUPABASE_DB_URL)
    return psycopg.connect(url, autocommit=True, connect_timeout=20)


def _one(conn: Any, sql: str) -> Any:
    return conn.execute(sql).fetchone()


def _pgvector_version(conn: Any) -> Optional[tuple]:
    row = _one(conn, "SELECT extversion FROM pg_extension WHERE extname = 'vector'")
    if not row or not row[0]:
        return None
    return tuple(int(p) for p in re.findall(r"\d+", str(row[0]))[:3])


def _column_dim(conn: Any) -> Optional[int]:
    """資料庫 content_vector 欄位實際的維度（本機 .env 的 VECTOR_DIMENSION 可能和正式站不同）。"""
    row = _one(conn, (
        "SELECT format_type(a.atttypid, a.atttypmod) FROM pg_attribute a"
        " WHERE a.attrelid = to_regclass('knowledge_base') AND a.attname = 'content_vector' AND NOT a.attisdropped"
    ))
    match = re.search(r"vector\((\d+)\)", str(row[0] if row else ""))
    return int(match.group(1)) if match else None


def _index_state(conn: Any) -> Optional[bool]:
    """None = 沒有這個索引；True／False = 有，能不能用（CONCURRENTLY 中途失敗會留下不能用的索引）。"""
    row = conn.execute(
        "SELECT i.indisvalid FROM pg_index i JOIN pg_class c ON c.oid = i.indexrelid WHERE c.relname = %s", (INDEX_NAME,)
    ).fetchone()
    return None if row is None else bool(row[0])


def _report_plan(conn: Any, dim: int) -> None:
    """用一筆存著的向量跑和 pg_store 有索引時相同的排序，看有沒有用到索引、要多久。只讀。"""
    row = _one(conn, "SELECT CAST(content_vector AS text) FROM knowledge_base WHERE content_vector IS NOT NULL LIMIT 1")
    if not row:
        say("知識庫沒有向量，略過查詢測試")
        return
    order = distance_sql(dim, half_index=True).replace(":q", "%s")
    plan: List[str] = [r[0] for r in conn.execute(
        "EXPLAIN (ANALYZE) SELECT id FROM knowledge_base WHERE verified AND content_vector IS NOT NULL"
        f" ORDER BY {order}, seq LIMIT 1",
        (row[0],),
    ).fetchall()]
    used = any(INDEX_NAME in line for line in plan)
    took = next((line for line in plan if "Execution Time" in line), "")
    say(f"向量查詢{'有' if used else '沒有'}用到索引；{took}")


def main(argv: Optional[List[str]] = None, connect: Callable[[], Any] = _connect) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="really create the index")
    parser.add_argument("--drop", action="store_true", help="drop the index")
    args = parser.parse_args(argv)
    conn = connect()
    # 索引的維度跟著資料庫欄位走；後端用 VECTOR_DIMENSION 偵測索引，兩者要一樣（正式站 render.yaml 設 1024）
    dim = _column_dim(conn) or int(settings.VECTOR_DIMENSION)
    if dim != int(settings.VECTOR_DIMENSION):
        say(f"注意：資料庫欄位是 {dim} 維，這台的 VECTOR_DIMENSION 是 {settings.VECTOR_DIMENSION}；索引照資料庫欄位建")
    db_bytes = _one(conn, "SELECT pg_database_size(current_database())")[0]
    vectors = _one(conn, "SELECT count(content_vector) FILTER (WHERE verified) FROM knowledge_base")[0]
    state = _index_state(conn)
    state_text = "沒有" if state is None else ("有，可以用" if state else "有，但不能用（上次沒建完，先 --drop）")
    say(f"目前資料庫 {_mb(db_bytes)}；已證實且有向量的列 {vectors} 筆（{dim} 維）；索引：{state_text}")

    if args.drop:
        conn.execute(DROP_SQL)
        say(f"已拿掉 {INDEX_NAME}。重新部署（或重啟）後端，程式才會改回全表掃描的寫法")
        return 0
    if state is True:
        _report_plan(conn, dim)
        return 0
    if state is False:
        say("索引沒建完。先跑 --drop 再 --apply。什麼都沒改。")
        return 1
    version = _pgvector_version(conn)
    if version is None or version[:2] < MIN_PGVECTOR:
        shown = ".".join(map(str, version)) if version else "讀不到"
        say(f"pgvector 版本 {shown}，沒有半精度 halfvec（要 0.7 以上）。什麼都沒改。")
        return 1
    estimate = estimate_bytes(vectors, dim)
    after = db_bytes + estimate
    say(f"半精度索引建了之後約多 {_mb(estimate)}，資料庫約 {_mb(after)}（免費方案上限 {_mb(DB_LIMIT_BYTES)}）")
    if after > DB_LIMIT_BYTES * SAFE_RATIO:
        say("建了會太接近上限，什麼都沒改。")
        return 1
    if not args.apply:
        say("只看不改。要建的話加 --apply（會寫正式資料庫，先經負責人同意）。")
        return 0
    conn.execute("SET statement_timeout = 0")
    conn.execute(f"SET maintenance_work_mem = '{BUILD_MEMORY}'")
    say("開始建索引，不擋查詢與寫入，約數分鐘，這個視窗不要關……")
    conn.execute(create_sql(dim))
    if _index_state(conn) is not True:
        say("索引沒有建成。跑 --drop 清掉，再看訊息。")
        return 1
    say(f"建好了。資料庫現在 {_mb(_one(conn, 'SELECT pg_database_size(current_database())')[0])}")
    _report_plan(conn, dim)
    say("重新部署（或重啟）後端一次，程式偵測到索引後才會用它")
    return 0


if __name__ == "__main__":
    sys.exit(main())
