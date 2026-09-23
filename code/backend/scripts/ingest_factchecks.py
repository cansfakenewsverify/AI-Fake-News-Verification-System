r"""
查核機構已證實資料的批次語料（MyGoPen、台灣事實查核中心、Cofacts），供知識庫入庫與證據信心分析使用。

只收「已做出判定」的資料（共識 §9、CLAUDE.md 第 9 節；負責人規則：求證平台上還沒有判定的貼文是髒資料，不收）：

| 來源 | 取得方式 | 收錄與標記 |
|------|----------|------------|
| MyGoPen | Blogger 文章 feed（/feeds/posts/summary） | 標題標籤【錯誤／假／謠言／誤導／易誤解／不實】→ MISINFO；【詐騙】→ SCAM；【真…／這真的／還真的／非謠言／非詐騙】→ SAFE；其餘標籤（【查證】【教學】…）不收 |
| 台灣事實查核中心 | WordPress REST：fact-check-reports（「查核結果」分類）＋ rumor-sources（謠言原文） | 錯誤、部分錯誤 → MISINFO；正確 → SAFE；事實釐清、證據不足不收。文字優先用同標題的謠言原文 |
| Cofacts | GraphQL ListArticles（文字訊息、至少 N 人回報） | 有 RUMOR 回覆且該回覆正面評價多於負面 → MISINFO；同時有 NOT_RUMOR 回覆（判定矛盾）不收。有 NOT_RUMOR 回覆且獲正面評價者 → SAFE |

`use` 欄決定用途：`kb` = 可寫入知識庫（只有 MISINFO／SCAM）；`analysis` = 只供信心分析，**永不寫入知識庫**。
SAFE 列一律是 `analysis`：詐騙訊息常刻意模仿官方通知，若讓「已證實為真」的列參與語意命中，
仿冒訊息可能以高相似度命中而拿到綠燈（偽陰性，本系統的絕對禁止項）。

步驟（分開執行、可重跑；原始回應快取在 data/factcheck_raw/，加 --refresh 才重抓）：
  fetch   抓資料 → data/factcheck_corpus.parquet 與抽樣檔 factcheck_corpus_sample.csv（不呼叫 AI、不寫知識庫）
  embed   為語料算向量（CGU embedding；只補還沒有向量的列）
  stats   印出語料統計
  apply   把可入庫列寫進知識庫（label_source=rule → verified，參與語意命中；origin=factcheck_batch）。
          預設 dry-run 只印數量；--apply 才寫。已有相同文字的已證實列、或上次已寫入的列會略過（可重跑）
  rollback  撤回：刪除 origin=factcheck_batch 的列（預設 dry-run；--apply 才刪）

    venv\Scripts\python scripts\ingest_factchecks.py fetch [--refresh] [--cofacts-min-requests 3] [--cofacts-max 9000]
    venv\Scripts\python scripts\ingest_factchecks.py embed [--batch 64]
    venv\Scripts\python scripts\ingest_factchecks.py stats
    venv\Scripts\python scripts\ingest_factchecks.py apply [--target local|cloud] [--sources MyGoPen,TFC,Cofacts] [--limit N] [--apply]
    venv\Scripts\python scripts\ingest_factchecks.py rollback [--target local|cloud] [--apply]

--target cloud 讀寫的是正式資料庫（Supabase），要負責人核准才執行 --apply。

主控台是 cp950：只印 ASCII 與數字，中文內容寫進 UTF-8 檔案。
"""
import argparse
import hashlib
import html
import json
import os
import re
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

HEADERS = {"User-Agent": "fakenewsverify-ingest/1.0 (+https://fakenewsverify.vercel.app)"}
DELAY_S = 0.6            # 每個請求之間的間隔（對來源網站客氣一點）
EMBED_MAX_CHARS = 2000   # 送 embedding 的文字上限（長篇轉傳文只取前段）
MIN_TEXT_CHARS = 15
MIN_RUMOR_CHARS = 20     # 台灣事實查核中心的謠言原文太短（多半是圖片或影片的配文）就改用標題裡的主張

