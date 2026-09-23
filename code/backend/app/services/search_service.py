"""
SearchService - fetch trending fake-news / fact-check articles from multiple sources.

Sources:
  1. MyGoPen RSS              (Taiwan fact-checker, reliable)
  2. TFC (台灣事實查核中心)    (try multiple URLs)
  3. Cofacts API              (collaborative fact-check, RUMOR-verified only)

Keyword search engines / aggregators are intentionally not used (FR-15):
aggregator items have no fact-check label and are always Tier 3.
"""
import html
import re
import requests
from typing import List, Dict
from urllib.parse import urlparse
from xml.etree import ElementTree as ET


# RSS feeds - direct
RSS_FEEDS = [
    {"url": "https://www.mygopen.com/feeds/posts/default?alt=rss", "name": "MyGoPen"},
    # TFC alternative URLs - we'll try them all and keep what works
    {"url": "https://tfc-taiwan.org.tw/feed/", "name": "TFC"},
    {"url": "https://tfc-taiwan.org.tw/feed", "name": "TFC"},
    {"url": "https://tfc-taiwan.org.tw/?feed=rss2", "name": "TFC"},
]

_SKIP_DOMAINS = {
    "facebook.com", "instagram.com", "twitter.com", "x.com",
    "youtube.com", "tiktok.com", "line.me",
}


def _is_valid_url(url: str) -> bool:
    if not url or not url.startswith("http"):
        return False
    return not any(d in url for d in _SKIP_DOMAINS)


def _is_aggregator_url(url: str) -> bool:
    """Defensive filter used by fetch_rss_items: drop aggregator (Tier 3, unlabeled) items."""
    host = (urlparse(url or "").hostname or "").lower()
    return host == "news.google.com" or host.endswith(".news.google.com")


# 查核機構 RSS 裡不是「查核某個說法」的文章：徵才、每週闢謠排行、小考題。
# 2026-09 資料清洗（FR-18）以人工刪過這幾類；進熱門牆前就擋下，不必再清一次。
_NON_FACTCHECK_TITLE = re.compile(r"(徵才|誠徵|TOP\s*10|小考題|小測驗)", re.IGNORECASE)


def _is_non_factcheck_post(title: str) -> bool:
    return bool(_NON_FACTCHECK_TITLE.search(title or ""))


def _strip_html(text: str) -> str:
    """去 HTML 標籤 + 解碼 entities（&nbsp; &amp; 等，Google News RSS 摘要常見）。"""
    s = re.sub(r"<[^>]+>", "", text or "")
    s = html.unescape(s)
    return s.replace("\xa0", " ").strip()


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
    def fetch_rss_items(num_per_feed: int = 4, include_cofacts: bool = True) -> List[Dict]:
        """Aggregate items from the fact-checker RSS feeds and (unless include_cofacts=False) Cofacts.
        Posts that are not fact-checks of a claim (job ads, weekly top-10 roundups, quizzes) are dropped."""
        all_items = []
        seen_urls = set()
        seen_tfc = False  # only need one working TFC URL

        # ── 台灣事實查核中心：查核報告（REST，判定來自「查核結果」分類）；失敗才讀 RSS ──
        try:
            tfc_items = SearchService._fetch_tfc_reports(num_per_feed)
        except Exception as e:
            print(f"[SearchService] TFC reports API error, falling back to RSS: {e}")
            tfc_items = []
        for it in tfc_items:
            if _is_non_factcheck_post(it.get("title", "")) or it["url"] in seen_urls:
                continue
            seen_urls.add(it["url"])
            all_items.append(it)
        if tfc_items:
            seen_tfc = True
            print(f"[SearchService] TFC reports: +{len(tfc_items)} items")

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
                    if _is_non_factcheck_post(it.get("title", "")):
                        continue
                    if it["url"] not in seen_urls:
                        seen_urls.add(it["url"])
                        all_items.append(it)
                        added += 1
                print(f"[SearchService] {feed['name']}: +{added} items")
            except Exception as e:
                print(f"[SearchService] {feed['name']} error: {e}")

        # ── Cofacts API (collaborative fact-checks) ─────────────
        if not include_cofacts:
            return [it for it in all_items if not _is_aggregator_url(it.get("url", ""))]
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

        # FR-06 acceptance 6: aggregator items must never reach _save_rss_record.
        return [it for it in all_items if not _is_aggregator_url(it.get("url", ""))]

    @staticmethod
    def _fetch_tfc_reports(num: int = 4) -> List[Dict]:
        """
        台灣事實查核中心最新的查核報告（app/services/tfc_client.py）。只收「查核結果」為錯誤或部分錯誤
        （verdict="FALSE"，確定不實，等同 Cofacts 的 RUMOR），且抽得出被查核主張者：claim 優先用同標題的
        謠言原文，其次是標題裡的主張（news_fetcher._claim_for_index）。新版標題寫的是結論（例：「健保署不會用
        LINE 通知健保卡異常」），直接配上「假訊息」會被讀成相反的意思，所以熱門牆顯示「網傳「主張」」。
        謠言原文查不到不影響報告本身。例外往外拋，由呼叫端改讀 RSS。
        """
        from app.services import tfc_client
        from app.services.news_fetcher import _claim_for_index

        reports = tfc_client.latest_reports(num)
        try:
            texts = tfc_client.latest_rumor_texts(max(num * 3, 30))
        except Exception:
            texts = {}
        items = []
        for rep in reports:
            title = rep["title"]
            if not rep["url"] or not title or rep["label"] != "MISINFO":
                continue
            claim = (texts.get(tfc_client.norm_title(title)) or [None])[0] or _claim_for_index(title)
            if not claim:
                continue
            first_line = claim.strip().splitlines()[0]
            short = first_line if len(first_line) <= 50 else first_line[:50] + "…"
            items.append({
                "url": rep["url"],
                "title": title if title.startswith("【") else f"網傳「{short}」",
                "summary": (title + "。" + rep["summary"])[:500],
                "published": rep["published"],
                "source": "TFC",
                "verdict": "FALSE",
                "claim": claim,
            })
        return items

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
