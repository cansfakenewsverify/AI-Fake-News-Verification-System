"""
台灣事實查核中心（TFC）WordPress REST API：查核報告的「查核結果」分類與謠言原文。

TFC 的 RSS（/feed/）大多是活動、Podcast 與公告；查核報告是另一個 post type（fact-check-reports），
判定寫在「查核結果」分類（錯誤／部分錯誤／正確／事實釐清／證據不足），新版標題也不再帶【錯誤】標籤。
熱門牆抓取（search_service）與批次入庫（scripts/ingest_factchecks.py）都從這裡讀：
錯誤、部分錯誤 → 確定不實（MISINFO）；正確 → SAFE；事實釐清、證據不足不算判定（CLAUDE.md 第 9 節）。
謠言原文（rumor-sources）與報告同標題，是使用者實際會收到、會貼進來查的文字，所以優先拿它當主張。
"""
import html
import re
from functools import lru_cache
from typing import Any, Dict, Iterable, List, Optional

import requests

API = "https://tfc-taiwan.org.tw/wp-json/wp/v2"
HEADERS = {"User-Agent": "fakenewsverify/1.0 (+https://fakenewsverify.vercel.app)"}
TIMEOUT = 15
REPORT_FIELDS = "id,date,link,title,excerpt,fact-check-report-classification"
RUMOR_FIELDS = "id,date,link,title,content"
LABEL_OF_CLASS = {"incorrect": "MISINFO", "partially-incorrect": "MISINFO", "correct": "SAFE"}
MIN_RUMOR_CHARS = 20          # 謠言原文太短（多半是圖片或影片的配文）就改用標題裡的主張

_NORM_RE = re.compile(r"[\s。．.!！?？、，,「」『』“”\"'（）()：:；;…\-—–|｜]+")
# 新版標題「背景。網傳「主張」說法，結論」：取引號內的主張
_QUOTED_RE = re.compile(r"(?:網傳|流傳|宣稱|傳言|影片稱|貼文稱)[^「]{0,12}「([^」]{6,120})」")
_CJK_RE = re.compile(r"[一-鿿]")


def strip_html(value: Any) -> str:
    text = re.sub(r"<style[^>]*>.*?</style>", " ", str(value or ""), flags=re.S)
    text = re.sub(r"<br\s*/?>|</p>|</div>|</li>", "\n", text, flags=re.I)
    text = html.unescape(re.sub(r"<[^>]+>", " ", text))
    text = re.sub(r"[ \t　\xa0]+", " ", text)
    return re.sub(r"\s*\n\s*", "\n", text).strip()


def norm_title(title: Any) -> str:
    """報告與謠言原文以標題對應：去掉空白與標點再比。"""
    return _NORM_RE.sub("", html.unescape(str(title or "")))


def quoted_claim(title: str) -> Optional[str]:
    match = _QUOTED_RE.search(title or "")
    return match.group(1).strip() if match else None


def label_of(slugs: Iterable[str]) -> Optional[str]:
    """查核結果分類 → MISINFO／SAFE；沒有分類、事實釐清、證據不足或互相矛盾 → None。"""
    labels = {LABEL_OF_CLASS[s] for s in slugs if s in LABEL_OF_CLASS}
    return labels.pop() if len(labels) == 1 else None


def is_rumor_text(text: str) -> bool:
    t = (text or "").strip()
    return len(t) >= MIN_RUMOR_CHARS and bool(_CJK_RE.search(t)) and not t.startswith(("http://", "https://"))


def get_json(kind: str, params: Dict[str, Any]) -> Any:
    resp = requests.get(f"{API}/{kind}", params=params, headers=HEADERS, timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.json()


@lru_cache(maxsize=1)
def classification_slugs() -> Dict[int, str]:
    """查核結果分類的 id → slug（每個行程查一次；失敗不快取，下次重試）。"""
    rows = get_json("fact-check-report-classification", {"per_page": 100, "_fields": "id,slug"})
    return {int(r["id"]): str(r["slug"]) for r in rows}


def report_item(raw: Dict[str, Any], slugs: Dict[int, str]) -> Dict[str, Any]:
    """REST 的一筆查核報告 → {url, title, summary, published, classification, label}。"""
    classes = [slugs.get(i, "") for i in raw.get("fact-check-report-classification") or []]
    return {
        "url": raw.get("link") or "",
        "title": html.unescape(((raw.get("title") or {}).get("rendered")) or "").strip(),
        "summary": strip_html(((raw.get("excerpt") or {}).get("rendered")) or ""),
        "published": (raw.get("date") or "")[:10],
        "classification": classes,
        "label": label_of(classes),
    }


def latest_reports(n: int) -> List[Dict[str, Any]]:
    """最新的 n 篇查核報告（新到舊）。"""
    slugs = classification_slugs()
    rows = get_json("fact-check-reports", {"per_page": max(1, min(int(n), 100)), "_fields": REPORT_FIELDS})
    return [report_item(r, slugs) for r in rows]


def rumor_texts_by_title(rows: Iterable[Dict[str, Any]]) -> Dict[str, List[str]]:
    """謠言原文（rumor-sources 的 REST 列）依正規化標題分組；太短的配文不收。"""
    texts: Dict[str, List[str]] = {}
    for r in rows:
        text = strip_html(((r.get("content") or {}).get("rendered")) or "")
        if is_rumor_text(text):
            texts.setdefault(norm_title((r.get("title") or {}).get("rendered")), []).append(text)
    return texts


def latest_rumor_texts(n: int) -> Dict[str, List[str]]:
    rows = get_json("rumor-sources", {"per_page": max(1, min(int(n), 100)), "_fields": RUMOR_FIELDS})
    return rumor_texts_by_title(rows)