MYGOPEN_FEED = "https://www.mygopen.com/feeds/posts/summary"
TFC_API = "https://tfc-taiwan.org.tw/wp-json/wp/v2"
COFACTS_API = "https://api.cofacts.tw/graphql"
COFACTS_SCAM_CATEGORY = "nD2n7nEBrIRcahlYwQoW"   # Cofacts 分類「詐騙」（主題分類，不等於訊息本身是詐騙）

TFC_LABELS = {"incorrect": "MISINFO", "partially-incorrect": "MISINFO", "correct": "SAFE"}
CJK_RE = re.compile(r"[一-鿿]")
TAG_RE = re.compile(r"^【[^】]+】")
# MyGoPen 查核結論為「真」的標籤（【真詐騙】是「確實是詐騙」，不算）
SAFE_TAG_RE = re.compile(r"^【(真(?!詐騙)[^】]*|這真的|還真的)】")
NORM_RE = re.compile(r"[\s。．.!！?？、，,「」『』“”\"'（）()：:；;…\-—–|｜]+")

ORIGIN = "factcheck_batch"   # 批次入庫列的 origin（rollback 以此撤回）
SOURCE_NAMES = {"MyGoPen": "MyGoPen", "TFC": "台灣事實查核中心", "Cofacts": "Cofacts"}

COLUMNS = ["source", "kind", "use", "label", "verdict_raw", "text", "content_hash", "url", "title",
           "published", "requests", "scam_topic", "extra"]


def log(msg: str) -> None:
    print(msg.encode("ascii", "replace").decode("ascii"), flush=True)


def content_hash(text: str) -> str:
    # 與 app/services/cache_service.CacheService.generate_hash 相同（hash 層命中要一字不差）
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def strip_html(value: str) -> str:
    text = re.sub(r"<style[^>]*>.*?</style>", " ", value or "", flags=re.S)
    text = re.sub(r"<br\s*/?>|</p>|</div>|</li>", "\n", text, flags=re.I)
    text = html.unescape(re.sub(r"<[^>]+>", " ", text))
    text = re.sub(r"[ \t　\xa0]+", " ", text)
    return re.sub(r"\s*\n\s*", "\n", text).strip()


def norm_title(title: str) -> str:
    return NORM_RE.sub("", html.unescape(title or ""))


def is_message_text(text: str) -> bool:
    t = (text or "").strip()
    return len(t) >= MIN_TEXT_CHARS and bool(CJK_RE.search(t)) and not t.startswith(("http://", "https://"))


# ── 原始回應快取 ──────────────────────────────────────────────

def cached(name: str, fetch, refresh: bool):
    path = RAW / name
    if path.exists() and not refresh:
        return json.loads(path.read_text(encoding="utf-8"))
    data = fetch()
    RAW.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    time.sleep(DELAY_S)
    return data


def http_json(method: str, url: str, *, params=None, body=None, allow_400=False):
    import requests

    for attempt in range(4):
        try:
            if method == "POST":
                r = requests.post(url, json=body, headers=HEADERS, timeout=60)
            else:
                r = requests.get(url, params=params, headers=HEADERS, timeout=60)
            if allow_400 and r.status_code == 400:
                return {"_status": 400, "_body": None, "_total_pages": 0}
            r.raise_for_status()
            return {"_status": r.status_code, "_body": r.json(),
                    "_total_pages": int(r.headers.get("X-WP-TotalPages", "0") or 0)}
        except Exception as exc:  # 網路抖動：退避重試
            if attempt == 3:
                raise
            log(f"  retry {attempt + 1} after error: {type(exc).__name__}")
            time.sleep(3 * (attempt + 1))


# ── MyGoPen ──────────────────────────────────────────────────

def fetch_mygopen(refresh: bool) -> list:
    entries, start = [], 1
    while True:
        page = cached(f"mygopen_{start:05d}.json", lambda: http_json(
            "GET", MYGOPEN_FEED, params={"alt": "json", "max-results": 150, "start-index": start})["_body"], refresh)
        batch = ((page or {}).get("feed") or {}).get("entry") or []
        if not batch:
            break
        entries.extend(batch)
        start += len(batch)
    log(f"[mygopen] posts: {len(entries)}")
    return entries


