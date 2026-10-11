r"""
人工更正正式知識庫的單一列（判定與說明一起改）。

為什麼不用管理者覆寫端點（/api/admin/tasks/{id}/override）：它要先有一筆任務，而且只改燈號、不改摘要；
判反的列改完燈號，結果頁還是寫著原本的說明（例如「此為已被查核的假訊息」），前後矛盾。

改的欄位：risk_type、is_risk、category、confidence_score、summary、explanation（頂層與 ai_analysis 都改）、
label_source=admin、verified。verified 預設 false：只有一模一樣的文字會命中這一列，不參與語意比對
（安全訊息若參與語意比對，長得像的詐騙訊息可能拿到綠燈，見 CLAUDE.md 第 3 節「查核結果為真只供分析、永不寫入」）。

    .\venv\Scripts\python scripts\correct_kb_row.py --preset xinian            # dry-run：改前改後寫進 data\correct_kb_row_report.txt
    .\venv\Scripts\python scripts\correct_kb_row.py --preset xinian --apply    # 先備份 data\correct_kb_row.bak-<時間>.json 再改
    .\venv\Scripts\python scripts\correct_kb_row.py --restore data\correct_kb_row.bak-<時間>.json

會改正式資料庫，--apply 要負責人同意。需要 .env 的 SUPABASE_DB_URL；不印連線字串；主控台只印 ASCII。
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
REPORT = DATA / "correct_kb_row_report.txt"
FIELDS = ("risk_type", "is_risk", "category", "confidence_score", "summary", "explanation", "label_source", "verified")

# HANDOFF 待辦第 5 項：這則是真的詐騙平台警示（Cofacts 回覆「不是謠言」），知識庫卻判成假訊息（2026-10-12 負責人同意更正）
PRESETS = {
    "xinian": {
        "id": "c792a37e-fa12-4226-8db4-76169014768c",
        "expect_raw": "禧年探索資本已被金管會通報為高風險投資詐騙黑平台",
        "set": {
            "risk_type": "SAFE", "is_risk": False, "category": "Safe", "confidence_score": 0.9,
            "summary": "這則警示屬實：Cofacts 查核回覆認定「不是謠言」。請勿投資「禧年探索資本」。",
            "explanation": "燈號判斷的是這則訊息本身：這則詐騙平台警示的內容正確，不代表該平台安全。"
                           "Cofacts 查核回覆認定這則訊息「不是謠言」，詳見下方查核來源。",
            "label_source": "admin", "verified": False,
        },
    },
}


def log(msg: str) -> None:
    print(msg.encode("ascii", "replace").decode("ascii"), flush=True)


def _as_json(value):
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            return None
    return value


def _read(conn, kb_id: str):
    from sqlalchemy import text

    cols = ", ".join(("id", "raw_content", "ai_analysis") + FIELDS)
    row = conn.execute(text(f"SELECT {cols} FROM knowledge_base WHERE id = :id"), {"id": kb_id}).mappings().first()
    return dict(row) if row else None


def _write(conn, kb_id: str, values: dict, ai_analysis) -> int:
    from sqlalchemy import text

    assignments = ", ".join(f"{k} = :{k}" for k in values) + ", ai_analysis = CAST(:ai AS jsonb)"
    params = {**values, "id": kb_id, "ai": None if ai_analysis is None else json.dumps(ai_analysis, ensure_ascii=False)}
    return conn.execute(text(f"UPDATE knowledge_base SET {assignments} WHERE id = :id"), params).rowcount or 0


def correct(engine, preset: dict, apply: bool) -> int:
    with engine.connect() as conn:
        row = _read(conn, preset["id"])
    if not row:
        log("row not found")
        return 1
    if (row["raw_content"] or "").strip() != preset["expect_raw"]:
        log("row content does not match the preset: not changed")
        return 1
    new = preset["set"]
    ai = _as_json(row["ai_analysis"])
    if isinstance(ai, dict):
        ai = {**ai, **{k: v for k, v in new.items() if k not in ("label_source", "verified")}}
    lines = [f"id {row['id']}", f"raw  {row['raw_content']}"]
    lines += [f"{k}: {row.get(k)!r}  ->  {new[k]!r}" for k in FIELDS]
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    log(f"before/after written to {REPORT.relative_to(BACKEND)}")
    if not apply:
        log("dry-run: nothing written (add --apply)")
        return 0
    backup = DATA / f"correct_kb_row.bak-{datetime.now():%Y%m%d-%H%M%S}.json"
    backup.write_text(json.dumps({"id": row["id"], "fields": {k: row.get(k) for k in FIELDS},
                                  "ai_analysis": _as_json(row["ai_analysis"])}, ensure_ascii=False, default=str),
                      encoding="utf-8")
    with engine.begin() as conn:
        changed = _write(conn, row["id"], new, ai)
    log(f"backup: {backup.relative_to(BACKEND)}; updated {changed} row")
    return 0 if changed else 1


def restore(engine, path: Path) -> int:
    saved = json.loads(path.read_text(encoding="utf-8"))
    with engine.begin() as conn:
        changed = _write(conn, saved["id"], saved["fields"], saved["ai_analysis"])
    log(f"restored {changed} row")
    return 0 if changed else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--preset", choices=sorted(PRESETS))
    ap.add_argument("--apply", action="store_true", help="write to the production knowledge base (default: dry-run)")
    ap.add_argument("--restore", type=Path, help="undo an --apply run from its backup file")
    args = ap.parse_args(argv)
    if not args.preset and not args.restore:
        ap.error("--preset or --restore is required")

    from app.config import settings
    from app.database_sql import build_pg_engine

    if not (settings.SUPABASE_DB_URL or "").strip():
        log("SUPABASE_DB_URL is not set in .env")
        return 2
    engine = build_pg_engine()
    try:
        if args.restore:
            return restore(engine, args.restore)
        return correct(engine, PRESETS[args.preset], args.apply)
    finally:
        engine.dispose()


if __name__ == "__main__":
    sys.exit(main())
