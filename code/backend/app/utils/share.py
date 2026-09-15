"""
分享文案（spec §7.7 分享文案、FR-05 Web Intent text；url 另帶）。

build_share(result, result_id) -> {"text", "url"} | None
- 只讀 frame_type / frame_label（spec §7.8 單一權威），不自行由 risk_type 推燈色。
- {summary≤80}：超過 80 字時截為 79 字並補「…」（與前端 i18n.t 同規則）。
- {source_domain} 只取 Tier 1／2 來源的網域；verification_status 非 verified/rule
  （或找不到 Tier 1／2 網域）時，紅燈文案去掉「。查核來源：{source_domain}」尾段（FR-16）。
- ai_unavailable / grey → None（spec §5.3：share=null）。
- url = {PUBLIC_BASE_URL}/r/{id}；PUBLIC_BASE_URL 為空時退用請求的 base URL
  （result.py 傳入，會參考 X-Forwarded-Proto/Host）；仍無絕對網址 → None。
  啟動時 main.py 呼叫 warn_if_public_base_url_missing() 記 warning。
"""
import logging
from typing import Any, Dict, Optional
from urllib.parse import urlparse

from app.config import settings
from app.utils.source_tier import tier_of
from app.utils.verdict import (
    LABEL_NO_VERIFIED_SOURCE, LABEL_SCAM, VERIFIED_STATUSES,
    LIGHT_GREEN, LIGHT_RED, LIGHT_YELLOW,
)

logger = logging.getLogger(__name__)

SUMMARY_MAX = 80
SHARE_TEXT_MAX = 200
SOURCE_TAIL = "。查核來源：{source_domain}"

# spec §7.7 逐字（與 code/frontend/src/i18n.js 同 key）
SHARE_TEMPLATES: Dict[str, str] = {
    "share_text_red_scam": LIGHT_RED + " AI 判定這則訊息是詐騙：{summary}" + SOURCE_TAIL,
    "share_text_red_misinfo": LIGHT_RED + " AI 判定這則訊息是假訊息：{summary}" + SOURCE_TAIL,
    "share_text_yellow": LIGHT_YELLOW + " 這則訊息 AI 尚無法確認：{summary}。轉傳前請先查證",
    "share_text_green": LIGHT_GREEN + " AI 查證這則訊息沒有發現異常：{summary}",
    "share_text_yellow_unverified": LIGHT_YELLOW + " 這則訊息尚無查核機構證實：{summary}。轉傳前請先查證",
}

_TRAILING_PUNCT = "。．.，,；;！!？?、 　"


def share_key(result: Dict[str, Any]) -> Optional[str]:
    """依 frame_type / frame_label 選分享文案 key；grey 或 ai_unavailable → None。"""
    if not isinstance(result, dict) or result.get("ai_unavailable") is True:
        return None
    frame_type = result.get("frame_type")
    frame_label = result.get("frame_label")
    if frame_type == "red":
        if frame_label == LABEL_SCAM:
            return "share_text_red_scam"
        # 「假訊息」與「風險訊息」（其他風險類型；7.7 未另訂文案）共用假訊息文案
        return "share_text_red_misinfo"
    if frame_type == "yellow":
        if frame_label == LABEL_NO_VERIFIED_SOURCE:
            return "share_text_yellow_unverified"
        return "share_text_yellow"
    if frame_type == "green":
        return "share_text_green"
    return None


def truncate_summary(summary: Any, limit: int = SUMMARY_MAX) -> str:
    text = " ".join(str(summary or "").split())
    text = text.rstrip(_TRAILING_PUNCT)
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)] + "…"


def _domain(url: str) -> str:
    try:
        host = (urlparse((url or "").strip()).hostname or "").lower().rstrip(".")
    except ValueError:
        return ""
    return host[4:] if host.startswith("www.") else host


def source_domain(result: Dict[str, Any]) -> Optional[str]:
    """第一個 Tier 1／2 來源的網域（防禦性再檢查 tier；缺 tier 時離線計算）。"""
    for item in result.get("sources") or []:
        if not isinstance(item, dict):
            continue
        url = item.get("url") or ""
        tier = item.get("tier")
        try:
            tier = int(tier) if tier is not None else None
        except (TypeError, ValueError):
            tier = None
        if tier not in (1, 2, 3):
            tier = tier_of(url, item.get("title") or "", offline=True)
        if tier in (1, 2):
            domain = _domain(url)
            if domain:
                return domain
    return None


def configured_base_url() -> str:
    return (settings.PUBLIC_BASE_URL or "").strip().rstrip("/")


def warn_if_public_base_url_missing() -> bool:
    """啟動時呼叫：PUBLIC_BASE_URL 未設定 → 記 warning（分享連結改用請求網址推算）。"""
    if configured_base_url():
        return False
    logger.warning(
        "PUBLIC_BASE_URL is empty: share links will fall back to the request base URL; "
        "set PUBLIC_BASE_URL (e.g. https://xxx.vercel.app) for correct Threads share/OG links"
    )
    return True


def share_url(result_id: str, fallback_base_url: Optional[str] = None) -> Optional[str]:
    """{PUBLIC_BASE_URL}/r/{id}；未設定時用 fallback_base_url（請求網址）；兩者皆無 → None。"""
    base = configured_base_url() or (fallback_base_url or "").strip().rstrip("/")
    if not base.lower().startswith(("http://", "https://")):
        return None
    return f"{base}/r/{result_id}"


def build_share(
    result: Optional[Dict[str, Any]], result_id: str, fallback_base_url: Optional[str] = None,
) -> Optional[Dict[str, str]]:
    key = share_key(result or {})
    if key is None:
        return None
    url = share_url(result_id, fallback_base_url)
    if url is None:
        # 無法組出絕對網址（Threads Web Intent 需要）→ share=null，而非回傳相對路徑
        return None
    template = SHARE_TEMPLATES[key]
    summary = truncate_summary(result.get("summary"))
    if SOURCE_TAIL in template:
        domain = source_domain(result)
        verified = result.get("verification_status") in VERIFIED_STATUSES
        if verified and domain:
            template = template.replace("{source_domain}", domain)
        else:
            template = template.replace(SOURCE_TAIL, "")
    # 用 replace 而非 format：summary 內可能含 { }
    text = template.replace("{summary}", summary)
    if len(text) > SHARE_TEXT_MAX:
        text = text[: SHARE_TEXT_MAX - 1] + "…"
    return {"text": text, "url": url}
