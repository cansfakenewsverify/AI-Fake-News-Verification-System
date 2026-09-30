"""
查核機構已證實資料的語料規則（MyGoPen、台灣事實查核中心、Cofacts）：抓取、判定標記、主張抽取、去重，
以及寫進知識庫的內容。批次入庫（scripts/ingest_factchecks.py）與每日同步（factcheck_sync.py）共用這一份規則。

只收「已做出判定」的資料（共識 §9、CLAUDE.md 第 9 節；負責人規則：求證平台上還沒有判定的貼文是髒資料，不收）：

| 來源 | 取得方式 | 收錄與標記 |
|------|----------|------------|
| MyGoPen | Blogger 文章 feed（/feeds/posts/summary） | 標題標籤【錯誤／假／謠言／誤導／易誤解／不實】→ MISINFO；【詐騙】→ SCAM；【真…／這真的／還真的／非謠言／非詐騙】→ SAFE；其餘標籤不收 |
| 台灣事實查核中心 | WordPress REST（tfc_client）：查核報告的「查核結果」分類＋謠言原文 | 錯誤、部分錯誤 → MISINFO；正確 → SAFE；事實釐清、證據不足不收。文字優先用同標題的謠言原文 |
| Cofacts | GraphQL ListArticles（文字訊息、至少 N 人回報） | 有 RUMOR 回覆且該回覆正面評價多於負面 → MISINFO；同時有 NOT_RUMOR 回覆（判定矛盾）不收。NOT_RUMOR 獲認可 → SAFE |

主張只收看得出被查核說法者（news_fetcher._claim_for_index）：結論句標題不收，否則會把正確說法標成假訊息。
`use` 欄：`kb` = 可寫入知識庫（只有 MISINFO／SCAM）；`analysis` = 只供分析，**永不寫入知識庫**——詐騙訊息常刻意模仿
官方通知，若讓「已證實為真」的列參與語意命中，仿冒訊息可能以高相似度命中而拿到綠燈（偽陰性，本系統的絕對禁止項）。

抓取函式都接受 `cache(name, fetch)`：預設直接呼叫 fetch（伺服器上的同步）；批次腳本傳入存檔快取，重跑不必重抓。
"""
import hashlib
import html
import logging
import re
import time
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

import requests

logger = logging.getLogger(__name__)

HEADERS = {"User-Agent": "fakenewsverify-ingest/1.0 (+https://fakenewsverify.vercel.app)"}
DELAY_S = 0.6            # 每個請求之間的間隔（對來源網站客氣一點）
EMBED_MAX_CHARS = 2000   # 送 embedding 的文字上限（長篇轉傳文只取前段）
EMBED_BATCH = 64
MIN_TEXT_CHARS = 15

MYGOPEN_FEED = "https://www.mygopen.com/feeds/posts/summary"
MYGOPEN_PAGE = 150
COFACTS_API = "https://api.cofacts.tw/graphql"
COFACTS_PAGE = 50
COFACTS_MIN_REQUESTS = 3                        # 入庫門檻：至少幾人回報（真的在流傳的訊息才收）
COFACTS_SCAM_CATEGORY = "nD2n7nEBrIRcahlYwQoW"   # Cofacts 分類「詐騙」（主題分類，不等於訊息本身是詐騙）

CJK_RE = re.compile(r"[一-鿿]")
TAG_RE = re.compile(r"^【[^】]+】")
# MyGoPen 查核結論為「真」的標籤（【真詐騙】是「確實是詐騙」，不算）
SAFE_TAG_RE = re.compile(r"^【(真(?!詐騙)[^】]*|這真的|還真的)】")

ORIGIN = "factcheck_batch"   # 批次入庫與每日同步寫入列的 origin（scripts/ingest_factchecks.py rollback 以此撤回）
SOURCE_NAMES = {"MyGoPen": "MyGoPen", "TFC": "台灣事實查核中心", "Cofacts": "Cofacts"}
SOURCE_PRIORITY = {"TFC": 0, "MyGoPen": 1, "Cofacts": 2}
COLUMNS = ["source", "kind", "use", "label", "verdict_raw", "text", "content_hash", "url", "title",
           "published", "requests", "scam_topic", "extra"]

Cache = Callable[[str, Callable[[], Any]], Any]


def no_cache(name: str, fetch: Callable[[], Any]) -> Any:
    data = fetch()
    time.sleep(DELAY_S)
    return data


