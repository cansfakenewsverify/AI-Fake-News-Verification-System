"""
來源分級（FR-16 / 共識 §9 第 1 點）。

Tier 1「查核機構」：已有判定的查核機構與官方機構網域；Cofacts 文章需有 RUMOR/NOT_RUMOR 回覆。
Tier 2「媒體查核報導」：一般網域，但標題命中 news_fetcher._title_indicates_debunk（不複製規則）。
Tier 3「相關討論（未查證）」：其餘一律。

網域比對一律精確尾綴：host == d or host.endswith("." + d)，不用子字串
（gov.tw.evil.com → Tier 3）。零 AI 成本；唯一網路 I/O 是 Cofacts GraphQL，
且 offline=True 時完全不發請求（供 PandasStore.save_record 使用）。
"""
import asyncio
import re
import time
from functools import lru_cache
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import requests

COFACTS_GRAPHQL_URL = "https://api.cofacts.tw/graphql"
COFACTS_TIMEOUT_SECONDS = 4.0
GRADE_TOTAL_TIMEOUT_SECONDS = 5.0

TIER1_DOMAINS = (
    "tfc-taiwan.org.tw",
    "mygopen.com",
    "gov.tw",
    "who.int",
    "cdc.gov",
)
COFACTS_DOMAINS = ("cofacts.tw", "cofacts.g0v.tw")
# 轉址／社群平台：無論標題為何一律 Tier 3
ALWAYS_TIER3_DOMAINS = ("news.google.com", "threads.com", "threads.net", "facebook.com", "line.me")

TIER_LABELS = {1: "查核機構", 2: "媒體查核報導", 3: "相關討論（未查證）"}

_VERDICT_TYPES = {"RUMOR", "NOT_RUMOR"}
_COFACTS_ARTICLE_RE = re.compile(r"/article/([^/?#]+)")

_ARTICLE_QUERY = """
query GetArticle($id: String!) {
  GetArticle(id: $id) {
    id
    articleReplies(status: NORMAL) { reply { type } }
  }
}
"""


def _host_of(url: str) -> str:
    try:
        parsed = urlparse((url or "").strip())
    except Exception:
        return ""
    if parsed.scheme not in ("http", "https"):
        return ""
    return (parsed.hostname or "").lower().rstrip(".")


def _host_matches(host: str, domains) -> bool:
    return bool(host) and any(host == d or host.endswith("." + d) for d in domains)


def cofacts_article_id(url: str) -> Optional[str]:
    """從 Cofacts 網址取 article id（https://cofacts.tw/article/{id}）。"""
    try:
        path = urlparse(url or "").path
    except Exception:
        return None
    m = _COFACTS_ARTICLE_RE.search(path)
    return m.group(1) if m else None


@lru_cache(maxsize=512)
def _cofacts_verdict_cached(article_id: str) -> bool:
    """實際查詢（有 LRU）。錯誤會 raise，例外不會被 lru_cache 快取，下次可重試。"""
    resp = requests.post(
        COFACTS_GRAPHQL_URL,
        json={"query": _ARTICLE_QUERY, "variables": {"id": article_id}},
        timeout=COFACTS_TIMEOUT_SECONDS,
    )
    resp.raise_for_status()
    data = (resp.json() or {}).get("data") or {}
    article = data.get("GetArticle") or {}
    types = {
        ((r or {}).get("reply") or {}).get("type")
        for r in (article.get("articleReplies") or [])
    }
    return bool(types & _VERDICT_TYPES)


def cofacts_has_verdict(article_id: str) -> bool:
    """Cofacts 文章是否有 RUMOR / NOT_RUMOR 回覆；逾時或任何錯誤視為無回覆（保守）。"""
    if not article_id:
        return False
    try:
        return _cofacts_verdict_cached(str(article_id))
    except Exception:
        return False


cofacts_has_verdict.cache_clear = _cofacts_verdict_cached.cache_clear  # type: ignore[attr-defined]