def mygopen_rows(entries: list, skipped: dict) -> list:
    from app.services.news_fetcher import (
        _NEGATED_VERDICT_RE, _extract_claim_from_title, _is_real_claim, _title_says_false,
    )
    from app.services.search_service import _is_non_factcheck_post

    rows = []
    for e in entries:
        title = html.unescape((e.get("title") or {}).get("$t", "")).strip()
        link = next((l.get("href") for l in e.get("link", []) if l.get("rel") == "alternate"), "")
        tag = (TAG_RE.match(title) or [""])[0]
        if _is_non_factcheck_post(title):
            skipped["mygopen:non_factcheck"] = skipped.get("mygopen:non_factcheck", 0) + 1
            continue
        negated = bool(_NEGATED_VERDICT_RE.search(tag))
        if "詐騙" in tag and not negated:
            label = "SCAM"
        elif _title_says_false(title):
            label = "MISINFO"
        elif negated or SAFE_TAG_RE.match(tag):
            label = "SAFE"
        else:
            key = f"mygopen:tag {tag or '(none)'}"
            skipped[key] = skipped.get(key, 0) + 1
            continue
        claim = _extract_claim_from_title(title)
        if not _is_real_claim(claim):
            skipped["mygopen:not_claim"] = skipped.get("mygopen:not_claim", 0) + 1
            continue
        summary = strip_html((e.get("summary") or {}).get("$t", ""))
        use = "analysis" if label == "SAFE" else "kb"
        rows.append({"source": "MyGoPen", "kind": "title_claim", "use": use, "label": label, "verdict_raw": tag,
                     "text": claim, "url": link, "title": title,
                     "published": (e.get("published") or {}).get("$t", "")[:10],
                     "requests": None, "scam_topic": label == "SCAM", "extra": summary[:300]})
    return rows


# ── 台灣事實查核中心 ─────────────────────────────────────────

def tfc_paged(kind: str, fields: str, refresh: bool) -> list:
    items, page = [], 1
    while True:
        resp = cached(f"tfc_{kind}_{page:04d}.json", lambda: http_json(
            "GET", f"{TFC_API}/{kind}", params={"per_page": 100, "page": page, "_fields": fields},
            allow_400=True), refresh)
        body = resp.get("_body") or []
        if not body:
            break
        items.extend(body)
        total_pages = resp.get("_total_pages") or 0
        if total_pages and page >= total_pages:
            break
        page += 1
    return items


def tfc_quoted_claim(title: str) -> str:
    """新版標題「背景。網傳「主張」說法，結論」取引號內的主張；舊版【錯誤】標題沿用 _extract_claim_from_title。"""
    from app.services.news_fetcher import _extract_claim_from_title

    m = re.search(r"(?:網傳|流傳|宣稱|傳言|影片稱|貼文稱)[^「]{0,12}「([^」]{6,120})」", title)
    return m.group(1).strip() if m else _extract_claim_from_title(title)


