"""
爬蟲服務 - 處理一般網頁 URL（safe_url.safe_get 抓取 + trafilatura / BeautifulSoup 解析）

FR-15：不再以無頭瀏覽器爬封閉平台、不再下載影音；影音 / FB / IG 網址
由 process_input 直接回 unsupported_platform，不發出任何網路請求。
"""
import asyncio
from typing import Dict, Optional, Tuple, Any
from urllib.parse import urlparse
import trafilatura
from app.config import settings
from app.utils.safe_url import SafeFetchError, safe_get


class CrawlerService:
    """爬蟲服務類別"""
    
    # 封閉平台列表（不支援爬取，回 unsupported_platform）
    CLOSED_PLATFORMS = ['facebook.com', 'instagram.com', 'fb.com', 'm.facebook.com']
    
    # 影音平台列表
    VIDEO_PLATFORMS = {
        'youtube.com': 'youtube',
        'youtu.be': 'youtube',
        'tiktok.com': 'tiktok',
        'instagram.com/reel': 'instagram_reel',
        'facebook.com/watch': 'facebook_video'
    }
    
    @staticmethod
    def detect_platform(url: str) -> Tuple[str, Optional[str]]:
        """
        偵測 URL 平台類型
        
        Args:
            url: 目標 URL
            
        Returns:
            (平台類型, 平台名稱)
            平台類型: 'url', 'video', 'image'
        """
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        path = parsed.path.lower()
        
        # 檢查是否為影音平台
        for platform_key, platform_name in CrawlerService.VIDEO_PLATFORMS.items():
            if platform_key in domain or platform_key in path:
                return ('video', platform_name)
        
        # 檢查是否為封閉平台（需要截圖）
        for closed_platform in CrawlerService.CLOSED_PLATFORMS:
            if closed_platform in domain:
                return ('url', 'closed_platform')
        
        return ('url', 'web')
    
    MIN_CONTENT_CHARS = 50

    @staticmethod
    def _failure(url: str, error_code: str, detail: str = "") -> Dict[str, Any]:
        return {
            'success': False,
            'error_code': error_code,
            'error': detail or error_code,
            'url': url,
        }

    @staticmethod
    async def _safe_fetch(url: str) -> Tuple[Optional[bytes], Optional[Dict[str, Any]]]:
        """經 safe_url 抓回 HTML bytes；失敗時回 (None, failure dict)。"""
        try:
            resp = await asyncio.to_thread(safe_get, url)
        except SafeFetchError as e:
            return None, CrawlerService._failure(url, e.code, e.reason)
        except Exception as e:  # 防呆：任何非預期錯誤都當一般爬取失敗
            return None, CrawlerService._failure(url, 'http_error', str(e))
        if not resp.ok:
            return None, CrawlerService._failure(url, 'http_error', f'HTTP {resp.status_code}')
        return resp.content, None

    @staticmethod
    async def crawl_url(url: str) -> Dict[str, Any]:
        """
        Pipeline A: 爬取一般網頁內容（B-18：一律經 safe_url.safe_get，SSRF 防護）

        Returns:
            成功：{success: True, url, title, content, author, date, source}
            失敗：{success: False, error_code: blocked_url|timeout|too_large|http_error|too_short, error, url}
        """
        html, failure = await CrawlerService._safe_fetch(url)
        if failure:
            return failure
        try:
            extracted = await asyncio.to_thread(
                trafilatura.extract,
                html,
                include_comments=False,
                include_tables=False,
            )
            if extracted and len(extracted.strip()) >= CrawlerService.MIN_CONTENT_CHARS:
                metadata = await asyncio.to_thread(trafilatura.extract_metadata, html)
                raw_author = metadata.author if metadata else None
                if isinstance(raw_author, list):
                    raw_author = raw_author[0] if raw_author else None
                return {
                    'success': True,
                    'url': url,
                    'title': metadata.title if metadata else None,
                    'content': extracted,
                    'author': raw_author,
                    'date': metadata.date if metadata else None,
                    'source': metadata.sitename if metadata else None,
                }
        except Exception:
            pass  # trafilatura 解析失敗 → 退回 BeautifulSoup（不重抓網頁）

        return await CrawlerService._fallback_crawl(url, html)

    @staticmethod
    async def _fallback_crawl(url: str, html: Optional[bytes] = None) -> Dict[str, Any]:
        """
        備用爬取方法（BeautifulSoup）。html 為 None 時自行經 safe_get 抓取。
        """
        if html is None:
            html, failure = await CrawlerService._safe_fetch(url)
            if failure:
                return failure
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, 'html.parser')

            # 移除 script 和 style
            for script in soup(["script", "style"]):
                script.decompose()

            title = soup.find('title')
            title_text = title.get_text() if title else None

            # 取得主要內容
            content = soup.get_text(separator=' ', strip=True)
            content = ' '.join(content.split()[:settings.MAX_CONTENT_LENGTH])
        except Exception as e:
            return CrawlerService._failure(url, 'http_error', str(e))

        if len(content.strip()) < CrawlerService.MIN_CONTENT_CHARS:
            return CrawlerService._failure(url, 'too_short')

        return {
            'success': True,
            'url': url,
            'title': title_text,
            'content': content,
            'author': None,
            'date': None,
            'source': None
        }

    @staticmethod
    async def process_input(input_data: str, input_type: str = 'url') -> Dict[str, Any]:
        """
        統一入口：只處理網址輸入（FR-01：文字輸入不爬、不送搜尋引擎）。

        Args:
            input_data: 目標 URL
            input_type: 只接受 'url'

        Returns:
            處理結果字典
        """
        if input_type != 'url':
            raise ValueError(f"process_input 只支援 url 型別，收到: {input_type}")

        platform_type, platform_name = CrawlerService.detect_platform(input_data)

        # 影音 / 封閉平台（FB、IG）不爬、不下載（FR-15）
        if platform_type == 'video' or platform_name == 'closed_platform':
            return {
                'success': False,
                'error_code': 'unsupported_platform',
                'error': 'unsupported_platform',
                'url': input_data,
                'platform': platform_name,
            }

        return await CrawlerService.crawl_url(input_data)
