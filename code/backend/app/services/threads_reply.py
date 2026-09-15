"""
Threads 回覆模板與長度計數（spec §7.7；純函式，無 I/O）。

回覆格式（共識 §3）：
    {燈} {判定標籤}                 ← 只讀 verdict.frame_of()，不自行查 risk_type（§7.8）
    {summary ≤120 字}
    查核來源：{Tier 1／2 url}       ← 未證實時固定「尚無查核機構證實」
    完整判讀：{PUBLIC_BASE_URL}/r/{id}
    AI 自動判讀，請自行查證。

長度：threads_len() 對 emoji／符號類字元計 UTF-8 bytes、其餘計 1（中文算 1 為推論，
待 live 實測）；目標 THREADS_TARGET_LEN、硬上限 THREADS_TEXT_LIMIT。
截斷順序：summary 截到 60 字加「…」→ 省略第 3 行 → 永不截結果頁連結與免責行。
"""
import unicodedata
from typing import Any, Dict, Iterable, Optional

from app.config import settings
from app.utils.source_tier import tier_of
from app.utils.verdict import (
    LABEL_NO_VERIFIED_SOURCE, LIGHT_GREEN, LIGHT_RED, LIGHT_YELLOW,
    VERIFIED_STATUSES, frame_of,
)

# Threads 單則貼文字數上限（官方：Text posts are limited to 500 characters）
THREADS_TEXT_LIMIT = 500
# 模板目標長度（spec §7.7 預設 400；T-17 實測 480 字＋3 emoji 通過後可改 480）
THREADS_TARGET_LEN = 400

SUMMARY_MAX = 120        # 超過時切到第 118 字並補「…」
SUMMARY_CUT_AT = 118
SUMMARY_SHORT = 60       # 超過目標長度時的第二段截斷

ELLIPSIS = "…"
SOURCE_PREFIX = "查核來源："
RESULT_PREFIX = "完整判讀："
DISCLAIMER = "AI 自動判讀，請自行查證。"

_KEEP_EMOJI = frozenset((LIGHT_RED, LIGHT_YELLOW, LIGHT_GREEN))

# emoji 相關碼位範圍（含變體選擇子、ZWJ、keycap、膚色、旗幟 tag）
_EMOJI_RANGES = (
    (0x1F000, 0x1FAFF),   # 麻將／撲克、符號與圖形、表情、交通、補充符號、旗幟區域字母
    (0x2600, 0x27BF),     # 雜項符號（⚠ U+26A0）、裝飾符號（✅ ✨）
    (0x2300, 0x23FF),     # 雜項技術（⌚ ⏰）
    (0x2B00, 0x2BFF),     # 箭頭補充（⬛ ⭐）
    (0xFE00, 0xFE0F),     # 變體選擇子
    (0x200D, 0x200D),     # ZWJ
    (0x20E3, 0x20E3),     # keycap
    (0xE0020, 0xE007F),   # tag（地區旗幟序列）
)


def _in_emoji_range(ch: str) -> bool:
    cp = ord(ch)
    return any(lo <= cp <= hi for lo, hi in _EMOJI_RANGES)


def threads_len(text: Any) -> int:
    """Threads 長度計數：Unicode 類別 So／Sk 或 emoji 範圍（含 U+FE0F、U+200D）的字元
    計 UTF-8 bytes，其餘（含中文）計 1。"""
    total = 0
    for ch in str(text or ""):
        if _in_emoji_range(ch) or unicodedata.category(ch) in ("So", "Sk"):
            total += len(ch.encode("utf-8"))
        else:
            total += 1
    return total


def strip_emoji(text: Any) -> str:
    """移除 🔴🟡🟢 以外的 emoji（模型偶爾輸出 ⚠️）。只移除 emoji 碼位範圍，
    保留 °、© 等一般符號以免改變語意。"""
    return "".join(
        ch for ch in str(text or "")
        if ch in _KEEP_EMOJI or not _in_emoji_range(ch)
    )


def _clean_summary(summary: Any) -> str:
    # 摺成單行（多行 summary 會打亂模板行序），句末不補標點
    return " ".join(strip_emoji(summary).split())