def content_hash(text: str) -> str:
    # 與 app/services/cache_service.CacheService.generate_hash 相同（hash 層命中要一字不差）
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def is_message_text(text: str) -> bool:
    t = (text or "").strip()
    return len(t) >= MIN_TEXT_CHARS and bool(CJK_RE.search(t)) and not t.startswith(("http://", "https://"))


def http_json(method: str, url: str, *, params=None, body=None, allow_400: bool = False) -> Dict[str, Any]:
    """→ {_status, _body, _total_pages}；網路抖動退避重試 3 次。"""
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
        except Exception as exc:
            if attempt == 3:
                raise
            logger.warning("fact-check fetch retry %d after %s", attempt + 1, type(exc).__name__)
            time.sleep(3 * (attempt + 1))
    raise RuntimeError("unreachable")


def _skip(skipped: Optional[dict], key: str) -> None:
    if skipped is not None:
        skipped[key] = skipped.get(key, 0) + 1


# ── MyGoPen ──────────────────────────────────────────────────

def mygopen_entries(cache: Cache = no_cache, max_pages: Optional[int] = None) -> list:
    """Blogger feed 由新到舊；max_pages=None 為全站。"""
    entries, start, page = [], 1, 0
    while max_pages is None or page < max_pages:
        data = cache(f"mygopen_{start:05d}.json", lambda: http_json(
            "GET", MYGOPEN_FEED, params={"alt": "json", "max-results": MYGOPEN_PAGE, "start-index": start})["_body"])
        batch = ((data or {}).get("feed") or {}).get("entry") or []
        if not batch:
            break
        entries.extend(batch)
        start += len(batch)
        page += 1
    return entries


def mygopen_rows(entries: Iterable[dict], skipped: Optional[dict] = None) -> list:
    from app.services import tfc_client
    from app.services.news_fetcher import _NEGATED_VERDICT_RE, _claim_for_index, _is_real_claim, _title_says_false
    from app.services.search_service import _is_non_factcheck_post

    rows = []
    for e in entries:
        title = html.unescape((e.get("title") or {}).get("$t", "")).strip()
        link = next((l.get("href") for l in e.get("link", []) if l.get("rel") == "alternate"), "")
        match = TAG_RE.match(title)
        tag = match.group(0) if match else ""
        if _is_non_factcheck_post(title):
            _skip(skipped, "mygopen:non_factcheck")
            continue
        negated = bool(_NEGATED_VERDICT_RE.search(tag))
        if "詐騙" in tag and not negated:
            label = "SCAM"
        elif _title_says_false(title):
            label = "MISINFO"
        elif negated or SAFE_TAG_RE.match(tag):
            label = "SAFE"
        else:
            _skip(skipped, f"mygopen:tag {tag or '(none)'}")
            continue
        claim = _claim_for_index(title)
        if not _is_real_claim(claim):
            _skip(skipped, "mygopen:no identifiable claim")
            continue
        summary = tfc_client.strip_html((e.get("summary") or {}).get("$t", ""))
        rows.append({"source": "MyGoPen", "kind": "title_claim", "use": "analysis" if label == "SAFE" else "kb",
                     "label": label, "verdict_raw": tag, "text": claim, "url": link, "title": title,
                     "published": (e.get("published") or {}).get("$t", "")[:10],
                     "requests": None, "scam_topic": label == "SCAM", "extra": summary[:300]})
    return rows


# ── 台灣事實查核中心 ─────────────────────────────────────────

def tfc_paged(kind: str, fields: str, cache: Cache = no_cache, max_pages: Optional[int] = None) -> list:
    """WordPress REST 預設由新到舊；max_pages=None 為全部。"""
    from app.services import tfc_client

    items, page = [], 1
    while max_pages is None or page <= max_pages:
        resp = cache(f"tfc_{kind}_{page:04d}.json", lambda: http_json(
            "GET", f"{tfc_client.API}/{kind}", params={"per_page": 100, "page": page, "_fields": fields},
            allow_400=True))
        body = resp.get("_body") or []
        if not body:
            break
        items.extend(body)
        total_pages = resp.get("_total_pages") or 0
        if total_pages and page >= total_pages:
            break
        page += 1
    return items


