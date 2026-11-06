r"""
知識庫向量換維度（票 B-52：text-embedding-3-small 1536 維 → 學校 Mercury 的 bge-m3 1024 維）。預設只看不改。

在負責人電腦的 code\backend 執行（--apply 會改正式資料庫的欄位，先經負責人同意）：

    .\venv\Scripts\python scripts\migrate_vector_dim.py --dim 1024                  # 只看：欄位現況、筆數、容量估計
    .\venv\Scripts\python scripts\migrate_vector_dim.py --dim 1024 --apply          # 改
    .\venv\Scripts\python scripts\migrate_vector_dim.py --rollback                  # 只看退回會做什麼
    .\venv\Scripts\python scripts\migrate_vector_dim.py --rollback --apply          # 退回

--apply 在一個交易裡做兩件事，都只改資料表定義、不搬資料，幾秒內做完：
1. content_vector 改名成 content_vector_te3s：舊向量全部留著，可以退回；程式不讀這一欄。
   舊欄位上若已有向量索引，索引名稱一起改成 ..._te3s（新欄位的索引之後用 create_vector_index.py 建）。
2. 新增空的 content_vector vector(--dim)。接著用 scripts/reembed_vectors.py 以新模型重算。
這段期間網站照常運作：沒有向量的列本來就會走關鍵字比對（票 B-48）；舊程式（1536 維）寫入的向量存成 NULL。

--rollback --apply：拿掉新欄位（重算的向量丟掉，之後可以再算），content_vector_te3s 改回 content_vector。

改欄位要短暫鎖表：等不到鎖 5 秒就放棄、什麼都不改，稍後再跑一次即可。連線字串不印。
"""
import argparse
import re
import sys
from pathlib import Path
from typing import Any, Callable, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

TABLE = "knowledge_base"
NEW_COLUMN = "content_vector"
OLD_COLUMN = "content_vector_te3s"          # 與 app.services.pg_store.OLD_VECTOR_COLUMN 相同
INDEX_NAME = "ix_knowledge_base_vector_hnsw"
OLD_INDEX_NAME = INDEX_NAME + "_te3s"
DB_LIMIT_BYTES = 500 * 1024 * 1024          # Supabase 免費方案的資料庫上限
SAFE_RATIO = 0.9
TOAST_CHUNK = 1996                          # 向量超過約 2 KB 會存到 TOAST，一段約 2 KB


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


def _scalar(conn: Any, sql: str, params: tuple = ()) -> Any:
    row = conn.execute(sql, params).fetchone()
    return row[0] if row else None


def column_dim(conn: Any, column: str) -> Optional[int]:
    """knowledge_base.<column> 的向量維度；沒有這欄 → None；有但沒寫維度 → 0。"""
    declared = _scalar(
        conn,
        "SELECT format_type(a.atttypid, a.atttypmod) FROM pg_attribute a"
        " WHERE a.attrelid = to_regclass(%s) AND a.attname = %s AND a.attnum > 0 AND NOT a.attisdropped",
        (TABLE, column),
    )
    if declared is None:
        return None
    match = re.search(r"vector\((\d+)\)", str(declared))
    return int(match.group(1)) if match else 0


def index_exists(conn: Any, name: str) -> bool:
    return _scalar(conn, "SELECT count(*) FROM pg_class WHERE relname = %s AND relkind = 'i'", (name,)) > 0