def _cut(text: str, limit: int, cut_at: int) -> str:
    if len(text) <= limit:
        return text
    return text[:cut_at] + ELLIPSIS


def _source_tier(item: Dict[str, Any]) -> Optional[int]:
    tier = item.get("tier")
    try:
        tier = int(tier) if tier is not None else None
    except (TypeError, ValueError):
        tier = None
    if tier not in (1, 2, 3):
        # 缺 tier 時離線計算（保證無網路 I/O）
        tier = tier_of(str(item.get("url") or ""), str(item.get("title") or ""), offline=True)
    return tier


def first_verified_source_url(sources: Optional[Iterable[Any]]) -> Optional[str]:
    """第一個 Tier 1／2 來源的 url（防禦性再檢查 tier；Tier 3 一律不取）。"""
    for item in sources or []:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or "").strip()
        if url and _source_tier(item) in (1, 2):
            return url
    return None


def _base_url() -> str:
    return (settings.PUBLIC_BASE_URL or "").strip().rstrip("/")


def _default_result_url(result: Dict[str, Any]) -> str:
    rid = ""
    for key in ("id", "result_id", "task_id"):
        if result.get(key):
            rid = str(result[key])
            break
    return f"{_base_url()}/r/{rid}"


def _source_line(result: Dict[str, Any]) -> str:
    if result.get("verification_status") not in VERIFIED_STATUSES:
        return LABEL_NO_VERIFIED_SOURCE
    url = first_verified_source_url(result.get("sources"))
    # rule／verified 狀態下 sources 保證非空（spec §5.3）；萬一沒有 Tier 1／2 仍不放未查證連結
    return f"{SOURCE_PREFIX}{url}" if url else LABEL_NO_VERIFIED_SOURCE


def _assemble(head: str, summary: str, source_line: Optional[str], result_url: str) -> str:
    lines = [head]
    if summary:
        lines.append(summary)
    if source_line:
        lines.append(source_line)
    lines.append(f"{RESULT_PREFIX}{result_url}")
    lines.append(DISCLAIMER)
    return "\n".join(lines)


def format_verdict_reply(
    result: Dict[str, Any],
    result_url: Optional[str] = None,
    without_source_line: bool = False,
) -> str:
    """把分析結果格式化成一則 Threads 回覆（spec §7.7）。

    result_url：結果頁網址（{PUBLIC_BASE_URL}/r/{task_id}）；省略時由設定與
    result 的 id／result_id／task_id 組出。
    without_source_line=True：省略第 3 行（T-13「連結超限」重送用）。
    """
    result = result if isinstance(result, dict) else {}
    _frame_type, label, light = frame_of(result)
    head = f"{light} {label}" if light else label

    url = (result_url or "").strip() or _default_result_url(result)
    summary = _cut(_clean_summary(result.get("summary")), SUMMARY_MAX, SUMMARY_CUT_AT)
    source_line = None if without_source_line else _source_line(result)

    text = _assemble(head, summary, source_line, url)
    if threads_len(text) <= THREADS_TARGET_LEN:
        return text

    # 第一段：summary 截到 60 字加「…」
    summary = _cut(summary, SUMMARY_SHORT, SUMMARY_SHORT)
    text = _assemble(head, summary, source_line, url)
    if threads_len(text) <= THREADS_TARGET_LEN:
        return text

    # 第二段：省略查核來源行（含「尚無查核機構證實」替代行）；結果頁連結與免責行永不截
    return _assemble(head, summary, None, url)


def reply_cannot_read() -> str:
    return (
        f"{LIGHT_YELLOW} 我讀不到這則原貼文（可能是私人帳號、或尚未加入測試名單）。"
        f"請把要查證的文字複製後貼到 {_base_url()} 查證。"
    )


def reply_media_only() -> str:
    return (
        f"{LIGHT_YELLOW} 這則貼文只有圖片或影片，我目前只能查文字。"
        f"請到 {_base_url()} 上傳圖片或貼上文字。"
    )


def reply_too_short() -> str:
    return f"{LIGHT_YELLOW} 這則貼文的文字太短，無法判讀。請貼上完整訊息內容再 @我。"
