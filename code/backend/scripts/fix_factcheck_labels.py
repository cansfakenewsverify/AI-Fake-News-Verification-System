"""
一次性資料修復：
1. 清掉 RSS 殘留的 HTML entities（&nbsp; &amp; 等）— SQLite 熱門記錄 + knowledge_base.parquet
2. 修正「主流媒體查核報導」被 AI 誤標 SAFE 的記錄 → MISINFO
   （判定規則同 news_fetcher._title_indicates_debunk：標題需同時含查核語境詞與不實判定詞）

零 AI 呼叫、零點數。可重複執行（冪等）。
用法：
    venv\\Scripts\\python scripts\\fix_factcheck_labels.py           # 實際修復
    venv\\Scripts\\python scripts\\fix_factcheck_labels.py --dry-run # 只看會改哪些
"""
import argparse
import html
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database_sql import SessionLocal, init_sql_db
from app.models.fact_check_record import FactCheckRecord
from app.services.pandas_store import PandasStore
from app.services.news_fetcher import _title_indicates_debunk, _extract_claim_from_title

REPORT_PATH = os.path.join("data", "fix_labels_report.txt")


def _clean(s):
    """解 HTML entities + 正規化空白。None 原樣回傳。"""
    if not isinstance(s, str) or not s:
        return s
    out = html.unescape(s).replace("\xa0", " ")
    return out


def fix_sqlite(dry: bool, log):
    init_sql_db()
    db = SessionLocal()
    ent_fixed = label_fixed = 0
    try:
        for r in db.query(FactCheckRecord).all():
            for field in ("news_title", "content", "ai_summary"):
                v = getattr(r, field)
                nv = _clean(v)
                if nv != v:
                    if not dry:
                        setattr(r, field, nv)
                    ent_fixed += 1

            title = r.news_title or ""
            if _title_indicates_debunk(title) and r.risk_type in (None, "", "PENDING", "UNKNOWN", "SAFE"):
                claim = _extract_claim_from_title(title)
                log.write(f"[SQLite 改標] {r.risk_type} -> MISINFO | {title[:70]}\n")
                if not dry:
                    r.risk_type = "MISINFO"
                    r.category = "已查核假訊息"
                    r.ai_score = 0.9
                    r.ai_summary = f"[事實查核報導] {claim or title}"
                label_fixed += 1
        if not dry:
            db.commit()
    finally:
        db.close()
    return ent_fixed, label_fixed


def fix_parquet(dry: bool, log):
    store = PandasStore()
    df = store.get_all_records()
    if df.empty:
        return 0, 0

    ent_fixed = label_fixed = 0
    text_cols = [c for c in ("raw_content", "summary", "explanation") if c in df.columns]

    for idx, row in df.iterrows():
        # 1) entities 清洗（含 ai_analysis 內層，快取命中時回的是 ai_analysis）
        for col in text_cols:
            v = row[col]
            nv = _clean(v)
            if nv != v:
                if not dry:
                    df.at[idx, col] = nv
                ent_fixed += 1
        ai = row.get("ai_analysis")
        if isinstance(ai, dict):
            new_ai = dict(ai)
            changed = False
            for k in ("summary", "explanation"):
                nv = _clean(new_ai.get(k))
                if nv != new_ai.get(k):
                    new_ai[k] = nv
                    changed = True
            if changed:
                if not dry:
                    df.at[idx, "ai_analysis"] = new_ai
                ent_fixed += 1

        # 2) 錯標修正：URL 型記錄的 raw_content 開頭就是 RSS 標題
        head = _clean(str(row.get("raw_content") or ""))[:200]
        risk = str(row.get("risk_type") or "")
        if (
            str(row.get("data_type")) == "URL"
            and risk in ("", "PENDING", "UNKNOWN", "SAFE", "None", "nan")
            and _title_indicates_debunk(head)
        ):
            log.write(f"[Parquet 改標] {risk} -> MISINFO | {head[:70]}\n")
            if not dry:
                df.at[idx, "risk_type"] = "MISINFO"
                df.at[idx, "is_risk"] = True
                df.at[idx, "category"] = "已查核假訊息"
                df.at[idx, "confidence_score"] = 0.9
                ai = df.at[idx, "ai_analysis"]
                if isinstance(ai, dict):
                    new_ai = dict(ai)
                    new_ai.update({
                        "risk_type": "MISINFO",
                        "is_risk": True,
                        "category": "已查核假訊息",
                        "confidence_score": 0.9,
                    })
                    df.at[idx, "ai_analysis"] = new_ai
            label_fixed += 1

    if not dry and (ent_fixed or label_fixed):
        store._save_knowledge_base(df)
    return ent_fixed, label_fixed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="只列出會修改的項目，不寫入")
    args = ap.parse_args()

    log = io.open(REPORT_PATH, "w", encoding="utf-8")
    mode = "DRY-RUN" if args.dry_run else "APPLY"
    log.write(f"mode={mode}\n\n")

    s_ent, s_lab = fix_sqlite(args.dry_run, log)
    p_ent, p_lab = fix_parquet(args.dry_run, log)
    log.write(f"\nSQLite : entities={s_ent}, relabel={s_lab}\n")
    log.write(f"Parquet: entities={p_ent}, relabel={p_lab}\n")
    log.close()

    print(f"[{mode}] SQLite : entity clean={s_ent}, relabel={s_lab}")
    print(f"[{mode}] Parquet: entity clean={p_ent}, relabel={p_lab}")
    print(f"detail -> {REPORT_PATH}")


if __name__ == "__main__":
    main()
