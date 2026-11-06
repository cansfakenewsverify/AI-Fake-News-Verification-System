r"""
重算知識庫的向量：維度不對的列（測試計畫 DEF-05），以及換 embedding 模型時整庫重算（票 B-52，bge-m3 1024 維）。
預設只看不改、不呼叫 API。

換模型時先在同一個 PowerShell 視窗設好新模型（或寫進 .env），再執行：

    $env:EMBED_RELAY_URL='https://air.cgu.edu.tw/mercuryapi/v1'; $env:EMBED_MODEL='bge-m3'; $env:VECTOR_DIMENSION='1024'
    .\venv\Scripts\python scripts\reembed_vectors.py --target cloud             # 只看：要算幾筆、欄位維度對不對
    .\venv\Scripts\python scripts\reembed_vectors.py --target cloud --embed     # 只算、存本機快取，不寫資料庫（校準用）
    .\venv\Scripts\python scripts\reembed_vectors.py --target cloud --apply     # 算完寫回 Supabase（先經負責人同意）
    .\venv\Scripts\python scripts\reembed_vectors.py --target local --apply     # 本機 Parquet（先自動備份）

哪些列要算：
- local：有向量、但維度不是 VECTOR_DIMENSION 的列（沒有向量的列不動：非主張、刻意不建向量）。
- cloud：content_vector 是空的，而且換模型前有向量（content_vector_te3s，scripts/migrate_vector_dim.py 留下的）
  或是已證實的查核資料列（embedding 停用期間寫入、向量待補，票 B-49）。資料庫欄位維度和設定不同時不做，先跑遷移。
送去算的文字和當初寫入時一樣：網站與 Threads 的文字查證列用 matching_text（去掉「網傳」「是真的嗎」，票 B-45），
其他列用原文；一律截到前 2000 字（factcheck_corpus.EMBED_MAX_CHARS）。

- 批次送（每次 64 筆），算好的向量先存本機快取（data/embed_cache/，只存雜湊與向量，不存文字）；
  中斷後重跑從沒算過的接著算，已寫入的列不會再寫。
- 寫 Supabase 時每 64 筆一個交易；每 20 批看一次資料庫大小，超過免費方案上限的 90% 就停下（之後重跑接著做）。
- 不呼叫 AI 判定。Windows 主控台是 cp950：只印中英文。
"""
import argparse
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from app.config import settings  # noqa: E402

KB_PATH = ROOT / "data" / "knowledge_base.parquet"
OLD_COLUMN = "content_vector_te3s"
FACTCHECK_ORIGIN = "factcheck_batch"
MATCHING_ORIGINS = ("web", "threads", "threads_sim")      # pandas_task_processor 寫入的列（文字輸入存 matching_text 的向量）
MATCHING_LABELS = ("ai", "admin")                         # admin：管理者覆寫過的網站查證列，向量沒變
DB_LIMIT_BYTES = 500 * 1024 * 1024
SAFE_RATIO = 0.9
WRITE_BATCH = 64
SIZE_CHECK_EVERY = 20


def say(msg: str) -> None:
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        enc = getattr(sys.stdout, "encoding", None) or "ascii"
        print(msg.encode(enc, "replace").decode(enc, "replace"), flush=True)


def vector_dim(value: Any) -> int:
    if value is None:
        return 0
    try:
        return int(len(value))
    except TypeError:
        return 0


def embed_text(row: Dict[str, Any]) -> str:
    """這一列要送去算向量的文字（和當初寫入時相同的規則）；空字串 = 不算。"""
    text = str(row.get("raw_content") or "")
    if (str(row.get("data_type") or "").upper() == "TEXT"
            and str(row.get("origin") or "web") in MATCHING_ORIGINS
            and str(row.get("label_source") or "ai") in MATCHING_LABELS):
        from app.utils.claim_text import matching_text
        text = matching_text(text)
    return text.strip()


def rows_to_fix(df: pd.DataFrame, want_dim: int) -> pd.DataFrame:
    """（本機）有向量、但維度不是 want_dim 的列。"""
    dims = df["content_vector"].map(vector_dim)
    return df[(dims > 0) & (dims != want_dim)]


def _good(vector: Any, want_dim: int) -> bool:
    if vector_dim(vector) != want_dim:
        return False
    arr = np.asarray(vector, dtype=np.float64)
    return bool(np.isfinite(arr).all() and np.any(arr))