def fetch_tfc(refresh: bool, skipped: dict) -> list:
    from app.services.news_fetcher import _is_real_claim

    classes = cached("tfc_classes.json", lambda: http_json(
        "GET", f"{TFC_API}/fact-check-report-classification",
        params={"per_page": 100, "_fields": "id,slug,name"})["_body"], refresh)
    slug_of = {c["id"]: c["slug"] for c in classes}
    reports = tfc_paged("fact-check-reports", "id,date,link,title,excerpt,fact-check-report-classification", refresh)
    rumors = tfc_paged("rumor-sources", "id,date,link,title,content", refresh)
    log(f"[tfc] reports: {len(reports)}  rumor-sources: {len(rumors)}")

    rumor_texts = {}
    for r in rumors:
        text = strip_html((r.get("content") or {}).get("rendered", ""))
        if is_message_text(text) and len(text) >= MIN_RUMOR_CHARS:
            rumor_texts.setdefault(norm_title((r.get("title") or {}).get("rendered", "")), []).append(text)

    rows, matched = [], 0
    for rep in reports:
        title = html.unescape((rep.get("title") or {}).get("rendered", "")).strip()
        slugs = [slug_of.get(i, "") for i in rep.get("fact-check-report-classification") or []]
        labels = {TFC_LABELS[s] for s in slugs if s in TFC_LABELS}
        if len(labels) != 1:
            key = f"tfc:class {'+'.join(sorted(slugs)) or '(none)'}"
            skipped[key] = skipped.get(key, 0) + 1
            continue
        label = labels.pop()
        use = "kb" if label != "SAFE" else "analysis"
        base = {"source": "TFC", "use": use, "label": label, "verdict_raw": "+".join(slugs), "url": rep.get("link", ""),
                "title": title, "published": (rep.get("date") or "")[:10], "requests": None, "scam_topic": False,
                "extra": strip_html((rep.get("excerpt") or {}).get("rendered", ""))[:300]}
        texts = rumor_texts.get(norm_title(title), [])
        if texts:
            matched += 1
            rows.extend({**base, "kind": "rumor_text", "text": t} for t in texts)
            continue
        claim = tfc_quoted_claim(title)
        if not _is_real_claim(claim):
            skipped["tfc:not_claim"] = skipped.get("tfc:not_claim", 0) + 1
            continue
        rows.append({**base, "kind": "title_claim", "text": claim})
    log(f"[tfc] reports with rumor text: {matched}")
    return rows


# ── Cofacts ──────────────────────────────────────────────────

COFACTS_QUERY = """
query($after: String, $min: Int, $types: [ReplyTypeEnum]) {
  ListArticles(
    filter: {replyTypes: $types, hasArticleReplyWithMorePositiveFeedback: true,
             replyRequestCount: {GTE: $min}, articleTypes: [TEXT]},
    orderBy: [{replyRequestCount: DESC}], first: 50, after: $after
  ) {
    totalCount
    edges {
      cursor
      node {
        id text createdAt replyRequestCount
        articleCategories(status: NORMAL) { categoryId }
        articleReplies(status: NORMAL) { positiveFeedbackCount negativeFeedbackCount reply { type text } }
      }
    }
  }
}
"""


def fetch_cofacts(reply_type: str, min_requests: int, limit: int, refresh: bool) -> list:
    nodes, after, page = [], None, 1
    while len(nodes) < limit:
        name = f"cofacts_{reply_type.lower()}_min{min_requests}_{page:04d}.json"
        body = {"query": COFACTS_QUERY, "variables": {"after": after, "min": min_requests, "types": [reply_type]}}
        data = cached(name, lambda: http_json("POST", COFACTS_API, body=body)["_body"], refresh)
        if data.get("errors"):
            raise RuntimeError(f"cofacts error: {data['errors']}")
        edges = data["data"]["ListArticles"]["edges"]
        if not edges:
            break
        nodes.extend(e["node"] for e in edges)
        after = edges[-1]["cursor"]
        page += 1
    log(f"[cofacts] {reply_type} articles fetched: {len(nodes)}")
    return nodes[:limit]


def cofacts_rows(nodes: list, want: str, skipped: dict) -> list:
    """want = RUMOR（MISINFO、可入庫）或 NOT_RUMOR（SAFE、只供分析）。"""
    other = "NOT_RUMOR" if want == "RUMOR" else "RUMOR"
    rows = []
    for n in nodes:
        replies = n.get("articleReplies") or []
        types = [(ar.get("reply") or {}).get("type") for ar in replies]
        endorsed = [ar for ar in replies if (ar.get("reply") or {}).get("type") == want
                    and (ar.get("positiveFeedbackCount") or 0) > (ar.get("negativeFeedbackCount") or 0)]
        if not endorsed:
            skipped[f"cofacts:{want} reply not endorsed"] = skipped.get(f"cofacts:{want} reply not endorsed", 0) + 1
            continue
        if other in types:
            skipped[f"cofacts:{want} conflicting {other}"] = skipped.get(f"cofacts:{want} conflicting {other}", 0) + 1
            continue
        text = (n.get("text") or "").strip()
        if not is_message_text(text):
            skipped["cofacts:not_message_text"] = skipped.get("cofacts:not_message_text", 0) + 1
            continue
        best = max(endorsed, key=lambda ar: (ar.get("positiveFeedbackCount") or 0) - (ar.get("negativeFeedbackCount") or 0))
        cats = {c.get("categoryId") for c in n.get("articleCategories") or []}
        rows.append({"source": "Cofacts", "kind": "article_text", "use": "kb" if want == "RUMOR" else "analysis",
                     "label": "MISINFO" if want == "RUMOR" else "SAFE", "verdict_raw": want, "text": text,
                     "url": f"https://cofacts.tw/article/{n['id']}", "title": text[:80],
                     "published": (n.get("createdAt") or "")[:10], "requests": n.get("replyRequestCount"),
                     "scam_topic": COFACTS_SCAM_CATEGORY in cats,
                     "extra": ((best.get("reply") or {}).get("text") or "")[:300]})
    return rows