def _title_tier(title: str) -> int:
    if not (title or "").strip():
        return 3
    # lazy import：避免 news_fetcher → pandas_store → source_tier 循環匯入
    from app.services import news_fetcher

    return 2 if news_fetcher._title_indicates_debunk(title) else 3


def tier_of(url: str, title: str = "", meta: Optional[Dict[str, Any]] = None,
            offline: bool = False) -> int:
    """回傳來源等級 1 / 2 / 3。offline=True 時保證不做任何網路 I/O。"""
    host = _host_of(url)
    if not host:
        return 3
    if _host_matches(host, ALWAYS_TIER3_DOMAINS):
        return 3
    if _host_matches(host, TIER1_DOMAINS):
        return 1
    if _host_matches(host, COFACTS_DOMAINS):
        if offline:
            return 3
        verdict = (meta or {}).get("verdict")
        if verdict in _VERDICT_TYPES:
            return 1
        article_id = (meta or {}).get("article_id") or cofacts_article_id(url)
        return 1 if article_id and cofacts_has_verdict(article_id) else 3
    return _title_tier(title)


def _normalize(source: Any) -> Dict[str, Any]:
    if isinstance(source, dict):
        return dict(source)
    return {"title": "", "url": str(source or "")}


def _with_tier(item: Dict[str, Any], tier: int) -> Dict[str, Any]:
    item["tier"] = tier
    item["tier_label"] = TIER_LABELS[tier]
    return item


async def grade_sources(sources: Optional[List[Any]]
                        ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], int]:
    """
    分級一組來源 → (tiered: Tier 1/2, related: Tier 3, tier_ms)。
    Cofacts 來源並行查詢（to_thread + gather），整組總逾時 5 s；
    逾時當下已完成的查詢照常採用，只有尚未完成者視為 Tier 3。
    """
    start = time.perf_counter()
    items = [_normalize(s) for s in (sources or [])]
    tiers: List[Optional[int]] = []
    pending: Dict[int, str] = {}  # index -> article id

    for idx, item in enumerate(items):
        url = item.get("url") or ""
        title = item.get("title") or ""
        host = _host_of(url)
        is_cofacts = (_host_matches(host, COFACTS_DOMAINS)
                      and not _host_matches(host, ALWAYS_TIER3_DOMAINS))
        if is_cofacts and item.get("verdict") not in _VERDICT_TYPES:
            aid = cofacts_article_id(url)
            if aid:
                pending[idx] = aid
                tiers.append(None)
                continue
        tiers.append(tier_of(url, title, meta=item, offline=not is_cofacts))

    if pending:
        indices = list(pending.keys())

        # 每個查詢各自一個 task；總逾時到時保留「已完成」的結果，只有未完成者視為 Tier 3
        # （不可整批丟棄：快速回 RUMOR 的 Cofacts 不應因同批另一筆慢查詢被降級）。
        tasks = [
            asyncio.ensure_future(asyncio.to_thread(cofacts_has_verdict, pending[i]))
            for i in indices
        ]
        try:
            await asyncio.wait(tasks, timeout=GRADE_TOTAL_TIMEOUT_SECONDS)
        except Exception:
            pass
        for i, task in zip(indices, tasks):
            ok = False
            if task.done() and not task.cancelled():
                try:
                    ok = task.result() is True
                except Exception:
                    ok = False
            else:
                task.cancel()  # 背景執行緒無法中斷，但不再等待其結果
            tiers[i] = 1 if ok else 3

    tiered: List[Dict[str, Any]] = []
    related: List[Dict[str, Any]] = []
    for item, tier in zip(items, tiers):
        graded = _with_tier(item, tier or 3)
        (related if graded["tier"] == 3 else tiered).append(graded)

    tier_ms = int((time.perf_counter() - start) * 1000)
    return tiered, related, tier_ms
