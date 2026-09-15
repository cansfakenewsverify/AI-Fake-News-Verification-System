"""
爬蟲服務 - 處理一般網頁 URL（trafilatura + requests 備援）

FR-15：不再以無頭瀏覽器爬封閉平台、不再下載影音；影音 / FB / IG 網址
由 process_input 直接回 unsupported_platform，不發出任何網路請求。
"""
import asyncio
from typing import Dict, Optional, Tuple, Any
from urllib.parse import urlparse
import trafilatura
import requests
from app.config import settings


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
    
    @staticmethod
    async def crawl_url(url: str) -> Dict[str, Any]:
        """
        Pipeline A: 爬取一般網頁內容
        
        Args:
            url: 目標 URL
            
        Returns:
            包含標題、內容、發布時間等資訊的字典
        """
        try:
            # 使用 Trafilatura 爬取（同步網路 IO，丟執行緒避免卡 event loop）
            downloaded = await asyncio.to_thread(trafilatura.fetch_url, url)
            if downloaded:
                extracted = await asyncio.to_thread(
                    trafilatura.extract,
                    downloaded,
                    include_comments=False,
                    include_tables=False,
                )

                if extracted:
                    # 取得標題和元數據
                    metadata = await asyncio.to_thread(trafilatura.extract_metadata, downloaded)
                    raw_author = metadata.author if metadata else None
                    if isinstance(raw_author, list):
                        raw_author = raw_author[0] if raw_author else None
                    result = {
                        'success': True,
                        'url': url,
                        'title': metadata.title if metadata else None,
                        'content': extracted,
                        'author': raw_author,
                        'date': metadata.date if metadata else None,
                        'source': metadata.sitename if metadata else None,
                    }
                    return result

            # 如果 Trafilatura 失敗，嘗試使用 requests + BeautifulSoup
            return await CrawlerService._fallback_crawl(url)
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'url': url
            }
    
    @staticmethod
    async def _fallback_crawl(url: str) -> Dict[str, Any]:
        """
        備用爬取方法（使用 requests）
        """
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            response = await asyncio.to_thread(
                requests.get, url, headers=headers, timeout=settings.CRAWLER_TIMEOUT
            )
            response.raise_for_status()
            
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 移除 script 和 style
            for script in soup(["script", "style"]):
                script.decompose()
            
            title = soup.find('title')
            title_text = title.get_text() if title else None
            
            # 取得主要內容
            content = soup.get_text(separator=' ', strip=True)
            content = ' '.join(content.split()[:settings.MAX_CONTENT_LENGTH])
            
            return {
                'success': True,
                'url': url,
                'title': title_text,
                'content': content,
                'author': None,
                'date': None,
                'source': None
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'url': url
            }

    @staticmethod
    async def search_keyword_and_crawl(keyword: str) -> Dict[str, Any]:
        """F1.3: 關鍵字搜尋並爬取相似新聞"""
        limit = getattr(settings, 'SEARCH_RESULTS_LIMIT', 5)
        try:
            from googlesearch import search
        except ImportError:
            # 套件未安裝（B-03 移除前的過渡期）：不擋文字查證，
            # 直接以使用者原文作為分析內容，形狀同「搜尋無結果」分支。
            search = None
        if search is None:
            return {
                'success': True,
                'url': None,
                'title': None,
                'content': keyword,
                'date': None,
                'source': None,
                'similar_news': [],
            }
        try:
            urls = await asyncio.to_thread(
                lambda: list(search(keyword, num_results=limit, lang='zh-TW'))
            )
        except Exception as e:
            return {
                'success': False,
                'error': f'關鍵字搜尋失敗: {e}',
                'input': keyword,
            }
        if not urls:
            return {
                'success': True,
                'url': None,
                'title': None,
                'content': keyword,
                'date': None,
                'source': None,
                'similar_news': [],
            }
        # 爬取第一個作為主要內容
        first = await CrawlerService.crawl_url(urls[0])
        if not first.get('success'):
            return {
                'success': True,
                'url': urls[0],
                'title': None,
                'content': keyword,
                'date': None,
                'source': None,
                'similar_news': [{'url': u, 'title': None, 'date': None} for u in urls[1:]],
            }
        similar = []
        for u in urls[1:]:
            cr = await CrawlerService.crawl_url(u)
            if cr.get('success'):
                similar.append({
                    'url': cr.get('url'),
                    'title': cr.get('title'),
                    'date': cr.get('date'),
                    'source': cr.get('source'),
                    'content': (cr.get('content') or '')[:500],
                })
            else:
                similar.append({'url': u, 'title': None, 'date': None})
        first['similar_news'] = similar
        return first

    @staticmethod
    async def process_input(input_data: str, input_type: str = 'url') -> Dict[str, Any]:
        """
        統一入口：處理各種類型的輸入
        
        Args:
            input_data: 輸入資料（URL 或關鍵字）
            input_type: 輸入類型（url, keyword）
            
        Returns:
            處理結果字典
        """
        if input_type == 'keyword':
            return await CrawlerService.search_keyword_and_crawl(input_data)

        # URL 處理
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

        res = await CrawlerService.crawl_url(input_data)
            
        # 自動為 URL 結果查找事實查核與網路相關文章
        if res.get('success') and res.get('title'):
            # 利用標題去搜尋可能的事實查核文章
            keyword = f"{res['title']} 事實查核 OR TFC OR MyGoPen"
            fc_res = await CrawlerService.search_keyword_and_crawl(keyword)
            
            # 將搜尋結果整理成 similar_news 陣列
            sim = []
            if fc_res.get('url'):
                sim.append({
                    'url': fc_res.get('url'), 
                    'title': fc_res.get('title'), 
                    'date': fc_res.get('date'), 
                    'content': fc_res.get('content')
                })
            for fallback in fc_res.get('similar_news', []):
                sim.append(fallback)
                
            res['similar_news'] = sim
            
        return res

