"""
URL validator - filters out 404/dead URLs from AI-returned sources.
Prevents AI hallucinated URLs from reaching users.

B-18: all requests go through app.utils.safe_url (SSRF guard); private /
blocked URLs count as "not alive" and are dropped.
"""
from concurrent.futures import ThreadPoolExecutor
from typing import List, Any

from app.utils.safe_url import safe_get


def _is_url_alive(url: str, timeout: float = 3.0) -> bool:
    # Liveness check keeps its short budget: each safe_get call is capped at
    # `timeout` seconds wall-clock (connect and total), not the crawler's
    # (10, CRAWLER_TIMEOUT). Worst case per source: HEAD + GET fallback = 2 x timeout.
    if not url or not isinstance(url, str) or not url.startswith(("http://", "https://")):
        return False
    limit = (timeout, timeout)
    try:
        # HEAD first (fast)
        resp = safe_get(url, method="HEAD", timeout=limit)
        if resp.status_code < 400:
            return True
        # Some servers don't support HEAD; try GET as fallback
        if resp.status_code in (405, 403):
            resp = safe_get(url, method="GET", read_body=False, timeout=limit)
            return resp.status_code < 400
        return False
    except Exception:
        return False


def filter_valid_sources(sources: List[Any], max_workers: int = 4) -> List[Any]:
    """
    Validate all source URLs in parallel. Drop the dead ones.
    Sources can be strings or dicts with 'url' key.
    """
    if not sources:
        return []

    def get_url(s):
        return s.get("url") if isinstance(s, dict) else s

    urls = [get_url(s) for s in sources]
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        alive = list(ex.map(_is_url_alive, urls))
    return [s for s, ok in zip(sources, alive) if ok]
