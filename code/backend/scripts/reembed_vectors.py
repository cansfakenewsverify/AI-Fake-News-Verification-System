"""
重算知識庫裡「維度不對」的向量（測試計畫 DEF-05）。

知識庫早期有一批用別的 embedding 模型產生的向量（768／3072 維）。向量層只比對
settings.VECTOR_DIMENSION（1536）維的向量，所以這些列雖然已證實，卻永遠不會被語意命中；
搬到 Supabase 時它們的向量欄是 NULL。本腳本用現行 embedding 模型以該列的 raw_content 重算。

    .\\venv\\Scripts\\python scripts\\reembed_vectors.py                      # 只列出會處理哪些列（不呼叫 API）
    .\\venv\\Scripts\\python scripts\\reembed_vectors.py --apply              # 重算並寫回本機 Parquet（先自動備份）
    .\\venv\\Scripts\\python scripts\\reembed_vectors.py --apply --target both   # 同時更新 Supabase 的同一批列

- 只處理「有向量但維度不對」的列；沒有向量的列（非主張、刻意不建索引）不動。
- 冪等：重跑時已經是 1536 維的列不會再處理。
- 每列一次 embedding 呼叫（text-embedding-3-small，費用極低）；不呼叫 AI 判定。
- Windows 主控台是 cp950：只印 ASCII。
"""
import argparse
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from app.config import settings  # noqa: E402

KB_PATH = ROOT / "data" / "knowledge_base.parquet"


def vector_dim(value: Any) -> int:
    if value is None:
        return 0
    try:
        return int(len(value))
    except TypeError:
        return 0


def rows_to_fix(df: pd.DataFrame, want_dim: int) -> pd.DataFrame:
    """有向量、但維度不是 want_dim 的列。"""
    dims = df["content_vector"].map(vector_dim)
    return df[(dims > 0) & (dims != want_dim)]


def reembed(
    df: pd.DataFrame, embed: Callable[[str], List[float]], want_dim: int,
) -> Dict[str, List[float]]:
    """回傳 {id: 新向量}；embedding 失敗或維度仍不對的列略過（不寫入壞資料）。"""
    fixed: Dict[str, List[float]] = {}
    for _, row in rows_to_fix(df, want_dim).iterrows():
        text = str(row.get("raw_content") or "").strip()
        if not text:
            continue
        vector = embed(text)
        if vector_dim(vector) != want_dim or not np.isfinite(np.asarray(vector, dtype=np.float64)).all():
            print(f"  skip {str(row['id'])[:8]}: embedding returned dim={vector_dim(vector)}")
            continue
        fixed[str(row["id"])] = [float(x) for x in vector]
    return fixed


def apply_local(path: Path, fixed: Dict[str, List[float]]) -> int:
    from app.utils.parquet_io import atomic_write_parquet, read_parquet_retry

    df = read_parquet_retry(path)
    backup = path.with_name(path.name + ".bak-" + datetime.now().strftime("%Y%m%d-%H%M%S"))
    shutil.copy2(path, backup)
    print(f"  backup: {backup.name}")
    changed = 0
    vectors = df["content_vector"].tolist()
    for i, row_id in enumerate(df["id"].astype(str).tolist()):
        if row_id in fixed:
            vectors[i] = np.asarray(fixed[row_id], dtype=np.float64)
            changed += 1
    df["content_vector"] = pd.Series(vectors, index=df.index, dtype=object)
    atomic_write_parquet(df, path)
    return changed


def apply_supabase(fixed: Dict[str, List[float]]) -> int:
    from sqlalchemy import text

    from app.database_sql import describe_db_error, get_pg_engine
    from app.services.pg_store import vector_literal

    changed = 0
    try:
        with get_pg_engine().begin() as conn:
            for row_id, vector in fixed.items():
                literal = vector_literal(vector)
                if literal is None:
                    continue
                result = conn.execute(
                    text("UPDATE knowledge_base SET content_vector = CAST(:v AS vector) WHERE id = :id"),
                    {"v": literal, "id": row_id},
                )
                changed += result.rowcount or 0
    except Exception as exc:  # 連線字串含密碼：只印遮蔽後的訊息
        print("  supabase update failed:", describe_db_error(exc))
        return -1
    return changed


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Re-embed knowledge base rows whose vector has the wrong dimension")
    ap.add_argument("--apply", action="store_true", help="really call the embedding API and write the results")
    ap.add_argument("--target", choices=("local", "supabase", "both"), default="local")
    args = ap.parse_args(argv)

    want_dim = int(settings.VECTOR_DIMENSION)
    df = pd.read_parquet(KB_PATH)
    todo = rows_to_fix(df, want_dim)
    print(f"knowledge base rows: {len(df)} | wrong-dimension vectors: {len(todo)} (want {want_dim})")
    for _, row in todo.iterrows():
        print(f"  {str(row['id'])[:8]} dim={vector_dim(row['content_vector'])} verified={bool(row.get('verified'))}")
    if not len(todo):
        print("nothing to do")
        return 0
    if not args.apply:
        print("dry run: add --apply to re-embed (one embedding call per row)")
        return 0

    from app.services.vector_service import VectorService

    fixed = reembed(df, VectorService().vectorize_content, want_dim)
    print(f"re-embedded: {len(fixed)} / {len(todo)}")
    if not fixed:
        return 1
    if args.target in ("local", "both"):
        print(f"local parquet rows updated: {apply_local(KB_PATH, fixed)}")
    if args.target in ("supabase", "both"):
        print(f"supabase rows updated: {apply_supabase(fixed)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
