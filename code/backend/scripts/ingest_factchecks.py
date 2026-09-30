r"""
查核機構已證實資料的批次語料（MyGoPen、台灣事實查核中心、Cofacts），供知識庫入庫與證據信心分析使用。

收錄與標記規則寫在 app/services/factcheck_corpus.py（伺服器上的每日同步 factcheck_sync.py 共用同一份）。
本腳本負責「全站」抓取與存檔快取、語料檔、在本機算向量，以及手動寫入／撤回。

步驟（分開執行、可重跑；原始回應快取在 data/factcheck_raw/，加 --refresh 才重抓）：
  fetch     抓資料 → data/factcheck_corpus.parquet 與抽樣檔 factcheck_corpus_sample.csv（不呼叫 AI、不寫知識庫）
  embed     為語料算向量（CGU embedding；只補還沒有向量的列）
  stats     印出語料統計
  apply     把可入庫列寫進知識庫（label_source=rule → verified，參與語意命中；origin=factcheck_batch）。
            預設 dry-run 只印數量；--apply 才寫。已有相同文字的已證實列、或上次已寫入的列會略過（可重跑）
  rollback  撤回：刪除 origin=factcheck_batch 的列（含每日同步寫入者；預設 dry-run；--apply 才刪）

    venv\Scripts\python scripts\ingest_factchecks.py fetch [--refresh] [--cofacts-min-requests 3] [--cofacts-max 9000]
    venv\Scripts\python scripts\ingest_factchecks.py embed [--batch 64]
    venv\Scripts\python scripts\ingest_factchecks.py stats
    venv\Scripts\python scripts\ingest_factchecks.py apply [--target local|cloud] [--sources MyGoPen,TFC,Cofacts] [--limit N] [--apply]
    venv\Scripts\python scripts\ingest_factchecks.py rollback [--target local|cloud] [--apply]

--target cloud 讀寫的是正式資料庫（Supabase），要負責人核准才執行 --apply。
正式環境平常不必跑本腳本：GitHub Actions 的 factcheck-sync 會叫後端同步（第一次的 full 同步就是完整回填）。

主控台是 cp950：只印 ASCII 與數字，中文內容寫進 UTF-8 檔案。
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

# fetch／embed 不需要資料庫：固定用本機設定，import 專案模組時不會連到 Supabase
os.environ.setdefault("STORAGE_BACKEND", "local")

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

DATA = BACKEND / "data"
RAW = DATA / "factcheck_raw"
CORPUS = DATA / "factcheck_corpus.parquet"
SAMPLE = DATA / "factcheck_corpus_sample.csv"


def log(msg: str) -> None:
    print(msg.encode("ascii", "replace").decode("ascii"), flush=True)


def make_cache(refresh: bool):
    """factcheck_corpus 的 cache hook：原始回應存成 data/factcheck_raw/<name>，重跑直接讀檔。"""
    from app.services.factcheck_corpus import DELAY_S

    def cache(name, fetch):
        path = RAW / name
        if path.exists() and not refresh:
            return json.loads(path.read_text(encoding="utf-8"))
        data = fetch()
        RAW.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        time.sleep(DELAY_S)
        return data

    return cache


# ── 指令 ─────────────────────────────────────────────────────

def cmd_fetch(args) -> int:
    import pandas as pd
    from app.services import factcheck_corpus as fc

    cache = make_cache(args.refresh)
    skipped: dict = {}
    entries = fc.mygopen_entries(cache)
    log(f"[mygopen] posts: {len(entries)}")
    rows = fc.mygopen_rows(entries, skipped)
    rows += fc.tfc_rows(cache, skipped=skipped)
    for want in ("RUMOR", "NOT_RUMOR"):
        nodes = fc.cofacts_nodes(want, args.cofacts_min_requests, args.cofacts_max, cache)
        log(f"[cofacts] {want} articles fetched: {len(nodes)}")
        rows += fc.cofacts_rows(nodes, want, skipped)

    df = pd.DataFrame(fc.dedupe_rows(rows, skipped), columns=fc.COLUMNS)
    # 重抓時保留已算好的向量（同一段文字不必再付一次 embedding）
    if CORPUS.exists():
        old = pd.read_parquet(CORPUS, columns=["content_hash", "vector"])
        df = df.merge(old.drop_duplicates("content_hash"), on="content_hash", how="left")
    else:
        df["vector"] = None
    df.to_parquet(CORPUS, index=False)

    sample = (df.groupby(["source", "label"], group_keys=False)
                .apply(lambda g: g.sample(min(len(g), 15), random_state=7)))
    sample.drop(columns=["vector"]).to_csv(SAMPLE, index=False, encoding="utf-8-sig")
    for key in sorted(skipped):
        log(f"  skipped {skipped[key]:>6}  {key}")
    print_stats(df)
    log(f"corpus: {CORPUS}  sample: {SAMPLE}")
    return 0


def print_stats(df) -> None:
    log("rows by source / label / use:")
    for (source, label, use), n in df.groupby(["source", "label", "use"]).size().items():
        log(f"  {source:<8} {label:<8} {use:<9} {n:>6}")
    kb = df[df["use"] == "kb"]
    lengths = kb["text"].str.len()
    log(f"kb rows: {len(kb)}  text chars p50={int(lengths.median())} p90={int(lengths.quantile(0.9))} "
        f"max={int(lengths.max())}")
    with_vec = int(df["vector"].notna().sum()) if "vector" in df else 0
    log(f"rows with vector: {with_vec}/{len(df)}")
    # Supabase 目前每列約 10 KB（向量 6 KB＋文字與 JSON）；免費方案上限 500 MB
    log(f"estimated knowledge_base growth if all kb rows are written: ~{len(kb) * 10 / 1024:.0f} MB")


def cmd_stats(args) -> int:
    import pandas as pd

    print_stats(pd.read_parquet(CORPUS))
    return 0


def embed_batch(texts: list) -> tuple:
    """相容舊呼叫端（scripts/evidence_confidence_study.py）。"""
    from app.services.factcheck_corpus import embed_batch as _embed

    return _embed(texts)


def cmd_embed(args) -> int:
    import pandas as pd
    from app.services.factcheck_corpus import cgu_usage

    df = pd.read_parquet(CORPUS)
    todo = [i for i in df.index if df.at[i, "vector"] is None or (isinstance(df.at[i, "vector"], float))]
    log(f"to embed: {len(todo)} / {len(df)}")
    cost_before = cgu_usage()["cost_usd"]
    vectors = df["vector"].tolist()
    tokens = 0
    for n, start in enumerate(range(0, len(todo), args.batch), 1):
        chunk = todo[start:start + args.batch]
        got, used = embed_batch([df.at[i, "text"] for i in chunk])
        for i, vec in zip(chunk, got):
            vectors[i] = vec
        tokens += used
        if n % 20 == 0 or start + args.batch >= len(todo):
            df["vector"] = vectors
            df.to_parquet(CORPUS, index=False)
            log(f"  embedded {min(start + args.batch, len(todo))}/{len(todo)}  tokens={tokens}")
    # text-embedding-3-small 牌價 USD 0.02／百萬 tokens；CGU 閘道實扣約牌價 2 倍，以 /me/usage 為準
    cost_after = cgu_usage()["cost_usd"]
    log(f"done. tokens={tokens}  list-price estimate USD {tokens * 0.02 / 1e6:.4f}  "
        f"CGU cost_usd before={cost_before:.4f} after={cost_after:.4f}")
    return 0


def cmd_apply(args) -> int:
    from datetime import datetime, timedelta

    import pandas as pd
    from app.config import settings
    from app.services import factcheck_corpus as fc
    from app.services.store_factory import get_knowledge_store

    if args.target == "cloud" and not settings.use_supabase:
        log("cloud target needs SUPABASE_DB_URL")
        return 2
    corpus = pd.read_parquet(CORPUS)
    has_vector = corpus["vector"].map(lambda v: v is not None and not isinstance(v, float))
    rows = corpus[(corpus["use"] == "kb") & has_vector]
    if args.sources:
        rows = rows[rows["source"].isin([x.strip() for x in args.sources.split(",")])]
    store = get_knowledge_store()
    present = store.existing_hashes(rows["content_hash"].tolist())
    fresh = rows[~rows["content_hash"].isin(present)]
    todo = fresh.sort_values("published", kind="mergesort")
    if args.limit:
        todo = todo.head(args.limit)
    log(f"target={args.target} ({type(store).__name__})  candidates={len(rows)}  already present={len(rows) - len(fresh)}")
    for (source, label), n in todo.groupby(["source", "label"]).size().items():
        log(f"  to write: {source:<8} {label:<8} {n:>6}")
    if not args.apply:
        log("dry-run: nothing written (add --apply)")
        return 0
    # created_at 依查核文章發布日由舊到新遞增：知識庫頁「新到舊」會先列出最新的查核結論
    start = datetime.now()
    written = 0
    for offset in range(0, len(todo), 1000):
        chunk = todo.iloc[offset:offset + 1000]
        items = [fc.kb_item(r, r["vector"], start + timedelta(microseconds=offset + i))
                 for i, (_, r) in enumerate(chunk.iterrows())]
        written += store.save_records(items)
        log(f"  written {written}/{len(todo)}")
    log(f"done: {written} rows written with origin={fc.ORIGIN}")
    return 0


def cmd_rollback(args) -> int:
    from sqlalchemy import text

    from app.config import settings
    from app.services.factcheck_corpus import ORIGIN
    from app.services.store_factory import get_knowledge_store

    if args.target == "cloud" and not settings.use_supabase:
        log("cloud target needs SUPABASE_DB_URL")
        return 2
    store = get_knowledge_store()
    df = store.get_all_records()
    n = int((df["origin"] == ORIGIN).sum()) if not df.empty else 0
    log(f"target={args.target} ({type(store).__name__})  rows with origin={ORIGIN}: {n}")
    if not args.apply or n == 0:
        log("dry-run: nothing deleted (add --apply)" if n else "nothing to delete")
        return 0
    if hasattr(store, "_connect"):
        with store._connect() as conn:
            deleted = conn.execute(text("DELETE FROM knowledge_base WHERE origin = :o"), {"o": ORIGIN}).rowcount
    else:
        store._save_knowledge_base(df[df["origin"] != ORIGIN].reset_index(drop=True))
        deleted = n
    log(f"deleted {deleted} rows")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fetch")
    f.add_argument("--refresh", action="store_true", help="ignore data/factcheck_raw/ and fetch again")
    f.add_argument("--cofacts-min-requests", type=int, default=3, help="same as factcheck_corpus.COFACTS_MIN_REQUESTS")
    f.add_argument("--cofacts-max", type=int, default=9000)
    e = sub.add_parser("embed")
    e.add_argument("--batch", type=int, default=64)
    sub.add_parser("stats")
    for name in ("apply", "rollback"):
        a = sub.add_parser(name)
        a.add_argument("--target", choices=["local", "cloud"], default="local")
        a.add_argument("--apply", action="store_true", help="actually write / delete (default: dry-run)")
        if name == "apply":
            a.add_argument("--sources", default="", help="comma-separated: MyGoPen,TFC,Cofacts")
            a.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()
    # 在 import app.config 之前決定讀寫哪一份資料（環境變數優先於 .env）
    os.environ["STORAGE_BACKEND"] = "supabase" if getattr(args, "target", "local") == "cloud" else "local"
    commands = {"fetch": cmd_fetch, "embed": cmd_embed, "stats": cmd_stats, "apply": cmd_apply,
                "rollback": cmd_rollback}
    return commands[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
