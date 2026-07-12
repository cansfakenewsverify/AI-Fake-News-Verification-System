"""
Threads API 客戶端 — 查核機器人（延伸功能）用。

官方 API：https://developers.facebook.com/docs/threads
需要的權限：threads_basic、threads_content_publish、
threads_read_replies、threads_manage_replies（mentions 相關權限以官方文件為準）。

注意：
- 所有方法都是「同步 requests」，在 async 流程中呼叫要包 asyncio.to_thread
  （同 ai_service 的慣例，避免卡 event loop）。
- 端點名稱依 2026-01 的官方文件實作；Meta 改版時只需要改這個檔。
- 回覆有 500 字上限（format_verdict_reply 已處理截斷）。
"""
from typing import Any, Dict, List, Optional

import requests

from app.config import settings

# Threads 單則貼文的字數上限
THREADS_TEXT_LIMIT = 500

_RISK_LABEL = {
    "SCAM": ("[紅燈] 詐騙警告", "這則訊息具有詐騙特徵，請勿點擊連結或提供個資！"),
    "MISINFO": ("[紅燈] 假訊息", "這則訊息經查核為不實或誤導內容，請勿轉傳。"),
    "SAFE": ("[綠燈] 查無異常", "這則訊息與可信來源相符。"),
    "UNKNOWN": ("[黃燈] 尚待確認", "目前查證資料不足，請多方查證後再分享。"),
}


def format_verdict_reply(result: Dict[str, Any]) -> str:
    """
    把分析結果（pandas_task_processor._build_result 的輸出）格式化成
    一則 Threads 回覆（<=500 字）。
    """
    risk = (result.get("risk_type") or "UNKNOWN").upper()
    label, advice = _RISK_LABEL.get(risk, _RISK_LABEL["UNKNOWN"])

    lines = [f"AI 查核結果：{label}"]
    level = result.get("confidence_level")
    if level:
        lines.append(f"判定信心：{level}（模型自評，未經校準）")

    explain = (result.get("explanation") or result.get("summary") or "").strip()
    if explain:
        lines.append(explain)
    lines.append(advice)

    # 附上第一個真實查核來源（sources 已過 url_validator 濾掉幻覺連結）
    for s in result.get("sources") or []:
        url = s.get("url") if isinstance(s, dict) else s
        if url:
            lines.append(f"查核來源：{url}")
            break

    lines.append("— 全民查證公社自動查核，僅供參考")

    # 截斷：優先砍說明文字，確保結尾聲明與來源保留
    text = "\n".join(lines)
    if len(text) > THREADS_TEXT_LIMIT and explain:
        overflow = len(text) - THREADS_TEXT_LIMIT
        explain_cut = explain[: max(20, len(explain) - overflow - 1)] + "…"
        lines[lines.index(explain)] = explain_cut
        text = "\n".join(lines)
    return text[:THREADS_TEXT_LIMIT]


class ThreadsService:
    """Threads Graph API 薄封裝。沒設 token/user_id 時 available=False，一律跳過。"""

    def __init__(self):
        self.base = (settings.THREADS_BASE_URL or "").rstrip("/")
        self.token = (settings.THREADS_ACCESS_TOKEN or "").strip()
        self.user_id = (settings.THREADS_USER_ID or "").strip()

    @property
    def available(self) -> bool:
        return bool(self.base and self.token and self.user_id)

    # ── HTTP helpers ─────────────────────────────────────────────
    def _get(self, path: str, **params) -> Dict[str, Any]:
        params["access_token"] = self.token
        r = requests.get(f"{self.base}/{path}", params=params, timeout=30)
        r.raise_for_status()
        return r.json()

    def _post(self, path: str, **params) -> Dict[str, Any]:
        params["access_token"] = self.token
        r = requests.post(f"{self.base}/{path}", data=params, timeout=30)
        r.raise_for_status()
        return r.json()

    # ── 讀取 ─────────────────────────────────────────────────────
    def get_profile(self) -> Dict[str, Any]:
        """驗證 token 用：回機器人自己的 id/username。"""
        return self._get("me", fields="id,username")

    def get_mentions(self, limit: int = 25) -> List[Dict[str, Any]]:
        """抓最近被 @ 提及的貼文（別人 tag 機器人請求查核）。"""
        data = self._get(
            f"{self.user_id}/mentions",
            fields="id,text,username,permalink,media_type,replied_to",
            limit=limit,
        )
        return data.get("data", []) or []

    def get_post(self, media_id: str) -> Dict[str, Any]:
        """抓單則貼文內容（用來取得「被查核的原貼文」文字）。"""
        return self._get(media_id, fields="id,text,username,permalink")

    # ── 發佈（兩段式：建 container → publish）────────────────────
    def reply_to(self, media_id: str, text: str) -> Optional[str]:
        """回覆指定貼文。回傳發佈後的 media id，失敗回 None。"""
        container = self._post(
            f"{self.user_id}/threads",
            media_type="TEXT",
            text=text[:THREADS_TEXT_LIMIT],
            reply_to_id=media_id,
        )
        cid = container.get("id")
        if not cid:
            return None
        published = self._post(f"{self.user_id}/threads_publish", creation_id=cid)
        return published.get("id")

    def publish_text(self, text: str) -> Optional[str]:
        """發佈一般貼文（模式 1：自動發佈查核結果時可用）。"""
        container = self._post(
            f"{self.user_id}/threads",
            media_type="TEXT",
            text=text[:THREADS_TEXT_LIMIT],
        )
        cid = container.get("id")
        if not cid:
            return None
        published = self._post(f"{self.user_id}/threads_publish", creation_id=cid)
        return published.get("id")
