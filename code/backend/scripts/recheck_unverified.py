"""查核結果回補的唯讀檢查：列出「尚未證實」的知識庫資料中，哪些已經有查核結果對得上。

用法（從 code/backend）：
    .\\venv\\Scripts\\python scripts\\recheck_unverified.py             # 本機資料＋抓最新查核文章
    .\\venv\\Scripts\\python scripts\\recheck_unverified.py --cloud     # 讀 Supabase 正式資料（只讀）
    .\\venv\\Scripts\\python scripts\\recheck_unverified.py --no-fetch  # 不抓查核文章，只比對知識庫

背景：知識庫中沒有 Tier 1／2 來源的判定以 verified=false 保存。這些列不參與向量層，
但雜湊層與網址層不過濾，所以一字不差的重複查詢會一直拿到當初「尚無查核機構證實」的結果，
即使查核機構之後已經發布查核。本腳本量出這個情況有多少、各自可由什麼證據補上。

每一筆未證實的列，找三種候選中相似度最高者：
  a. 知識庫中已證實的列（依 label_source 分成 AI 判定＋來源，或 rule／gold／admin 確定性標記）；
  b. 最新的查核文章：MyGoPen、TFC 的 RSS 與 Cofacts 已有回覆的文章，
     以 news_fetcher._extract_claim_from_title 取出被查核的主張後計算向量；
  c. 該列本身引用過、當時還沒有回覆的 Cofacts 文章，現在是否已有 RUMOR／NOT_RUMOR 回覆。
取樣與相似度算法與 find_similar_by_vector 相同（1536 維、cosine）。

不呼叫判讀模型、不寫入任何資料：只呼叫 embedding（每篇查核文章一次）與 Cofacts 公開 API。
--cloud 連線時會照常確認資料表存在（CREATE ... IF NOT EXISTS，與後端啟動時相同），不修改任何列。

輸出 data/recheck_unverified_<日期>.csv（已 gitignore：內含使用者送出的原文，不進版本庫）
與主控台摘要。Windows 主控台是 cp950，本檔只印 ASCII 與中文。
"""
import argparse
import csv
import datetime
import io
import json
import os
import re
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)
sys.path.insert(0, BACKEND)

from app.config import settings                                       # noqa: E402
from app.services.news_fetcher import (                               # noqa: E402
    _extract_claim_from_title,
    _is_confirmed_false,
    _title_indicates_debunk,
)
from app.services.search_service import SearchService                 # noqa: E402
from app.services.vector_service import VectorService                 # noqa: E402
from app.utils.source_tier import cofacts_article_id, cofacts_has_verdict  # noqa: E402

DIM = 1536
DETERMINISTIC = ("rule", "gold", "admin")
_TAG_RE = re.compile(r"^【([^】]+)】")
_COFACTS_RE = re.compile(r"cofacts\.tw/article/[^\s\"'<>]+")


def load_kb(cloud: bool) -> pd.DataFrame:
    if cloud:
        from app.services.pg_store import PgKnowledgeStore
        return PgKnowledgeStore().get_all_records(include_vectors=True)
    from app.services.pandas_store import PandasStore
    return PandasStore(os.path.join(BACKEND, "data")).get_all_records()


def as_vector(value):
    if value is None:
        return None
    try:
        a = np.asarray(value, dtype=np.float32)
    except (TypeError, ValueError):
        return None
    return a if a.shape == (DIM,) and np.linalg.norm(a) > 0 else None


def matrix_of(vectors):
    m = np.stack(vectors)
    return m / np.linalg.norm(m, axis=1, keepdims=True)


def tag_verdict(title: str, item: dict) -> str:
    """查核文章的判定：沿用熱門牆的確定性規則；另把【詐騙】標出來（現行規則不收）。"""
    tag = _TAG_RE.match((title or "").strip())
    if tag and "詐騙" in tag.group(1):
        return "SCAM（標題標籤）"
    if _is_confirmed_false(item, title):
        return "MISINFO（標題標籤或 Cofacts 回覆）"
    if _title_indicates_debunk(title):
        return "MISINFO（媒體查核報導）"
    return "未標示判定"