def reembed(df: pd.DataFrame, embed: Callable[[str], List[float]], want_dim: int) -> Dict[str, List[float]]:
    """一次一筆的舊介面（測試與小量修補用）：{id: 新向量}；空白文字不呼叫，維度仍不對的略過。"""
    fixed: Dict[str, List[float]] = {}
    for _, row in rows_to_fix(df, want_dim).iterrows():
        text = embed_text(row.to_dict())
        if not text:
            continue
        vector = embed(text)
        if not _good(vector, want_dim):
            say(f"  略過 {str(row['id'])[:8]}：回傳 {vector_dim(vector)} 維")
            continue
        fixed[str(row["id"])] = [float(x) for x in vector]
    return fixed


def vectors_from_cache(rows: List[Dict[str, Any]], cache: Any, want_dim: int) -> Dict[str, np.ndarray]:
    out: Dict[str, np.ndarray] = {}
    for row in rows:
        text = embed_text(row)
        vector = cache.known(text) if text else None
        if vector is not None and _good(vector, want_dim):
            out[str(row["id"])] = vector
    return out


def apply_local(path: Path, fixed: Dict[str, Any]) -> int:
    from app.utils.parquet_io import atomic_write_parquet, read_parquet_retry

    df = read_parquet_retry(path)
    backup = path.with_name(path.name + ".bak-" + datetime.now().strftime("%Y%m%d-%H%M%S"))
    shutil.copy2(path, backup)
    say(f"  備份：{backup.name}")
    changed = 0
    vectors = df["content_vector"].tolist()
    for i, row_id in enumerate(df["id"].astype(str).tolist()):
        if row_id in fixed:
            vectors[i] = np.asarray(fixed[row_id], dtype=np.float64)
            changed += 1
    # Parquet 的同一欄不能混 float32 與 float64，整欄統一
    vectors = [None if vector_dim(v) == 0 else np.asarray(v, dtype=np.float64) for v in vectors]
    df["content_vector"] = pd.Series(vectors, index=df.index, dtype=object)
    atomic_write_parquet(df, path)
    return changed


# ── Supabase ────────────────────────────────────────────────────
def _engine():
    from app.database_sql import get_pg_engine
    return get_pg_engine()


def cloud_state(conn: Any) -> Dict[str, Any]:
    from sqlalchemy import text

    def dim_of(column: str) -> Optional[int]:
        declared = conn.execute(text(
            "SELECT format_type(a.atttypid, a.atttypmod) FROM pg_attribute a"
            " WHERE a.attrelid = to_regclass('knowledge_base') AND a.attname = :c AND a.attnum > 0 AND NOT a.attisdropped"
        ), {"c": column}).scalar()
        if declared is None:
            return None
        import re
        match = re.search(r"vector\((\d+)\)", str(declared))
        return int(match.group(1)) if match else 0

    return {
        "column_dim": dim_of("content_vector"),
        "has_old": dim_of(OLD_COLUMN) is not None,
        "db_bytes": int(conn.execute(text("SELECT pg_database_size(current_database())")).scalar()),
    }


def cloud_rows(conn: Any, has_old: bool) -> List[Dict[str, Any]]:
    from sqlalchemy import text

    had_vector = f"{OLD_COLUMN} IS NOT NULL OR " if has_old else ""
    statement = text(
        "SELECT id, raw_content, data_type, origin, label_source FROM knowledge_base"
        f" WHERE content_vector IS NULL AND ({had_vector}(verified AND origin = :origin))"
        " ORDER BY seq"
    )
    return [dict(r) for r in conn.execute(statement, {"origin": FACTCHECK_ORIGIN}).mappings().all()]