def tfc_rows(cache: Cache = no_cache, report_pages: Optional[int] = None, rumor_pages: Optional[int] = None,
             skipped: Optional[dict] = None) -> list:
    from app.services import tfc_client
    from app.services.news_fetcher import _claim_for_index, _is_real_claim

    classes = cache("tfc_classes.json", lambda: http_json(
        "GET", f"{tfc_client.API}/fact-check-report-classification",
        params={"per_page": 100, "_fields": "id,slug,name"})["_body"])
    slug_of = {c["id"]: c["slug"] for c in classes}
    reports = tfc_paged("fact-check-reports", tfc_client.REPORT_FIELDS, cache, report_pages)
    rumors = tfc_paged("rumor-sources", tfc_client.RUMOR_FIELDS, cache, rumor_pages)
    rumor_texts = tfc_client.rumor_texts_by_title(rumors)

    rows = []
    for raw in reports:
        rep = tfc_client.report_item(raw, slug_of)
        title, label = rep["title"], rep["label"]
        if label is None:
            _skip(skipped, f"tfc:class {'+'.join(sorted(rep['classification'])) or '(none)'}")
            continue
        base = {"source": "TFC", "use": "kb" if label != "SAFE" else "analysis", "label": label,
                "verdict_raw": "+".join(rep["classification"]), "url": rep["url"], "title": title,
                "published": rep["published"], "requests": None, "scam_topic": False, "extra": rep["summary"][:300]}
        texts = rumor_texts.get(tfc_client.norm_title(title), [])
        if texts:
            rows.extend({**base, "kind": "rumor_text", "text": t} for t in texts)
            continue
        claim = _claim_for_index(title)
        if not _is_real_claim(claim):
            _skip(skipped, "tfc:no identifiable claim")
            continue
        rows.append({**base, "kind": "title_claim", "text": claim})
    return rows


# ── Cofacts ──────────────────────────────────────────────────

