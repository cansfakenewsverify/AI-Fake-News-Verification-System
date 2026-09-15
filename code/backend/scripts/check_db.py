"""
Quick DB inspector (D-02): prints data-quality distributions for the
knowledge base (Parquet) and the trending table (SQLite), used as the
before/after baseline for the source cleanup (OP-9 / OP-7).

Run from backend folder:
    venv\\Scripts\\python scripts\\check_db.py
    venv\\Scripts\\python scripts\\check_db.py --out data\\check_before.txt
    venv\\Scripts\\python scripts\\check_db.py --list      # also dump every trending row

Output is ASCII/Chinese only (cp950 safe, no emoji). --out writes UTF-8.
Read-only except that init_sql_db() runs the idempotent column migration.
"""
import argparse
import os
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

EMBED_DIM = 1536
KB_FILE = "knowledge_base.parquet"


def _fmt_counter(counter: Counter) -> str:
    if not counter:
        return "(none)"
    items = sorted(counter.items(), key=lambda kv: (-kv[1], str(kv[0])))
    return ", ".join(f"{k}={v}" for k, v in items)


def _norm(value):
    """NaN / None -> 'None' so distributions stay comparable across runs."""
    if value is None:
        return "None"
    try:
        if value != value:  # NaN
            return "None"
    except Exception:
        pass
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _vector_dim(v):
    if v is None:
        return None
    try:
        return len(v)
    except TypeError:
        return None  # NaN / scalar


def kb_lines(data_dir: Path) -> list:
    import pandas as pd

    lines = ["=== Parquet knowledge_base ==="]
    path = data_dir / KB_FILE
    if not path.exists():
        lines.append(f"file: {path} (missing)")
        lines.append("total: 0")
        return lines

    df = pd.read_parquet(path)
    lines.append(f"total: {len(df)}")

    missing = [c for c in ("verified", "source_tier", "label_source") if c not in df.columns]
    if missing:
        lines.append(f"columns missing in file (counted as None): {', '.join(missing)}")

    ver = Counter(_norm(v) for v in df["verified"]) if "verified" in df.columns else Counter({"None": len(df)})
    lines.append(
        f"verified: true={ver.get('True', 0)} false={ver.get('False', 0)} null={ver.get('None', 0)}"
    )
    tier = Counter(_norm(v) for v in df["source_tier"]) if "source_tier" in df.columns else Counter({"None": len(df)})
    lines.append(f"source_tier: {_fmt_counter(tier)}")
    lsrc = Counter(_norm(v) for v in df["label_source"]) if "label_source" in df.columns else Counter({"None": len(df)})
    lines.append(f"label_source: {_fmt_counter(lsrc)}")

    if "content_vector" in df.columns:
        dims = [_vector_dim(v) for v in df["content_vector"]]
        no_vec = sum(1 for d in dims if d is None)
        bad_dim = Counter(d for d in dims if d is not None and d != EMBED_DIM)
        lines.append(f"content_vector: with_vector={len(dims) - no_vec} no_vector={no_vec}")
        lines.append(
            f"content_vector non-{EMBED_DIM}-dim rows: {sum(bad_dim.values())}"
            + (f" (dims: {_fmt_counter(bad_dim)})" if bad_dim else "")
        )
    else:
        lines.append("content_vector: column missing")
        lines.append(f"content_vector non-{EMBED_DIM}-dim rows: 0")

    if "risk_type" in df.columns:
        lines.append(f"risk_type: {_fmt_counter(Counter(_norm(v) for v in df['risk_type']))}")
    return lines


def trending_lines(records) -> list:
    lines = ["=== SQLite fact_check_records (trending) ==="]
    lines.append(f"total: {len(records)}")
    ver = Counter(_norm(r.verified) for r in records)
    lines.append(
        f"verified: true={ver.get('True', 0)} false={ver.get('False', 0)} null={ver.get('None', 0)}"
    )
    google = sum(1 for r in records if r.source_url and "news.google.com" in r.source_url)
    lines.append(f"source_url contains news.google.com: {google}")
    lines.append(
        "risk_type: " + _fmt_counter(Counter(r.risk_type or "PENDING(None)" for r in records))
    )
    lines.append(f"label_source: {_fmt_counter(Counter(_norm(r.label_source) for r in records))}")
    lines.append(f"source_tier: {_fmt_counter(Counter(_norm(r.source_tier) for r in records))}")
    return lines


def trending_detail_lines(records) -> list:
    lines = ["=== trending rows ==="]
    for i, r in enumerate(records, 1):
        title = r.news_title[:50] if r.news_title else "(no title)"
        lines.append(f"[{i}] {r.risk_type or 'PENDING':8s} | score={r.ai_score} | verified={r.verified} | {title}")
        lines.append(f"     URL: {r.source_url}")
        lines.append(f"     Created: {r.created_at}")
    return lines


def _safe_print(text: str) -> None:
    enc = sys.stdout.encoding or "utf-8"
    sys.stdout.write(text.encode(enc, errors="replace").decode(enc, errors="replace") + "\n")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Print knowledge base / trending data-quality stats.")
    parser.add_argument("--out", help="also write the report to this path (UTF-8)")
    parser.add_argument("--list", action="store_true", help="also list every trending row")
    args = parser.parse_args(argv)

    # Resolve --out against the caller's cwd before switching to the backend root.
    out_path = Path(args.out).resolve() if args.out else None
    os.chdir(ROOT)

    from app.database_sql import SessionLocal, init_sql_db
    from app.models.fact_check_record import FactCheckRecord

    init_sql_db()
    db = SessionLocal()
    try:
        records = db.query(FactCheckRecord).order_by(FactCheckRecord.created_at.desc()).all()
        lines = kb_lines(ROOT / "data") + [""] + trending_lines(records)
        if args.list:
            lines += [""] + trending_detail_lines(records)
    finally:
        db.close()

    report = "\n".join(lines)
    _safe_print(report)
    if out_path:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(report + "\n", encoding="utf-8")
        _safe_print(f"\n[written] {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
