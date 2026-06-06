"""
SearchService - fetch trending fake-news / fact-check articles from multiple sources.

Sources:
  1. MyGoPen RSS              (Taiwan fact-checker, reliable)
  2. TFC (台灣事實查核中心)    (try multiple URLs)
  3. Google News Taiwan RSS   (general news, search-based)
  4. Cofacts API              (collaborative fact-check, optional)
  5. Serper API               (paid keyword search, optional)
"""
import time
import re
import requests
from urllib.parse import quote
from typing import List, Dict
from xml.etree import ElementTree as ET
from app.config import settings


# RSS feeds - direct
RSS_FEEDS = [
    {"url": "https://www.mygopen.com/feeds/posts/default?alt=rss", "name": "MyGoPen"},
    # TFC alternative URLs - we'll try them all and keep what works
    {"url": "https://tfc-taiwan.org.tw/feed/", "name": "TFC"},
    {"url": "https://tfc-taiwan.org.tw/feed", "name": "TFC"},
    {"url": "https://tfc-taiwan.org.tw/?feed=rss2", "name": "TFC"},
]

# Google News RSS searches (gives diverse current news)
GOOGLE_NEWS_QUERIES = [
    "台灣 詐騙 最新",
    "假訊息 闢謠",
    "事實查核",
    "假新聞 台灣",
]

TRENDING_KEYWORDS = [
    "台灣詐騙新聞",
    "假訊息 台灣",
    "投資詐騙",
    "健康謠言",
]

_SKIP_DOMAINS = {
    "facebook.com", "instagram.com", "twitter.com", "x.com",
    "youtube.com", "tiktok.com", "line.me",
}


def _is_valid_url(url: str) -> bool:
    if not url or not url.startswith("http"):
        return False
    return not any(d in url for d in _SKIP_DOMAINS)


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text or "").strip()


_CJK_RE = re.compile(r"[一-鿿]")


def _is_real_text(text: str) -> bool:
    """是否為真正的「訊息文字」：非純網址、夠長、含中文、不是標籤雲。"""
    t = (text or "").strip()
    if not t or t.startswith(("http://", "https://")):
        return False
    if len(t) < 8 or not _CJK_RE.search(t):
        return False
    if t.count(",") >= 8 or t.count("，") >= 8:   # 標籤雲 / 關鍵字列表
        return False
    return True


def _parse_rss_xml(xml_bytes: bytes, source_name: str, num: int) -> List[Dict]:
    """Parse RSS or Atom XML into normalized items."""
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return []

    items = []
    # RSS 2.0
    channel = root.find("channel")
    if channel is not None:
        entries = channel.findall("item")
        for entry in entries[:num]:
            items.append({
                "url": (entry.findtext("link") or "").strip(),
                "title": _strip_html(entry.findtext("title") or "")[:200],
                "summary": _strip_html(entry.findtext("description") or "")[:500],
                "published": entry.findtext("pubDate") or "",
                "source": source_name,
            })
    else:
        # Atom
        ns = "{http://www.w3.org/2005/Atom}"
        entries = root.findall(f".//{ns}entry")
        for entry in entries[:num]:
            link_el = entry.find(f"{ns}link")
            link = link_el.attrib.get("href", "") if link_el is not None else ""
            items.append({
                "url": link.strip(),
                "title": _strip_html(entry.findtext(f"{ns}title") or "")[:200],
                "summary": _strip_html(entry.findtext(f"{ns}summary") or "")[:500],
                "published": entry.findtext(f"{ns}published") or "",
                "source": source_name,
            })
    return [i for i in items if _is_valid_url(i["url"])]


