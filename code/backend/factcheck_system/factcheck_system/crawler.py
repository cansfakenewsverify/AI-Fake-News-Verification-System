from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from app.services.crawler import CrawlerService


@dataclass(frozen=True)
class CrawlResult:
    success: bool
    url: Optional[str] = None
    title: Optional[str] = None
    content: Optional[str] = None
    date: Optional[str] = None
    source: Optional[str] = None
    screenshot_path: Optional[str] = None
    platform: Optional[str] = None
    similar_news: Optional[list] = None
    raw: Optional[Dict[str, Any]] = None


class CrawlerClient:
    """
    給其他系統使用的 crawler 封裝介面。
    """

    @staticmethod
    async def crawl_url(url: str) -> CrawlResult:
        d = await CrawlerService.process_input(url, "url")
        return CrawlerClient._to_result(d)

    @staticmethod
    async def search_keyword(keyword: str) -> CrawlResult:
        d = await CrawlerService.process_input(keyword, "keyword")
        return CrawlerClient._to_result(d)

    @staticmethod
    def _to_result(d: Dict[str, Any]) -> CrawlResult:
        return CrawlResult(
            success=bool(d.get("success")),
            url=d.get("url"),
            title=d.get("title"),
            content=d.get("content"),
            date=d.get("date"),
            source=d.get("source"),
            screenshot_path=d.get("screenshot_path"),
            platform=d.get("platform"),
            similar_news=d.get("similar_news"),
            raw=d,
        )

