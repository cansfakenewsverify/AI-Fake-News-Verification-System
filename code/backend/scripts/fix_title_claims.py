r"""
2026-10：標籤標題的主張改取「最後一段結論以外的所有問句段落」（news_fetcher._tagged_title_claim）之後，
把正式知識庫裡用舊規則（只取第一個問號前）寫入的列改成新主張。
原因見 docs/test/results/weekly/review_2026-10-05.md：MyGoPen「【錯誤】日月同輝照片？用16部相機等62天捕捉？錯誤描述」
只存了「日月同輝照片」，被查核的說法不在知識庫裡。

對象：source_url 是 MyGoPen 或台灣事實查核中心、raw_content 等於舊規則從標題取出的主張、新規則取出的不同者。
標題取自該列 sources[0].title（入庫時寫入的文章標題）。
- 一般情形就地更新 raw_content、data_hash、content_vector、summary（含 ai_analysis 裡的 summary）；
  id 不變，熱門查證與結果頁的 kb_id 不受影響。
- 新主張已經有別的列（同步先寫入了，或兩篇文章取出同一句）時，刪掉這筆舊列。

    .\venv\Scripts\python scripts\fix_title_claims.py            # dry-run：印數量，例子寫進 data\fix_title_claims_report.txt
    .\venv\Scripts\python scripts\fix_title_claims.py --apply    # 先備份到 data\fix_title_claims.bak-<時間>.json 再更新
    .\venv\Scripts\python scripts\fix_title_claims.py --restore data\fix_title_claims.bak-<時間>.json

可重跑：已更新的列不會再被選到。部署新規則前後各跑一次也沒關係，舊程式的同步若又寫回短主張，再跑一次就會清掉。
會改正式資料庫，--apply 要負責人同意（2026-10-12 已同意）。需要 .env 的 SUPABASE_DB_URL 與 CGU embedding 金鑰。
不印連線字串；主控台只印 ASCII，中文例子寫進 UTF-8 檔。
"""
import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
os.chdir(BACKEND)

DATA = BACKEND / "data"
REPORT = DATA / "fix_title_claims_report.txt"
SITES = ("%mygopen.com%", "%tfc-taiwan.org.tw%")
SUMMARY_TEMPLATES = ("此為已被查核的假訊息：「{}」", "此為查核機構已證實的詐騙手法：「{}」")
EMBED_BATCH = 64
ROW_COLUMNS = ("id", "data_type", "source_url", "raw_content", "data_hash", "content_vector", "is_risk", "risk_type",
               "category", "confidence_score", "summary", "explanation", "sources", "ai_analysis", "created_at",
               "last_accessed_at", "hit_count", "label_source", "origin", "last_result_id", "source_tier", "verified",
               "related_discussions")


def log(msg: str) -> None:
    print(msg.encode("ascii", "replace").decode("ascii"), flush=True)


def _short(claim: str) -> str:
    return claim if len(claim) <= 60 else claim[:60] + "…"


def _swap_summary(summary, old: str, new: str):
    """入庫時產生的固定摘要（含主張）換成新主張；其他摘要不動。"""
    for template in SUMMARY_TEMPLATES:
        if summary == template.format(_short(old)):
            return template.format(_short(new))
    return summary


def _as_json(value):
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            return None
    return value


def plan(conn):
    """(檢查的列數, 變更清單)。每筆變更：row、old、new、new_hash、action（update／delete）。"""
    from sqlalchemy import text
    from app.services import news_fetcher as nf
    from app.services.factcheck_corpus import content_hash

    rows = conn.execute(text(
        "SELECT id, source_url, raw_content, data_hash, summary, ai_analysis, sources FROM knowledge_base "
        "WHERE source_url LIKE :a OR source_url LIKE :b ORDER BY seq"), {"a": SITES[0], "b": SITES[1]}).mappings().all()
    changes = []
    for r in rows:
        sources = _as_json(r["sources"]) or []
        first = sources[0] if sources and isinstance(sources[0], dict) else {}
        title = str(first.get("title") or "").strip()
        if not nf._LEADING_TAG_RE.match(title):
            continue
        old = nf._extract_claim_from_title(title)
        new = nf._claim_for_index(title)
        if (r["raw_content"] or "").strip() != old or not new or new == old or not nf._is_real_claim(new):
            continue
        changes.append({"row": dict(r), "old": old, "new": new, "new_hash": content_hash(new)})

    hashes = sorted({c["new_hash"] for c in changes})
    taken = set()
    for start in range(0, len(hashes), 500):
        taken.update(h for (h,) in conn.execute(
            text("SELECT data_hash FROM knowledge_base WHERE data_hash = ANY(:h)"), {"h": hashes[start:start + 500]}))
    for c in changes:
        c["action"] = "delete" if c["new_hash"] in taken else "update"
        taken.add(c["new_hash"])
    return len(rows), changes


def write_report(checked: int, changes: list) -> None:
    lines = [f"checked {checked}, update {sum(c['action'] == 'update' for c in changes)}, "
             f"delete {sum(c['action'] == 'delete' for c in changes)}", ""]
    for c in changes[:80]:
        lines.append(f"[{c['action']}] {c['old']}  ->  {c['new']}  ({c['row']['source_url']})")
    REPORT.write_text("\n".join(lines), encoding="utf-8")