def vector_bytes(dim: int) -> int:
    """一筆 dim 維向量存在資料庫約佔多少位元組（float4 + 8 位元組標頭；超過 2 KB 時分段存 TOAST）。"""
    raw = 4 * dim + 8
    chunks = -(-raw // TOAST_CHUNK) if raw > 2032 else 0
    return raw + chunks * 40


def report(conn: Any, dim: int) -> dict:
    """現況（只讀）。"""
    state = {
        "db_bytes": int(_scalar(conn, "SELECT pg_database_size(current_database())")),
        "table_bytes": int(_scalar(conn, f"SELECT pg_total_relation_size('{TABLE}')")),
        "heap_bytes": int(_scalar(conn, f"SELECT pg_relation_size('{TABLE}')")),
        "new_dim": column_dim(conn, NEW_COLUMN),
        "old_dim": column_dim(conn, OLD_COLUMN),
        "rows": int(_scalar(conn, f"SELECT count(*) FROM {TABLE}")),
    }
    state["with_vector"] = int(_scalar(conn, f"SELECT count({NEW_COLUMN}) FROM {TABLE}")) if state["new_dim"] is not None else 0
    state["with_old_vector"] = (int(_scalar(conn, f"SELECT count({OLD_COLUMN}) FROM {TABLE}"))
                                if state["old_dim"] is not None else 0)
    say(f"資料庫 {_mb(state['db_bytes'])}（免費方案上限 {_mb(DB_LIMIT_BYTES)}）；{TABLE} 共 {_mb(state['table_bytes'])}"
        f"（資料列本身 {_mb(state['heap_bytes'])}），{state['rows']} 列")
    say(f"{NEW_COLUMN}：" + ("沒有這一欄" if state["new_dim"] is None else
                              f"vector({state['new_dim']})，有向量 {state['with_vector']} 列"))
    say(f"{OLD_COLUMN}：" + ("沒有這一欄" if state["old_dim"] is None else
                             f"vector({state['old_dim']})，有向量 {state['with_old_vector']} 列"))
    for name in (INDEX_NAME, OLD_INDEX_NAME):
        if index_exists(conn, name):
            say(f"向量索引 {name}：有")
    return state


def estimate(state: dict, dim: int) -> int:
    """重算完之後資料庫大概多大：新欄位＋更新每一列時的暫時空間（autovacuum 會回收再利用，檔案不一定變小）。"""
    to_fill = max(state["with_vector"], state["with_old_vector"], 0) or state["rows"]
    new_bytes = to_fill * vector_bytes(dim)
    after = state["db_bytes"] + new_bytes + state["heap_bytes"]
    say(f"重算 {to_fill} 列的 {dim} 維向量約多 {_mb(new_bytes)}；更新每一列時資料列最多再多約 {_mb(state['heap_bytes'])}"
        f"（暫時，之後回收再利用）→ 最多約 {_mb(after)}")
    if after > DB_LIMIT_BYTES * SAFE_RATIO:
        say("  注意：太接近免費方案上限。重算要分批、每批之間讓 autovacuum 回收（reembed_vectors.py 會自己檢查大小）。")
    return after


def migrate(conn: Any, dim: int) -> None:
    with conn.transaction():
        conn.execute("SET LOCAL lock_timeout = '5s'")
        conn.execute(f"ALTER TABLE {TABLE} RENAME COLUMN {NEW_COLUMN} TO {OLD_COLUMN}")
        if index_exists(conn, INDEX_NAME):
            conn.execute(f"ALTER INDEX {INDEX_NAME} RENAME TO {OLD_INDEX_NAME}")
        conn.execute(f"ALTER TABLE {TABLE} ADD COLUMN {NEW_COLUMN} vector({int(dim)})")


def rollback(conn: Any) -> None:
    with conn.transaction():
        conn.execute("SET LOCAL lock_timeout = '5s'")
        conn.execute(f"ALTER TABLE {TABLE} DROP COLUMN {NEW_COLUMN}")   # 新欄位上的索引一起拿掉
        conn.execute(f"ALTER TABLE {TABLE} RENAME COLUMN {OLD_COLUMN} TO {NEW_COLUMN}")
        if index_exists(conn, OLD_INDEX_NAME) and not index_exists(conn, INDEX_NAME):
            conn.execute(f"ALTER INDEX {OLD_INDEX_NAME} RENAME TO {INDEX_NAME}")


def main(argv: Optional[List[str]] = None, connect: Callable[[], Any] = _connect) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dim", type=int, default=1024, help="new vector dimension (bge-m3: 1024)")
    parser.add_argument("--apply", action="store_true", help="really change the table")
    parser.add_argument("--rollback", action="store_true", help="drop the new column and restore the old one")
    args = parser.parse_args(argv)
    if args.dim <= 0 or args.dim > 16000:
        say("維度不合理，結束。")
        return 2

    conn = connect()
    state = report(conn, args.dim)
    new_dim, old_dim = state["new_dim"], state["old_dim"]

    if args.rollback:
        if old_dim is None:
            say(f"沒有 {OLD_COLUMN}，沒有可以退回的東西。什麼都沒改。")
            return 1
        say(f"退回會做：拿掉 {NEW_COLUMN}（vector({new_dim})，{state['with_vector']} 列的新向量丟掉），"
            f"{OLD_COLUMN} 改回 {NEW_COLUMN}（vector({old_dim})）。")
        if not args.apply:
            say("只看不改。要退回的話加 --apply（會改正式資料庫，先經負責人同意），程式與 render.yaml 也要一起改回 1536。")
            return 0
        rollback(conn)
        say("已退回。")
        report(conn, args.dim)
        return 0

    if new_dim == args.dim and old_dim is not None:
        say(f"已經換過了：{NEW_COLUMN} 是 vector({args.dim})，舊向量留在 {OLD_COLUMN}。什麼都沒改。")
        estimate(state, args.dim)
        say("下一步：scripts/reembed_vectors.py --target cloud（先不加 --apply 看要算幾筆）。")
        return 0
    if new_dim == args.dim:
        say(f"{NEW_COLUMN} 本來就是 vector({args.dim})，不用換。什麼都沒改。")
        return 0
    if old_dim is not None:
        say(f"{OLD_COLUMN} 已經存在，但 {NEW_COLUMN} 不是 vector({args.dim})：狀態不對，先人工確認。什麼都沒改。")
        return 1
    if new_dim is None:
        say(f"找不到 {NEW_COLUMN}，狀態不對。什麼都沒改。")
        return 1

    say(f"要做的事：{NEW_COLUMN}（vector({new_dim})）改名成 {OLD_COLUMN} 保留；新增空的 {NEW_COLUMN} vector({args.dim})。")
    after = estimate(state, args.dim)
    if after > DB_LIMIT_BYTES:
        say("估計會超過免費方案上限，什麼都沒改。先和負責人討論要不要清掉舊向量。")
        return 1
    if not args.apply:
        say("只看不改。要換的話加 --apply（會改正式資料庫，先經負責人同意）。")
        return 0
    try:
        migrate(conn, args.dim)
    except Exception as exc:  # noqa: BLE001 — 鎖不到或權限問題：整個交易沒有生效
        say(f"沒有改成（{type(exc).__name__}），資料表維持原樣。等一下再跑一次；一直失敗就把這行訊息給 Claude。")
        return 1
    say("換好了。")
    report(conn, args.dim)
    say("下一步：scripts/reembed_vectors.py --target cloud（先不加 --apply 看要算幾筆）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