def factcheck_candidates(per_feed: int):
    """抓最新查核文章並算出被查核主張的向量。回傳 (items, matrix)。"""
    items = SearchService.fetch_rss_items(num_per_feed=per_feed)
    vs = VectorService()
    kept, vectors = [], []
    for it in items:
        title = it.get("title") or ""
        claim = _extract_claim_from_title(title) if it.get("source") != "Cofacts" else title
        claim = (claim or "").strip()
        if len(claim) < 6:
            continue
        vec = as_vector(vs.vectorize_content(claim))
        if vec is None:
            continue
        kept.append({**it, "claim": claim, "verdict_label": tag_verdict(title, it)})
        vectors.append(vec)
    return kept, (matrix_of(vectors) if vectors else np.empty((0, DIM), dtype=np.float32))


def cofacts_ids_of(row) -> list:
    """列本身的 sources／related_discussions 中引用過的 Cofacts 文章編號。"""
    blobs = []
    for col in ("sources", "related_discussions"):
        value = row.get(col)
        if value is None or (isinstance(value, float) and np.isnan(value)):
            continue
        if hasattr(value, "tolist"):
            value = value.tolist()
        blobs.append(value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str))
    ids = []
    for url in _COFACTS_RE.findall(" ".join(blobs)):
        aid = cofacts_article_id("https://" + url)
        if aid and aid not in ids:
            ids.append(aid)
    return ids


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cloud", action="store_true", help="讀 Supabase 正式資料（只讀）")
    ap.add_argument("--no-fetch", action="store_true", help="不抓最新查核文章")
    ap.add_argument("--per-feed", type=int, default=25, help="每個 RSS 來源最多取幾篇（預設 25）")
    ap.add_argument("--floor", type=float, default=0.65, help="列入輸出的最低相似度（預設 0.65）")
    args = ap.parse_args()
    threshold = float(settings.SIMILARITY_THRESHOLD)

    df = load_kb(args.cloud)
    df["verified"] = df["verified"].fillna(False).astype(bool)
    df["_vec"] = df["content_vector"].map(as_vector)
    unverified = df[~df["verified"]]
    todo = unverified[unverified["_vec"].notna()]
    verified = df[df["verified"] & df["_vec"].notna()]
    print(f"資料來源：{'Supabase 正式資料' if args.cloud else '本機 data/knowledge_base.parquet'}")
    print(f"未證實 {len(unverified)} 筆，其中有 {DIM} 維向量可比對 {len(todo)} 筆；"
          f"已證實可當候選 {len(verified)} 筆；門檻 {threshold}")
    if todo.empty:
        print("沒有可比對的未證實資料")
        return

    q = matrix_of(list(todo["_vec"]))
    kb_scores = q @ matrix_of(list(verified["_vec"])).T if len(verified) else None

    items, fc_matrix = [], None
    if not args.no_fetch:
        items, fc_matrix = factcheck_candidates(args.per_feed)
        labels = pd.Series([i["verdict_label"] for i in items]).value_counts().to_dict() if items else {}
        print(f"最新查核文章 {len(items)} 篇（" + "、".join(f"{k} {v}" for k, v in labels.items()) + "）")
    fc_scores = q @ fc_matrix.T if items else None

    rows = []
    cofacts_checked = {}
    for n, (_, r) in enumerate(todo.iterrows()):
        out = {
            "kb_id": r["id"],
            "hit_count": int(r.get("hit_count") or 0),
            "last_accessed_at": str(r.get("last_accessed_at") or "")[:19],
            "原判定": r.get("risk_type") or "",
            "原文": str(r.get("raw_content") or "")[:120],
            "已證實資料_相似度": "", "已證實資料_標記": "", "已證實資料_判定": "", "已證實資料_原文": "",
            "查核文章_相似度": "", "查核文章_判定": "", "查核文章_標題": "", "查核文章_網址": "",
            "Cofacts_新回覆": "",
        }
        if kb_scores is not None:
            k = int(np.argmax(kb_scores[n]))
            best = verified.iloc[k]
            out.update({
                "已證實資料_相似度": round(float(kb_scores[n][k]), 4),
                "已證實資料_標記": best.get("label_source") or "ai",
                "已證實資料_判定": best.get("risk_type") or "",
                "已證實資料_原文": str(best.get("raw_content") or "")[:120],
            })
        if fc_scores is not None:
            k = int(np.argmax(fc_scores[n]))
            it = items[k]
            out.update({
                "查核文章_相似度": round(float(fc_scores[n][k]), 4),
                "查核文章_判定": it["verdict_label"],
                "查核文章_標題": it.get("title", "")[:120],
                "查核文章_網址": it.get("url", ""),
            })
        found = []
        for aid in cofacts_ids_of(r):
            if aid not in cofacts_checked:
                cofacts_checked[aid] = cofacts_has_verdict(aid)
            if cofacts_checked[aid]:
                found.append(f"https://cofacts.tw/article/{aid}")
        out["Cofacts_新回覆"] = " ".join(found)
        rows.append(out)

    def best_sim(o):
        return max([s for s in (o["已證實資料_相似度"], o["查核文章_相似度"]) if s != ""] or [0.0])

    for o in rows:
        s = best_sim(o)
        o["最高相似度"] = round(s, 4)
        o["結論"] = ("可回補" if s >= threshold or o["Cofacts_新回覆"]
                     else "接近，需人工判斷" if s >= args.floor else "尚無對應")

    rows.sort(key=lambda o: (-o["hit_count"], -o["最高相似度"]))
    keep = [o for o in rows if o["結論"] != "尚無對應"]

    stamp = datetime.date.today().isoformat()
    path = os.path.join(BACKEND, "data", f"recheck_unverified_{'cloud' if args.cloud else 'local'}_{stamp}.csv")
    with io.open(path, "w", encoding="utf-8-sig", newline="") as f:
        fields = ["結論", "最高相似度"] + [k for k in rows[0] if k not in ("結論", "最高相似度")]
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    # ── 摘要 ──
    kb_hits = [o for o in rows if o["已證實資料_相似度"] != "" and o["已證實資料_相似度"] >= threshold]
    kb_det = [o for o in kb_hits if o["已證實資料_標記"] in DETERMINISTIC]
    kb_flip = [o for o in kb_hits if o["已證實資料_判定"] != o["原判定"]]
    fc_hits = [o for o in rows if o["查核文章_相似度"] != "" and o["查核文章_相似度"] >= threshold]
    co_hits = [o for o in rows if o["Cofacts_新回覆"]]
    print()
    print(f"可回補 {sum(o['結論'] == '可回補' for o in rows)}／{len(rows)}；"
          f"接近需人工判斷 {sum(o['結論'] == '接近，需人工判斷' for o in rows)}；"
          f"尚無對應 {sum(o['結論'] == '尚無對應' for o in rows)}")
    print(f"  對上已證實資料（>= {threshold}）{len(kb_hits)} 筆：其中確定性標記 {len(kb_det)} 筆、"
          f"判定與原本不同 {len(kb_flip)} 筆")
    print(f"  對上最新查核文章（>= {threshold}）{len(fc_hits)} 筆")
    print(f"  引用的 Cofacts 文章已有新回覆 {len(co_hits)} 筆（檢查 {len(cofacts_checked)} 篇）")
    if kb_flip:
        print("  判定會改變的配對（原判定 -> 已證實資料的判定）：")
        for o in kb_flip[:10]:
            print(f"    {o['已證實資料_相似度']:.3f}  {o['原判定']} -> {o['已證實資料_判定']}"
                  f"（{o['已證實資料_標記']}）  {o['原文'][:24]}")
    if keep:
        print("依被查詢次數排序的前 10 筆：")
        for o in keep[:10]:
            print(f"  hit {o['hit_count']:>3}  {o['最高相似度']:.3f}  {o['結論']:<8}  {o['原文'][:28]}")
    print(f"逐筆結果：{os.path.relpath(path, BACKEND)}（內含使用者原文，已 gitignore）")


main()