def backup(conn, changes: list) -> Path:
    from sqlalchemy import text

    deleted = [c["row"]["id"] for c in changes if c["action"] == "delete"]
    full = {}
    if deleted:
        cols = ", ".join("content_vector::text AS content_vector" if col == "content_vector" else col
                         for col in ROW_COLUMNS)
        for r in conn.execute(text(f"SELECT {cols} FROM knowledge_base WHERE id = ANY(:ids)"),
                              {"ids": deleted}).mappings():
            full[r["id"]] = dict(r)
    items = []
    for c in changes:
        r = c["row"]
        item = {"action": c["action"], "id": r["id"], "raw_content": r["raw_content"], "data_hash": r["data_hash"],
                "summary": r["summary"], "ai_analysis": _as_json(r["ai_analysis"])}
        if c["action"] == "delete":
            item["row"] = full.get(r["id"])
        items.append(item)
    path = DATA / f"fix_title_claims.bak-{datetime.now():%Y%m%d-%H%M%S}.json"
    path.write_text(json.dumps(items, ensure_ascii=False, default=str), encoding="utf-8")
    return path


def _update(conn, kb_id, raw, new_hash, vector, summary, ai_analysis, expected_hash=None) -> int:
    from sqlalchemy import text
    from app.services.pg_store import vector_literal

    where = "id = :id" + (" AND data_hash = :expected" if expected_hash else "")
    result = conn.execute(text(
        "UPDATE knowledge_base SET raw_content = :raw, data_hash = :h, content_vector = CAST(:v AS vector), "
        f"summary = :s, ai_analysis = CAST(:ai AS jsonb) WHERE {where}"),
        {"raw": raw, "h": new_hash, "v": vector_literal(vector), "s": summary,
         "ai": None if ai_analysis is None else json.dumps(ai_analysis, ensure_ascii=False),
         "id": kb_id, "expected": expected_hash})
    return result.rowcount or 0


def apply(engine, changes: list) -> None:
    from sqlalchemy import text
    from app.services.factcheck_corpus import embed_batch

    with engine.connect() as conn:
        path = backup(conn, changes)
    log(f"backup: {path.relative_to(BACKEND)}")
    updates = [c for c in changes if c["action"] == "update"]
    done, tokens = 0, 0
    for start in range(0, len(updates), EMBED_BATCH):
        batch = updates[start:start + EMBED_BATCH]
        vectors, used = embed_batch([c["new"] for c in batch])
        tokens += used
        with engine.begin() as conn:
            for c, vector in zip(batch, vectors):
                r = c["row"]
                ai = _as_json(r["ai_analysis"])
                if isinstance(ai, dict):
                    ai = {**ai, "summary": _swap_summary(ai.get("summary"), c["old"], c["new"])}
                done += _update(conn, r["id"], c["new"], c["new_hash"], vector,
                                _swap_summary(r["summary"], c["old"], c["new"]), ai, expected_hash=r["data_hash"])
        log(f"  updated {done}/{len(updates)}")
    deleted = [c["row"]["id"] for c in changes if c["action"] == "delete"]
    if deleted:
        with engine.begin() as conn:
            gone = conn.execute(text("DELETE FROM knowledge_base WHERE id = ANY(:ids)"), {"ids": deleted}).rowcount
        log(f"  deleted {gone} rows whose new claim already exists")
    log(f"done: updated {done}, deleted {len(deleted)}, embedding tokens {tokens}")


def restore(engine, path: Path) -> None:
    from sqlalchemy import text
    from app.services.factcheck_corpus import embed_batch

    items = json.loads(path.read_text(encoding="utf-8"))
    updates = [i for i in items if i["action"] == "update"]
    restored = 0
    for start in range(0, len(updates), EMBED_BATCH):
        batch = updates[start:start + EMBED_BATCH]
        vectors, _ = embed_batch([i["raw_content"] for i in batch])
        with engine.begin() as conn:
            for i, vector in zip(batch, vectors):
                restored += _update(conn, i["id"], i["raw_content"], i["data_hash"], vector, i["summary"],
                                    i["ai_analysis"])
    rows = [i["row"] for i in items if i["action"] == "delete" and i.get("row")]
    if rows:
        casts = {"content_vector": "vector", "sources": "jsonb", "ai_analysis": "jsonb",
                 "created_at": "timestamp", "last_accessed_at": "timestamp"}
        values = ", ".join(f"CAST(:{c} AS {casts[c]})" if c in casts else f":{c}" for c in ROW_COLUMNS)
        statement = text(f"INSERT INTO knowledge_base ({', '.join(ROW_COLUMNS)}) VALUES ({values}) "
                         "ON CONFLICT (id) DO NOTHING")
        with engine.begin() as conn:
            for row in rows:
                params = dict(row)
                for col in ("sources", "ai_analysis"):
                    if params.get(col) is not None and not isinstance(params[col], str):
                        params[col] = json.dumps(params[col], ensure_ascii=False)
                conn.execute(statement, params)
    log(f"restored: {restored} updated rows, {len(rows)} deleted rows re-inserted")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="update the production knowledge base (default: dry-run)")
    ap.add_argument("--restore", type=Path, help="undo an --apply run from its backup file")
    args = ap.parse_args(argv)

    from app.config import settings
    from app.database_sql import build_pg_engine

    if not (settings.SUPABASE_DB_URL or "").strip():
        log("SUPABASE_DB_URL is not set in .env")
        return 2
    engine = build_pg_engine()
    try:
        if args.restore:
            restore(engine, args.restore)
            return 0
        with engine.connect() as conn:
            checked, changes = plan(conn)
        write_report(checked, changes)
        log(f"checked {checked} MyGoPen/TFC rows: update {sum(c['action'] == 'update' for c in changes)}, "
            f"delete {sum(c['action'] == 'delete' for c in changes)}  (examples: {REPORT.relative_to(BACKEND)})")
        if not args.apply:
            log("dry-run: nothing written (add --apply)")
            return 0
        if changes:
            apply(engine, changes)
    finally:
        engine.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(main())
