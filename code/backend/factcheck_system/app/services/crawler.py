"""
爬蟲服務 - 處理 URL、影音、圖片等多種輸入格式

專題規格 F1.4: 擷取標題、發布時間、來源媒體、內文、原始新聞截圖
專題規格 F1.3: 依據關鍵字執行搜尋查找相關新聞
"""
import re
import asyncio
import tempfile
import os
from typing import Dict, Optional, Tuple, Any, List
from urllib.parse import urlparse
import trafilatura
import requests
try:
    from playwright.async_api import async_playwright
except ImportError:
    async_playwright = None
try:
    import yt_dlp
except ImportError:
    yt_dlp = None
from app.config import settings


class CrawlerService:
    """爬蟲服務類別"""
    
    # 封閉平台列表（需要 Headless Browser）
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
            # 使用 Trafilatura 爬取
            downloaded = trafilatura.fetch_url(url)
            if downloaded:
                extracted = trafilatura.extract(
                    downloaded,
                    include_comments=False,
                    include_tables=False
                )
                
                if extracted:
                    # 取得標題和元數據
                    metadata = trafilatura.extract_metadata(downloaded)
                    result = {
                        'success': True,
                        'url': url,
                        'title': metadata.title if metadata else None,
                        'content': extracted,
                        'author': metadata.author if metadata else None,
                        'date': metadata.date if metadata else None,
                        'source': metadata.sitename if metadata else None,
                    }
                    if getattr(settings, 'CRAWL_WITH_SCREENSHOT', False) and async_playwright:
                        result = await CrawlerService._add_screenshot(url, result)
                    return result
            
            # 如果 Trafilatura 失敗，嘗試使用 requests + BeautifulSoup
            base = await CrawlerService._fallback_crawl(url)
            if base.get('success') and getattr(settings, 'CRAWL_WITH_SCREENSHOT', False) and async_playwright:
                base = await CrawlerService._add_screenshot(url, base)
            return base
            
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
            response = requests.get(url, headers=headers, timeout=settings.CRAWLER_TIMEOUT)
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
    async def _add_screenshot(url: str, result: Dict[str, Any]) -> Dict[str, Any]:
        """F1.4: 對爬取結果追加原始新聞截圖"""
        try:
            tmpdir = tempfile.gettempdir()
            path = os.path.join(tmpdir, f"screenshot_{abs(hash(url)) % 10**8}.png")
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                await page.set_viewport_size({"width": 1280, "height": 720})
                await page.goto(url, wait_until="domcontentloaded", timeout=15000)
                await page.wait_for_timeout(1500)
                await page.screenshot(path=path, full_page=False)
                await browser.close()
            result['screenshot_path'] = path
        except Exception as e:
            result['screenshot_path'] = None
        return result
    
    @staticmethod
    async def crawl_closed_platform(url: str) -> Dict[str, Any]:
        """
        Pipeline C: 爬取封閉平台（FB/IG）- 使用 Headless Browser 截圖
        
        Args:
            url: 目標 URL
            
        Returns:
            包含截圖路徑和 OCR 文字的字典
        """
        try:
            if async_playwright is None:
                return {
                    'success': False,
                    'error': 'Playwright 未安裝，無法處理封閉平台',
                    'url': url
                }
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                
                # 設定視窗大小
                await page.set_viewport_size({"width": 1920, "height": 1080})
                
                # 訪問頁面
                await page.goto(url, wait_until="networkidle", timeout=30000)
                
                # 等待內容載入
                await page.wait_for_timeout(2000)
                
                # 截圖（使用 tempfile 以跨平台）
                td = tempfile.gettempdir()
                screenshot_path = os.path.join(td, f"screenshot_{abs(hash(url)) % 10**8}.png")
                await page.screenshot(path=screenshot_path, full_page=True)
                
                # 取得頁面文字（部分內容可能可以取得）
                page_text = await page.evaluate("() => document.body.innerText")
                
                await browser.close()
                
                content = (page_text or "")[:settings.MAX_CONTENT_LENGTH]
                return {
                    'success': True,
                    'url': url,
                    'title': None,
                    'content': content,
                    'date': None,
                    'source': 'closed_platform',
                    'screenshot_path': screenshot_path,
                    'platform': 'closed_platform',
                }
                
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'url': url
            }
    
    @staticmethod
    async def download_video(url: str, platform: str) -> Dict[str, Any]:
        """
        Pipeline B: 下載影音並提取資訊
        
        Args:
            url: 影音 URL
            platform: 平台名稱（youtube, tiktok 等）
            
        Returns:
            包含影片資訊、字幕、截圖的字典
        """
        try:
            if yt_dlp is None:
                return {
                    'success': False,
                    'error': 'yt-dlp 未安裝，無法下載影音',
                    'url': url
                }
            # 只取 metadata 與字幕，不下載整支影片
            # （省頻寬、避免 /tmp 在 Windows 失敗；分析只需要逐字稿）
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'skip_download': True,
            }

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)

                # 關鍵：把「影片裡講的話」轉成逐字稿（之前只抓描述）
                transcript = CrawlerService._extract_transcript(info)
                # 無字幕時的後備：下載音軌走 whisper 語音轉文字
                if not transcript:
                    transcript = CrawlerService._stt_from_audio(url)

                desc = (info.get('description') or '')[:settings.MAX_CONTENT_LENGTH]
                title = info.get('title') or ''

                # content 以逐字稿為主，輔以標題與描述，讓 AI 真正分析到影片內容
                parts = []
                if title:
                    parts.append(f"【影片標題】{title}")
                if transcript:
                    parts.append(f"【影片逐字稿】{transcript}")
                if desc:
                    parts.append(f"【影片描述】{desc}")
                content = "\n".join(parts) or str(title or '')

                return {
                    'success': True,
                    'url': url,
                    'platform': platform,
                    'video_path': None,
                    'title': title,
                    'content': content[:settings.MAX_CONTENT_LENGTH],
                    'date': info.get('upload_date'),
                    'source': info.get('uploader'),
                    'duration': info.get('duration'),
                    'has_transcript': bool(transcript),
                    'subtitles': info.get('subtitles') or info.get('automatic_captions') or {},
                    'thumbnail': info.get('thumbnail'),
                }

        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'url': url
            }

    @staticmethod
    def _extract_transcript(info: dict, max_chars: int = 8000) -> str:
        """
        從 yt-dlp info 取出字幕並轉成純文字逐字稿。
        優先：人工字幕 > 自動字幕；語言優先中文 > 英文 > 第一個可用。
        """
        import requests as _rq

        subs = info.get("subtitles") or {}
        auto = info.get("automatic_captions") or {}
        tracks = subs or auto  # 人工字幕優先，沒有才用自動字幕
        if not tracks:
            return ""

        # 選語言
        lang = None
        for pref in ("zh-Hant", "zh-TW", "zh", "zh-Hans", "en", "en-US"):
            if pref in tracks:
                lang = pref
                break
        if lang is None:
            lang = next(iter(tracks))

        fmts = tracks.get(lang) or []
        # 偏好純文字易解析的格式
        chosen = None
        for ext in ("vtt", "srv1", "srv3", "ttml"):
            for f in fmts:
                if f.get("ext") == ext and f.get("url"):
                    chosen = f
                    break
            if chosen:
                break
        if chosen is None and fmts:
            chosen = fmts[0]
        if not chosen or not chosen.get("url"):
            return ""

        try:
            r = _rq.get(chosen["url"], timeout=30)
            r.raise_for_status()
            raw = r.text
        except Exception:
            return ""

        return CrawlerService._parse_subtitle_text(raw)[:max_chars]

    @staticmethod
    def _parse_subtitle_text(raw: str) -> str:
        """把 VTT / TTML 字幕轉成純文字（去時間軸、去標籤、去重複行）。"""
        import re

        lines = []
        for line in raw.splitlines():
            s = line.strip()
            if not s:
                continue
            if s.startswith(("WEBVTT", "NOTE", "Kind:", "Language:")):
                continue
            if "-->" in s:          # 時間軸行
                continue
            if s.isdigit():         # cue 編號
                continue
            s = re.sub(r"<[^>]+>", "", s)   # 去掉 <c>、<00:00:00.000> 等標籤
            s = re.sub(r"&nbsp;", " ", s)
            s = s.strip()
            if s:
                lines.append(s)

        # 去除連續重複（自動字幕常見的滾動重複）
        deduped = []
        for s in lines:
            if not deduped or deduped[-1] != s:
                deduped.append(s)
        return " ".join(deduped)

    @staticmethod
    def _stt_from_audio(url: str, max_chars: int = 8000) -> str:
        """
        無字幕影片的後備：下載最小音軌，走學校中繼 whisper 語音轉文字。
        失敗（無 yt-dlp / 下載失敗 / 檔案過大）一律回空字串，不影響主流程。
        """
        if yt_dlp is None:
            return ""
        import tempfile
        import os as _os

        tmpl = _os.path.join(tempfile.gettempdir(), "fnv_audio_%(id)s.%(ext)s")
        opts = {
            "format": "bestaudio/best",
            "outtmpl": tmpl,
            "quiet": True,
            "no_warnings": True,
        }
        path = None
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
                path = ydl.prepare_filename(info)
            # whisper 單檔上限約 25MB，過大則略過（避免長片失敗）
            if path and _os.path.getsize(path) > 24 * 1024 * 1024:
                return ""
            from app.services.ai_service import AIService
            return (AIService().transcribe_audio(path) or "")[:max_chars]
        except Exception as e:
            print(f"[Crawler] 音訊 STT 後備失敗: {e}")
            return ""
        finally:
            if path and _os.path.exists(path):
                try:
                    _os.remove(path)
                except Exception:
                    pass
    
    @staticmethod
    async def search_keyword_and_crawl(keyword: str) -> Dict[str, Any]:
        """F1.3: 關鍵字搜尋並爬取相似新聞"""
        limit = getattr(settings, 'SEARCH_RESULTS_LIMIT', 5)
        try:
            from googlesearch import search
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
        
        if platform_type == 'video':
            res = await CrawlerService.download_video(input_data, platform_name)
        elif platform_name == 'closed_platform':
            res = await CrawlerService.crawl_closed_platform(input_data)
        else:
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