COFACTS_QUERY = """
query($after: String, $min: Int, $types: [ReplyTypeEnum], $order: [ListArticleOrderBy]) {
  ListArticles(
    filter: {replyTypes: $types, hasArticleReplyWithMorePositiveFeedback: true,
             replyRequestCount: {GTE: $min}, articleTypes: [TEXT]},
    orderBy: $order, first: 50, after: $after
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
COFACTS_ORDERS = {"requests": [{"replyRequestCount": "DESC"}], "replied": [{"lastRepliedAt": "DESC"}]}


def cofacts_nodes(reply_type: str, min_requests: int, limit: int, cache: Cache = no_cache,
                  order: str = "requests") -> list:
    """order="requests"：最多人回報的在前（批次）；"replied"：最近有新回覆的在前（每日同步）。"""
    nodes, after, page = [], None, 1
    while len(nodes) < limit:
        name = f"cofacts_{reply_type.lower()}_min{min_requests}_{page:04d}.json" if order == "requests" \
            else f"cofacts_{reply_type.lower()}_{order}_min{min_requests}_{page:04d}.json"
        body = {"query": COFACTS_QUERY,
                "variables": {"after": after, "min": min_requests, "types": [reply_type],
                              "order": COFACTS_ORDERS[order]}}
        data = cache(name, lambda: http_json("POST", COFACTS_API, body=body)["_body"])
        if data.get("errors"):
            raise RuntimeError(f"cofacts error: {data['errors']}")
        edges = data["data"]["ListArticles"]["edges"]
        if not edges:
            break
        nodes.extend(e["node"] for e in edges)
        after = edges[-1]["cursor"]
        page += 1
    return nodes[:limit]


def cofacts_rows(nodes: Iterable[dict], want: str, skipped: Optional[dict] = None) -> list:
    """want = RUMOR（MISINFO、可入庫）或 NOT_RUMOR（SAFE、只供分析）。"""
    other = "NOT_RUMOR" if want == "RUMOR" else "RUMOR"
    rows = []
    for n in nodes:
        replies = n.get("articleReplies") or []
        types = [(ar.get("reply") or {}).get("type") for ar in replies]
        endorsed = [ar for ar in replies if (ar.get("reply") or {}).get("type") == want
                    and (ar.get("positiveFeedbackCount") or 0) > (ar.get("negativeFeedbackCount") or 0)]
        if not endorsed:
            _skip(skipped, f"cofacts:{want} reply not endorsed")
            continue
        if other in types:
            _skip(skipped, f"cofacts:{want} conflicting {other}")
            continue
        text = (n.get("text") or "").strip()
        if not is_message_text(text):
            _skip(skipped, "cofacts:not_message_text")
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


# ── 去重與寫入內容 ─────────────────────────────────────────────

def dedupe_rows(rows: Iterable[dict], skipped: Optional[dict] = None) -> List[dict]:
    """同一段文字只留一筆：判定互相矛盾的整組不收；其餘依來源優先序（查核機構 > Cofacts）、發布日新到舊。"""
    by_hash: Dict[str, List[dict]] = {}
    for row in rows:
        text = (row.get("text") or "").strip()
        if not text:
            continue
        row = {**row, "text": text, "content_hash": content_hash(text)}
        by_hash.setdefault(row["content_hash"], []).append(row)
    kept = []
    for group in by_hash.values():
        if len({r["label"] for r in group}) > 1:
            if skipped is not None:
                skipped["dedupe:conflicting labels"] = skipped.get("dedupe:conflicting labels", 0) + len(group)
            continue
        group.sort(key=lambda r: (SOURCE_PRIORITY.get(r["source"], 9), _neg_date(r.get("published"))))
        if skipped is not None and len(group) > 1:
            skipped["dedupe:same text"] = skipped.get("dedupe:same text", 0) + len(group) - 1
        kept.append({col: group[0].get(col) for col in COLUMNS})
    return kept


def _neg_date(published: Any) -> str:
    # 發布日新到舊：把 YYYY-MM-DD 的每一位數反轉，字串遞增排序即為日期遞減
    return "".join(str(9 - int(ch)) if ch.isdigit() else ch for ch in str(published or ""))


def kb_item(row: Dict[str, Any], vector: Iterable[float], now) -> Dict[str, Any]:
    """語料列 → store.save_records 的一筆（label_source=rule：寫入即證實；來源帶 tier 1，寫入時不連網分級）。"""
    name = SOURCE_NAMES[row["source"]]
    text = row["text"]
    short = text if len(text) <= 60 else text[:60] + "…"
    source = {"title": str(row.get("title") or "")[:120], "url": row["url"], "tier": 1}
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
        if row["source"] == "Cofacts" and row.get("extra"):
            explanation = f"Cofacts 查核回應判定此訊息含有不實資訊：「{str(row['extra'])[:200]}」詳見下方查核來源。"
    return {
        "data_type": "TEXT", "raw_content": text, "content_hash": row["content_hash"],
        "content_vector": [float(x) for x in vector],
        "ai_result": {"is_risk": True, "risk_type": row["label"], "category": category, "confidence_score": 0.95,
                      "summary": summary, "explanation": explanation, "sources": [source]},
        "source_url": row["url"], "label_source": "rule", "origin": ORIGIN, "now": now,
    }


# ── CGU：embedding 與用量 ─────────────────────────────────────

def embed_batch(texts: List[str]) -> Tuple[list, int]:
    """一批文字 → (向量 list[np.ndarray float32], tokens)。CGU /embeddings（OpenAI 相容，一次可送多筆）。"""
    import numpy as np
    from app.config import settings

    base = (settings.EMBED_RELAY_URL or "").rstrip("/")
    key = (settings.EMBED_API_KEY or settings.CGU_API_KEY or "").strip()
    if not base or not key:
        raise RuntimeError("embedding is not configured (EMBED_RELAY_URL / EMBED_API_KEY or CGU_API_KEY)")
    payload = {"model": settings.EMBED_MODEL, "input": [t[:EMBED_MAX_CHARS] for t in texts]}
    body = None
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
            logger.warning("embedding retry %d after %s", attempt + 1, type(exc).__name__)
            time.sleep(5 * (attempt + 1))
    vectors = [None] * len(texts)
    for item in body["data"]:
        vectors[item["index"]] = np.asarray(item["embedding"], dtype=np.float32)
    return vectors, int((body.get("usage") or {}).get("total_tokens") or 0)


def cgu_usage() -> Dict[str, float]:
    """CGU openai 池的用量（/me/usage）：{cost_usd, quota_usd, remaining_usd}；查不到的欄位為 -1。每週重置。"""
    from app.config import settings

    out = {"cost_usd": -1.0, "quota_usd": -1.0, "remaining_usd": -1.0}
    key = (settings.CGU_API_KEY or "").strip()
    base = (settings.CGU_BASE_URL or "").rstrip("/")
    if not key or not base:
        return out
    try:
        r = requests.get(f"{base}/me/usage", headers={"Authorization": f"Bearer {key}"}, timeout=20)
        r.raise_for_status()
        pool = r.json().get("openai") or {}
        for field in out:
            if pool.get(field) is not None:
                out[field] = float(pool[field])
    except Exception as exc:
        logger.warning("CGU usage lookup failed: %s", type(exc).__name__)
    return out