# ── 指令 ─────────────────────────────────────────────────────

SOURCE_PRIORITY = {"TFC": 0, "MyGoPen": 1, "Cofacts": 2}


def cmd_fetch(args) -> int:
    import pandas as pd

    skipped: dict = {}
    rows = mygopen_rows(fetch_mygopen(args.refresh), skipped)
    rows += fetch_tfc(args.refresh, skipped)
    rows += cofacts_rows(fetch_cofacts("RUMOR", args.cofacts_min_requests, args.cofacts_max, args.refresh),
                         "RUMOR", skipped)
    rows += cofacts_rows(fetch_cofacts("NOT_RUMOR", args.cofacts_min_requests, args.cofacts_max, args.refresh),
                         "NOT_RUMOR", skipped)

    df = pd.DataFrame(rows)
    df["text"] = df["text"].str.strip()
    df["content_hash"] = df["text"].map(content_hash)
    # 同一段文字只留一筆：判定互相矛盾的整組不收；其餘依來源優先序（查核機構 > Cofacts）
    labels_per_hash = df.groupby("content_hash")["label"].nunique()
    conflict = df["content_hash"].map(labels_per_hash) > 1
    skipped["dedupe:conflicting labels"] = int(conflict.sum())
    df = df[~conflict]
    before = len(df)
    df = (df.assign(_p=df["source"].map(SOURCE_PRIORITY))
            .sort_values(["_p", "published"], ascending=[True, False])
            .drop_duplicates("content_hash").drop(columns="_p"))
    skipped["dedupe:same text"] = before - len(df)
    df = df[COLUMNS].reset_index(drop=True)

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


def cgu_cost_usd() -> float:
    """CGU openai 池累計花費（/me/usage；查不到回 -1）。與 scripts/batch_verify_pending.py 相同。"""
    import requests
    from app.config import settings

    key = (settings.CGU_API_KEY or "").strip()
    base = (settings.CGU_BASE_URL or "").rstrip("/")
    if not key or not base:
        return -1.0
    try:
        r = requests.get(f"{base}/me/usage", headers={"Authorization": f"Bearer {key}"}, timeout=20)
        r.raise_for_status()
        return float(r.json().get("openai", {}).get("cost_usd", -1.0))
    except Exception:
        return -1.0


def embed_batch(texts: list) -> tuple:
    """一批文字 → (向量 list[np.ndarray float32], tokens)。CGU /embeddings（OpenAI 相容，一次可送多筆）。"""
    import numpy as np
    import requests
    from app.config import settings

    base = (settings.EMBED_RELAY_URL or "").rstrip("/")
    key = (settings.EMBED_API_KEY or settings.CGU_API_KEY or "").strip()
    if not base or not key:
        raise RuntimeError("embedding is not configured (EMBED_RELAY_URL / EMBED_API_KEY or CGU_API_KEY)")
    payload = {"model": settings.EMBED_MODEL, "input": [t[:EMBED_MAX_CHARS] for t in texts]}
    for attempt in range(4):
        try:
            r = requests.post(f"{base}/embeddings", headers={"Authorization": f"Bearer {key}"},
                              json=payload, timeout=120)
            r.raise_for_status()
            body = r.json()
            break
        except Exception as exc:
            if attempt == 3:
                raise
            log(f"  retry {attempt + 1}: {type(exc).__name__}")
            time.sleep(5 * (attempt + 1))
    vectors = [None] * len(texts)
    for item in body["data"]:
        vectors[item["index"]] = np.asarray(item["embedding"], dtype=np.float32)
    return vectors, int((body.get("usage") or {}).get("total_tokens") or 0)


