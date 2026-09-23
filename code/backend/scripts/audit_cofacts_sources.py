r"""
盤點知識庫中「以 Cofacts 文章當 Tier 1 查核來源」的已證實列（HANDOFF 待辦第 5 項）。

共識 §9：只有已有 RUMOR／NOT_RUMOR 回覆的 Cofacts 文章才算查核機構；還沒有判定的回報貼文是髒資料，
不能讓一筆判定變成「已證實」。2026-09-20 檢查正式知識庫時，128 筆已證實列中約 24 筆的查核來源是這種貼文。

預設 dry-run：逐一向 Cofacts 公開 API 查該文章現在的回覆類型，列出哪些列的 Tier 1 依據其實沒有判定、
修正後會不會變成未證實；另外標出「判定方向相反」者（本列判為詐騙或假訊息，引用的 Cofacts 文章卻只有
NOT_RUMOR 判定），這類只列出、不自動修改，交由人工確認。來源項目已帶 verdict（批次入庫時查過）者不重查。
--apply 才修改：把沒有判定的 Cofacts 來源移到 related_discussions（Tier 3），依寫入門檻
（pandas_store.compute_write_gate）重算 source_tier／verified；rule／gold／admin 的列 verified 不變。
查詢失敗的列不動。--target cloud 讀寫正式資料庫，--apply 前要負責人核准。

    venv\Scripts\python scripts\audit_cofacts_sources.py [--target local|cloud] [--apply]

輸出 data/audit_cofacts_sources_<target>.csv（gitignored）。主控台只印 ASCII 與數字。
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
DATA = BACKEND / "data"
VERDICTS = {"RUMOR", "NOT_RUMOR"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--target", choices=["local", "cloud"], default="local")
    parser.add_argument("--apply", action="store_true", help="actually update rows (default: dry-run)")
    args = parser.parse_args()
    # 在 import app.config 之前決定讀寫哪一份資料（環境變數優先於 .env）
    os.environ["STORAGE_BACKEND"] = "supabase" if args.target == "cloud" else "local"

    import pandas as pd
    from app.config import settings
    from app.services.pandas_store import compute_write_gate
    from app.services.store_factory import get_knowledge_store
    import requests
    from app.utils.source_tier import COFACTS_DOMAINS, COFACTS_GRAPHQL_URL, _host_matches, _host_of, cofacts_article_id

    query = "query($id: String!) { GetArticle(id: $id) { articleReplies(status: NORMAL) { reply { type } } } }"

    def reply_types(article_id: str) -> set:
        resp = requests.post(COFACTS_GRAPHQL_URL, json={"query": query, "variables": {"id": article_id}}, timeout=15)
        resp.raise_for_status()
        article = ((resp.json() or {}).get("data") or {}).get("GetArticle") or {}
        return {((r or {}).get("reply") or {}).get("type") for r in article.get("articleReplies") or []}

    if args.target == "cloud" and not settings.use_supabase:
        print("cloud target needs SUPABASE_DB_URL")
        return 2
    store = get_knowledge_store()
    df = store.get_all_records()
    verified = df[df["verified"]] if not df.empty else df
    print(f"target={args.target} rows={len(df)} verified={len(verified)}")

    def is_cofacts(source) -> bool:
        return isinstance(source, dict) and _host_matches(_host_of(source.get("url") or ""), COFACTS_DOMAINS)

    checks, verdict_cache = [], {}
    for _, row in verified.iterrows():
        sources = [dict(s) for s in (row["sources"] or []) if isinstance(s, dict)]
        suspects = [s for s in sources if is_cofacts(s) and int(s.get("tier") or 0) == 1
                    and s.get("verdict") not in VERDICTS]
        if not suspects:
            continue
        results = {}
        for s in suspects:
            aid = cofacts_article_id(s.get("url") or "")
            if aid not in verdict_cache:
                try:
                    verdict_cache[aid] = reply_types(aid) if aid else set()
                except Exception as exc:  # 查不到 ≠ 沒有判定：這一列先不動
                    verdict_cache[aid] = None
                    print(f"  lookup failed for one article: {type(exc).__name__}")
                time.sleep(0.3)
            results[s.get("url")] = verdict_cache[aid]
        checks.append((row, sources, results))

    records = []
    for row, sources, results in checks:
        if any(v is None for v in results.values()):
            action = "unknown"
            keep, demoted = sources, []
        else:
            demoted = [s for s in sources if s.get("url") in results and not (results[s.get("url")] & VERDICTS)]
            keep = [s for s in sources if s not in demoted]
            action = "demote" if demoted else "ok"
            risky = str(row.get("risk_type") or "").upper() in ("SCAM", "MISINFO")
            only_not_rumor = [u for u, t in results.items() if t and t & VERDICTS == {"NOT_RUMOR"}]
            if action == "ok" and risky and only_not_rumor:
                action = "contradicts"
        graded, tier, now_verified = compute_write_gate(
            keep, row.get("source_url"), row.get("raw_content") or "", label_source=row.get("label_source") or "ai",
        )
        records.append({
            "id": row["id"], "label_source": row.get("label_source"), "risk_type": row.get("risk_type"),
            "raw_content": str(row.get("raw_content") or "")[:80].replace("\n", " "),
            "cofacts_urls": " ".join(u for u in results),
            "reply_types": " ".join("+".join(sorted(t)) if t else ("-" if t is not None else "?") for t in results.values()),
            "action": action, "source_tier_after": tier, "verified_after": now_verified,
            "_keep": graded, "_demoted": demoted, "_row": row,
        })

    out = pd.DataFrame([{k: v for k, v in r.items() if not k.startswith("_")} for r in records])
    DATA.mkdir(exist_ok=True)
    path = DATA / f"audit_cofacts_sources_{args.target}.csv"
    out.to_csv(path, index=False, encoding="utf-8-sig")
    demote = [r for r in records if r["action"] == "demote"]
    print(f"rows citing Cofacts as tier 1 without a stored verdict: {len(records)}")
    print(f"  still backed by a verdict: {sum(r['action'] == 'ok' for r in records)}")
    print(f"  verdict points the other way (NOT_RUMOR only; review by hand): "
          f"{sum(r['action'] == 'contradicts' for r in records)}")
    print(f"  to demote: {len(demote)} (becoming unverified: {sum(not r['verified_after'] for r in demote)})")
    print(f"  lookup failed (left untouched): {sum(r['action'] == 'unknown' for r in records)}")
    print(f"report: {path}")
    if not args.apply or not demote:
        print("dry-run: nothing changed (add --apply)" if demote else "nothing to change")
        return 0

    updated = 0
    for r in demote:
        row = r["_row"]
        related = row.get("related_discussions")
        try:
            related = json.loads(related) if isinstance(related, str) and related else []
        except ValueError:
            related = []
        related = list(related) + [{**s, "tier": 3} for s in r["_demoted"]]
        analysis = row.get("ai_analysis") if isinstance(row.get("ai_analysis"), dict) else {}
        analysis = {**analysis, "sources": r["_keep"]}
        fields = {"sources": r["_keep"], "ai_analysis": analysis, "source_tier": r["source_tier_after"],
                  "verified": bool(r["verified_after"]), "related_discussions": json.dumps(related, ensure_ascii=False)}
        if hasattr(store, "_connect"):
            from sqlalchemy import text

            with store._connect() as conn:
                conn.execute(text(
                    "UPDATE knowledge_base SET sources = CAST(:sources AS jsonb), ai_analysis = CAST(:analysis AS jsonb),"
                    " source_tier = :tier, verified = :verified, related_discussions = :related WHERE id = :id"
                ), {"sources": json.dumps(fields["sources"], ensure_ascii=False),
                    "analysis": json.dumps(fields["ai_analysis"], ensure_ascii=False, default=str),
                    "tier": fields["source_tier"], "verified": fields["verified"],
                    "related": fields["related_discussions"], "id": row["id"]})
        else:
            full = store.get_all_records()
            idx = full.index[full["id"] == row["id"]][0]
            for key, value in fields.items():
                full.at[idx, key] = value
            store._save_knowledge_base(full)
        updated += 1
    print(f"updated {updated} rows")
    return 0


if __name__ == "__main__":
    sys.exit(main())