class SearchService:

    @staticmethod
    def fetch_rss_items(num_per_feed: int = 4) -> List[Dict]:
        """Aggregate items from all configured RSS feeds and Google News searches."""
        all_items = []
        seen_urls = set()
        seen_tfc = False  # only need one working TFC URL

        # ── Direct RSS feeds ────────────────────────────────────
        for feed in RSS_FEEDS:
            if feed["name"] == "TFC" and seen_tfc:
                continue
            try:
                resp = requests.get(feed["url"], timeout=10, headers={
                    "User-Agent": "Mozilla/5.0 (FactCheckBot/1.0)"
                })
                if resp.status_code != 200:
                    print(f"[SearchService] {feed['name']} ({feed['url']}): {resp.status_code}")
                    continue
                items = _parse_rss_xml(resp.content, feed["name"], num_per_feed)
                if not items:
                    continue
                if feed["name"] == "TFC":
                    seen_tfc = True
                added = 0
                for it in items:
                    if it["url"] not in seen_urls:
                        seen_urls.add(it["url"])
                        all_items.append(it)
                        added += 1
                print(f"[SearchService] {feed['name']}: +{added} items")
            except Exception as e:
                print(f"[SearchService] {feed['name']} error: {e}")

        # ── Google News RSS searches ────────────────────────────
        for q in GOOGLE_NEWS_QUERIES:
            try:
                gn_url = (
                    f"https://news.google.com/rss/search?q={quote(q)}"
                    f"&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
                )
                resp = requests.get(gn_url, timeout=10, headers={
                    "User-Agent": "Mozilla/5.0"
                })
                if resp.status_code != 200:
                    continue
                items = _parse_rss_xml(resp.content, f"GoogleNews:{q}", num_per_feed)
                added = 0
                for it in items[:num_per_feed]:
                    if it["url"] not in seen_urls:
                        seen_urls.add(it["url"])
                        all_items.append(it)
                        added += 1
                print(f"[SearchService] GoogleNews '{q}': +{added}")
            except Exception as e:
                print(f"[SearchService] GoogleNews '{q}' error: {e}")
            time.sleep(0.5)

        # ── Cofacts API (collaborative fact-checks) ─────────────
        try:
            cofacts_items = SearchService._fetch_cofacts(num=num_per_feed * 2)
            added = 0
            for it in cofacts_items:
                if it["url"] not in seen_urls:
                    seen_urls.add(it["url"])
                    all_items.append(it)
                    added += 1
            print(f"[SearchService] Cofacts: +{added}")
        except Exception as e:
            print(f"[SearchService] Cofacts error: {e}")

        return all_items

    @staticmethod
    def _fetch_cofacts(num: int = 5) -> List[Dict]:
        """
        從 Cofacts 取「已被查核為謠言(RUMOR)」的訊息。
        重點：只收有 RUMOR 回覆的文章（真的被判定為假訊息），而不是剛被提交、
        尚未查證的訊息——後者多半是個人訊息、垃圾或純網址，不能當成已查核假訊息。
        """
        query = """
        query ListArticles($first: Int) {
          ListArticles(
            filter: {replyCount: {GTE: 1}},
            orderBy: [{lastRepliedAt: DESC}],
            first: $first
          ) {
            edges {
              node {
                id
                text
                articleReplies(status: NORMAL) { reply { type } }
              }
            }
          }
        }
        """
        try:
            resp = requests.post(
                "https://api.cofacts.tw/graphql",
                json={"query": query, "variables": {"first": num * 3}},
                timeout=12,
            )
            resp.raise_for_status()
            edges = resp.json().get("data", {}).get("ListArticles", {}).get("edges", [])
            items = []
            for e in edges:
                node = e.get("node", {})
                aid = node.get("id", "")
                text = (node.get("text", "") or "").strip()
                types = {(r.get("reply") or {}).get("type")
                         for r in (node.get("articleReplies") or [])}
                if "RUMOR" not in types:        # 沒有「謠言」判定 → 跳過
                    continue
                if not aid or not _is_real_text(text):
                    continue
                items.append({
                    "url": f"https://cofacts.tw/article/{aid}",
                    "title": text[:120],
                    "summary": text[:500],
                    "published": "",
                    "source": "Cofacts",
                    "verdict": "RUMOR",          # 已查核為謠言
                })
                if len(items) >= num:
                    break
            return items
        except Exception:
            return []

    @staticmethod
    def search_urls(keyword: str, num_results: int = 5) -> List[str]:
        serper_key = getattr(settings, "SERPER_API_KEY", "").strip()
        if serper_key:
            return SearchService._serper_search(keyword, num_results, serper_key)
        return SearchService._google_search(keyword, num_results)

    @staticmethod
    def _serper_search(keyword: str, num: int, api_key: str) -> List[str]:
        try:
            resp = requests.post(
                "https://google.serper.dev/news",
                headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
                json={"q": keyword, "gl": "tw", "hl": "zh-tw", "num": num},
                timeout=10,
            )
            resp.raise_for_status()
            items = resp.json().get("news", [])
            return [i["link"] for i in items if _is_valid_url(i.get("link", ""))][:num]
        except Exception as e:
            print(f"[SearchService] Serper error: {e}")
            return []

    @staticmethod
    def _google_search(keyword: str, num: int) -> List[str]:
        try:
            from googlesearch import search
            urls = []
            for url in search(keyword, num_results=num * 2, lang="zh-TW", sleep_interval=1):
                if _is_valid_url(url):
                    urls.append(url)
                if len(urls) >= num:
                    break
                time.sleep(0.3)
            return urls
        except Exception as e:
            print(f"[SearchService] googlesearch error: {e}")
            return []
