"""
URL validator - filters out 404/dead URLs from AI-returned sources.
Prevents AI hallucinated URLs from reaching users.
"""
import requests
from concurrent.futures import ThreadPoolExecutor
from typing import List, Any


def _is_url_alive(url: str, timeout: float = 3.0) -> bool:
    if not url or not url.startswith(("http://", "https://")):
        return False
    try:
        # HEAD first (fast)
        resp = requests.head(url, timeout=timeout, allow_redirects=True,
                             headers={"User-Agent": "Mozilla/5.0"})
        if resp.status_code < 400:
            return True
        # Some servers don't support HEAD; try GET as fallback
        if resp.status_code in (405, 403):
            resp = requests.get(url, timeout=timeout, allow_redirects=True,
                                headers={"User-Agent": "Mozilla/5.0"}, stream=True)
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