def cmd_embed(args) -> int:
    import pandas as pd

    df = pd.read_parquet(CORPUS)
    todo = [i for i in df.index if df.at[i, "vector"] is None or (isinstance(df.at[i, "vector"], float))]
    log(f"to embed: {len(todo)} / {len(df)}")
    cost_before = cgu_cost_usd()
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
    # text-embedding-3-small 牌價 USD 0.02／百萬 tokens；實際扣款以 CGU /me/usage 為準
    cost_after = cgu_cost_usd()
    log(f"done. tokens={tokens}  list-price estimate USD {tokens * 0.02 / 1e6:.4f}  "
        f"CGU cost_usd before={cost_before:.4f} after={cost_after:.4f}")
    return 0


def kb_item(row, now) -> dict:
    """語料列 → store.save_records 的一筆（label_source=rule：寫入即證實；來源帶 tier 1，寫入時不連網分級）。"""
    name = SOURCE_NAMES[row["source"]]
    text = row["text"]
    short = text if len(text) <= 60 else text[:60] + "…"
    source = {"title": str(row["title"] or "")[:120], "url": row["url"], "tier": 1}
    if row["source"] == "Cofacts":
        source.update({"title": "Cofacts 查核回應", "verdict": "RUMOR"})
    if row["label"] == "SCAM":
        category = "已查核詐騙"
        summary = f"此為查核機構已證實的詐騙手法：「{short}」"
        explanation = f"{name} 已查證此為詐騙手法。請勿點擊連結、勿提供個資或匯款，並參考下方查核來源。"
    else:
        category = "已查核假訊息"
        summary = f"此為已被查核的假訊息：「{short}」"
        explanation = f"{name} 已對此訊息進行查證，判定為假訊息或誤導內容。建議勿轉傳，並參考下方查核來源了解事實。"
        if row["source"] == "Cofacts" and row["extra"]:
            explanation = f"Cofacts 查核回應判定此訊息含有不實資訊：「{str(row['extra'])[:200]}」詳見下方查核來源。"
    return {
        "data_type": "TEXT", "raw_content": text, "content_hash": row["content_hash"],
        "content_vector": [float(x) for x in row["vector"]],
        "ai_result": {"is_risk": True, "risk_type": row["label"], "category": category, "confidence_score": 0.95,
                      "summary": summary, "explanation": explanation, "sources": [source]},
        "source_url": row["url"], "label_source": "rule", "origin": ORIGIN, "now": now,
    }


def cmd_apply(args) -> int:
    from datetime import datetime, timedelta

    import pandas as pd
    from app.config import settings
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
    existing = store.get_all_records()
    skip = set()
    if not existing.empty:
        mask = existing["verified"] | (existing["origin"] == ORIGIN)
        skip = set(existing.loc[mask, "data_hash"].dropna())
    fresh = rows[~rows["content_hash"].isin(skip)]
    todo = fresh.sort_values("published", kind="mergesort")
    if args.limit:
        todo = todo.head(args.limit)
    log(f"target={args.target} ({type(store).__name__})  existing rows={len(existing)}  "
        f"candidates={len(rows)}  already present={len(rows) - len(fresh)}")
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
        items = [kb_item(r, start + timedelta(microseconds=offset + i)) for i, (_, r) in enumerate(chunk.iterrows())]
        written += store.save_records(items)
        log(f"  written {written}/{len(todo)}")
    log(f"done: {written} rows written with origin={ORIGIN}")
    return 0


def cmd_rollback(args) -> int:
    from sqlalchemy import text

    from app.config import settings
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
    f.add_argument("--cofacts-min-requests", type=int, default=3)
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