def write_cloud(engine: Any, vectors: Dict[str, np.ndarray], limit_bytes: int = DB_LIMIT_BYTES) -> int:
    """每 WRITE_BATCH 筆一個交易，只寫 content_vector 還是空的列（重跑不會重寫）；太接近容量上限就停。"""
    from sqlalchemy import text

    from app.services.pg_store import vector_literal

    statement = text("UPDATE knowledge_base SET content_vector = CAST(:v AS vector)"
                     " WHERE id = :id AND content_vector IS NULL")
    items = [(k, vector_literal(v)) for k, v in vectors.items()]
    items = [(k, lit) for k, lit in items if lit is not None]
    written = 0
    for b in range(0, len(items), WRITE_BATCH):
        if (b // WRITE_BATCH) % SIZE_CHECK_EVERY == 0:
            with engine.connect() as conn:
                size = int(conn.execute(text("SELECT pg_database_size(current_database())")).scalar())
            if size > limit_bytes * SAFE_RATIO:
                say(f"資料庫已到 {size / 1024 / 1024:.0f} MB，太接近上限，先停下（已寫 {written} 筆；等 autovacuum 回收後重跑會接著寫）。")
                return written
        with engine.begin() as conn:
            result = conn.execute(statement, [{"id": k, "v": lit} for k, lit in items[b:b + WRITE_BATCH]])
            written += max(result.rowcount or 0, 0)
        if (b // WRITE_BATCH + 1) % SIZE_CHECK_EVERY == 0:
            say(f"  已寫 {written}／{len(items)}")
    return written


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Re-embed knowledge base vectors (wrong dimension / new embedding model)")
    ap.add_argument("--target", choices=("local", "cloud", "supabase", "both"), default="local",
                    help="supabase is an old name for cloud")
    ap.add_argument("--embed", action="store_true", help="call the embedding API and fill the local cache only")
    ap.add_argument("--apply", action="store_true", help="call the embedding API and write the vectors")
    args = ap.parse_args(argv)
    target = "cloud" if args.target == "supabase" else args.target
    want_dim = int(settings.VECTOR_DIMENSION)
    say(f"模型 {settings.EMBED_MODEL}（{settings.EMBED_RELAY_URL}），要 {want_dim} 維")

    local_rows: List[Dict[str, Any]] = []
    if target in ("local", "both"):
        df = pd.read_parquet(KB_PATH)
        todo = rows_to_fix(df, want_dim)
        local_rows = [r for r in todo.to_dict("records")]
        say(f"本機知識庫 {len(df)} 列；向量維度不對的 {len(todo)} 列")

    engine, state, cloud_todo = None, None, []
    if target in ("cloud", "both"):
        engine = _engine()
        with engine.connect() as conn:
            state = cloud_state(conn)
            say(f"Supabase：content_vector 是 vector({state['column_dim']})，"
                f"{'有' if state['has_old'] else '沒有'} {OLD_COLUMN}；資料庫 {state['db_bytes'] / 1024 / 1024:.0f} MB")
            if state["column_dim"] != want_dim:
                say(f"資料庫欄位不是 {want_dim} 維：先跑 scripts/migrate_vector_dim.py --dim {want_dim}（經負責人同意）。什麼都沒做。")
                return 1
            cloud_todo = cloud_rows(conn, state["has_old"])
        say(f"Supabase 要補向量的列 {len(cloud_todo)} 列")

    all_rows = local_rows + cloud_todo
    texts = [embed_text(r) for r in all_rows]
    blank = sum(1 for t in texts if not t)
    if blank:
        say(f"其中 {blank} 列沒有文字，不算")
    if not any(texts):
        say("沒有要算的。")
        return 0

    from embed_cache import EmbedCache

    cache = EmbedCache(settings.EMBED_MODEL, dim=want_dim)
    need = cache.missing(texts)
    say(f"本機快取已有 {len(cache)} 筆；還要呼叫 embedding {len(need)} 筆（約 {-(-len(need) // cache.batch)} 批）")
    if not (args.embed or args.apply):
        say("只看不改。--embed 只算、存本機快取；--apply 算完寫回（寫正式資料庫前先經負責人同意）。")
        return 0

    try:
        cache.ensure(texts)
    except KeyboardInterrupt:
        say("中斷了；已算的存在本機快取，重跑會接著算。")
        return 1
    except Exception as exc:  # noqa: BLE001 — 例外訊息可能含網址：只印類別與狀態碼
        code = getattr(getattr(exc, "response", None), "status_code", None)
        say(f"embedding 失敗（{type(exc).__name__}{f' HTTP {code}' if code else ''}）；已算的存在本機快取，重跑會接著算。")
        return 1
    if not args.apply:
        say(f"已存本機快取 {cache.path.name}（{len(cache)} 筆）。沒有寫任何資料庫。")
        return 0

    if local_rows:
        fixed = vectors_from_cache(local_rows, cache, want_dim)
        say(f"本機 Parquet 更新 {apply_local(KB_PATH, fixed)} 列")
    if cloud_todo:
        vectors = vectors_from_cache(cloud_todo, cache, want_dim)
        say(f"寫入 Supabase {len(vectors)} 列……")
        try:
            written = write_cloud(engine, vectors)
        except Exception as exc:  # noqa: BLE001 — 連線字串含密碼：只印遮蔽後的訊息
            from app.database_sql import describe_db_error
            say(f"寫入 Supabase 失敗：{describe_db_error(exc)}（已寫的保留，重跑會接著寫）")
            return 1
        say(f"Supabase 寫入 {written} 列")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
