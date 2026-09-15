"""
Threads API 客戶端 — 查核機器人（延伸功能）用。

官方 API：https://developers.facebook.com/docs/threads
需要的權限（四項）：threads_basic、threads_content_publish、
threads_manage_replies、threads_manage_mentions。

注意：
- 所有方法都是「同步 requests」，在 async 流程中呼叫要包 asyncio.to_thread
  （同 ai_service 的慣例，避免卡 event loop）。
- 端點名稱依 2026-01 的官方文件實作；Meta 改版時只需要改這個檔。
- 回覆有 500 字上限（format_verdict_reply／threads_len 見 threads_reply.py）。
- token 來源：data/threads_token.json（scripts/threads_auth.py 寫出）存在且有
  access_token 時優先；否則退用 .env 的 THREADS_ACCESS_TOKEN／THREADS_USER_ID。
- token 絕不可出現在例外訊息或 log：HTTP 錯誤一律經 redact_token() 遮蔽後再拋出。
"""
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol, Union, runtime_checkable

import requests

from app.config import settings

# 回覆模板與長度計數在 threads_reply.py（spec 7.7 純函式）；此處 re-export 維持舊 import 路徑
from app.services.threads_reply import (  # noqa: F401
    THREADS_TARGET_LEN,
    THREADS_TEXT_LIMIT,
    format_verdict_reply,
    reply_cannot_read,
    reply_media_only,
    reply_too_short,
    threads_len,
)

# token 檔（相對後端工作目錄，與 threads_state.json 等 store 一致）
TOKEN_PATH = Path("data") / "threads_token.json"

# 授權本身的有效期（與 60 天 token 分開計算，spec 7.3 第 5 點）
AUTH_VALID_DAYS = 90

_TOKEN_PARAM_RE = re.compile(r"(access_token=)[^&\s'\"]+", re.IGNORECASE)


def redact_token(text: Any, token: Optional[str] = None) -> str:
    """把字串中的 access_token=xxx 參數值換成 ***；另外把已知 token 原文也遮蔽。"""
    s = str(text)
    s = _TOKEN_PARAM_RE.sub(r"\1***", s)
    if token:
        s = s.replace(token, "***")
    return s


class ThreadsApiError(Exception):
    """Threads API 回非 2xx（spec 7.10：分流以 HTTP 狀態碼為主）。

    status：HTTP 狀態碼（連線失敗等拿不到回應時為 None）
    body：回應內容（dict 或字串；已遮蔽 token）
    live（ThreadsService）與 sim（FakeThreadsService 的 _sim_error 注入）共用。
    """

    def __init__(self, status: Optional[int], body: Any = None, message: Optional[str] = None):
        self.status = status
        self.body = body
        super().__init__(message or f"Threads API error: HTTP {status}: {body!r}")

    @property
    def status_code(self) -> Optional[int]:
        """舊名相容（T-02 起的呼叫端讀 status_code）。"""
        return self.status


class ThreadsAPIError(ThreadsApiError):
    """舊名相容：以 (message, status_code) 建構；可用 ThreadsApiError 一併捕捉。"""

    def __init__(self, message: str, status_code: Optional[int] = None, body: Any = None):
        super().__init__(status_code, body, message=message)


@runtime_checkable
class ThreadsClient(Protocol):
    """Threads 客戶端介面（spec 7.9）。run_threads_poll 只依賴這個 Protocol；
    ThreadsService（live）與 FakeThreadsService（sim，app/services/threads_sim.py）皆實作。
    所有方法都是同步呼叫，async 流程中要包 asyncio.to_thread。"""

    @property
    def available(self) -> bool: ...

    def get_profile(self) -> Dict[str, Any]: ...

    def get_mentions(self, since: Any = None, after_cursor: Optional[str] = None) -> List[Dict[str, Any]]: ...

    def get_post(self, media_id: str) -> Dict[str, Any]: ...

    def reply_to(self, media_id: str, text: str) -> Optional[str]: ...

    def publish_text(self, text: str) -> Optional[str]: ...

    def get_publishing_limit(self) -> Dict[str, Any]: ...

    def refresh_token(self) -> Dict[str, Any]: ...


def get_threads_client() -> Optional["ThreadsClient"]:
    """依 settings.threads_mode_effective 回傳客戶端：live → ThreadsService、
    sim → FakeThreadsService、off → None。回傳的 live 客戶端可能 available=False
    （沒 token／token 過期），由呼叫端判斷。"""
    mode = settings.threads_mode_effective
    if mode == "live":
        return ThreadsService()
    if mode == "sim":
        from app.services.threads_sim import FakeThreadsService  # 延遲 import 避免循環

        return FakeThreadsService()
    return None


def load_token_file(path: Union[str, Path, None] = None) -> Optional[Dict[str, Any]]:
    """讀 threads_token.json；不存在、損毀或沒有 access_token 時回 None。"""
    p = Path(path) if path is not None else TOKEN_PATH
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or not str(data.get("access_token") or "").strip():
        return None
    return data


def _parse_iso(value: Any) -> Optional[datetime]:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _days_left(until: Optional[datetime], now: Optional[datetime] = None) -> Optional[int]:
    """剩餘整天數（向下取整；已過期為負數）。"""
    if until is None:
        return None
    now = now or datetime.now(timezone.utc)
    return int((until - now).total_seconds() // 86400)


class ThreadsService:
    """Threads Graph API 薄封裝（ThreadsClient 的 live 實作）。
    沒設 token/user_id 時 available=False，一律跳過。"""

    def __init__(self, token_path: Union[str, Path, None] = None):
        self.base = (settings.THREADS_BASE_URL or "").rstrip("/")
        self.token = (settings.THREADS_ACCESS_TOKEN or "").strip()
        self.user_id = (settings.THREADS_USER_ID or "").strip()
        self.token_source = "env" if self.token else None
        self.token_expires_at: Optional[datetime] = None
        self.authorized_at: Optional[datetime] = None

        data = load_token_file(token_path)
        if data:
            self.token = str(data["access_token"]).strip()
            file_uid = str(data.get("user_id") or "").strip()
            if file_uid:
                self.user_id = file_uid
            self.token_source = "file"
            self.token_expires_at = _parse_iso(data.get("expires_at"))
            self.authorized_at = _parse_iso(data.get("authorized_at"))

    # ── token 期限 ───────────────────────────────────────────────
    @property
    def token_days_left(self) -> Optional[int]:
        return _days_left(self.token_expires_at)

    @property
    def auth_days_left(self) -> Optional[int]:
        if self.authorized_at is None:
            return None
        return _days_left(self.authorized_at + timedelta(days=AUTH_VALID_DAYS))

    @property
    def invalid_reason(self) -> Optional[str]:
        days = self.token_days_left
        if days is not None and days < 0:
            return "token_invalid"
        return None

    @property
    def available(self) -> bool:
        if self.invalid_reason:
            return False
        return bool(self.base and self.token and self.user_id)

    # ── HTTP helpers ─────────────────────────────────────────────
    def _request(self, method: str, path: str, params: Dict[str, Any]) -> Dict[str, Any]:
        params["access_token"] = self.token
        url = f"{self.base}/{path}"
        msg: Optional[str] = None
        status: Optional[int] = None
        body: Optional[str] = None
        try:
            if method == "GET":
                r = requests.get(url, params=params, timeout=30)
            else:
                r = requests.post(url, data=params, timeout=30)
            r.raise_for_status()
            return r.json()
        except requests.RequestException as e:
            resp = getattr(e, "response", None)
            status = getattr(resp, "status_code", None)
            msg = redact_token(f"{type(e).__name__}: {e}", self.token)
            if resp is not None:
                try:
                    body = redact_token(resp.text, self.token)
                except Exception:
                    body = None
        # 在 except 區塊外才 raise：__cause__ 與 __context__ 皆為 None，
        # 任何會走訪 __context__ 的錯誤回報都拿不到含 token 的原始例外 / URL
        raise ThreadsAPIError(msg or "request failed", status_code=status, body=body)

    def _get(self, path: str, **params) -> Dict[str, Any]:
        return self._request("GET", path, params)

    def _post(self, path: str, **params) -> Dict[str, Any]:
        return self._request("POST", path, params)

    # ── 讀取 ─────────────────────────────────────────────────────
    def get_profile(self) -> Dict[str, Any]:
        """驗證 token 用：回機器人自己的 id/username。"""
        return self._get("me", fields="id,username")

    def get_mentions(
        self,
        since: Any = None,
        after_cursor: Optional[str] = None,
        limit: int = 25,
    ) -> List[Dict[str, Any]]:
        """抓最近被 @ 提及的貼文（別人 tag 機器人請求查核）。
        since：unix 秒數（spec 7.4）；after_cursor：分頁游標（分頁容忍見 T-14）。"""
        params: Dict[str, Any] = {
            "fields": "id,text,username,permalink,media_type,replied_to,timestamp",
            "limit": limit,
        }
        if since is not None:
            params["since"] = since
        if after_cursor:
            params["after"] = after_cursor
        data = self._get(f"{self.user_id}/mentions", **params)
        return data.get("data", []) or []

    def get_post(self, media_id: str) -> Dict[str, Any]:
        """抓單則貼文內容（用來取得「被查核的原貼文」文字）。"""
        return self._get(media_id, fields="id,text,username,permalink,media_type")

    def get_publishing_limit(self) -> Dict[str, Any]:
        """回覆配額（spec 7.10 護欄）：reply_quota_usage 與 reply_config。"""
        data = self._get(
            f"{self.user_id}/threads_publishing_limit",
            fields="reply_quota_usage,reply_config",
        )
        rows = data.get("data") or []
        return rows[0] if rows else {}

    def refresh_token(self) -> Dict[str, Any]:
        """把長效 token 再延 60 天（th_refresh_token）；只更新記憶體中的 token，
        寫檔由 scripts/threads_auth.py --refresh 負責。"""
        host = re.sub(r"/v\d+(\.\d+)?$", "", self.base)
        url = f"{host}/refresh_access_token"
        err_msg: Optional[str] = None
        err_status: Optional[int] = None
        data: Dict[str, Any] = {}
        try:
            r = requests.get(
                url,
                params={"grant_type": "th_refresh_token", "access_token": self.token},
                timeout=30,
            )
            r.raise_for_status()
            data = r.json()
        except requests.RequestException as e:
            err_status = getattr(getattr(e, "response", None), "status_code", None)
            err_msg = redact_token(f"{type(e).__name__}: {e}", self.token)
        if err_msg is not None:
            # 區塊外 raise：不留 __context__（原例外訊息含 token URL）
            raise ThreadsAPIError(err_msg, status_code=err_status)
        new_token = str(data.get("access_token") or "").strip()
        if new_token:
            self.token = new_token
            expires_in = data.get("expires_in")
            if isinstance(expires_in, (int, float)):
                self.token_expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
        return {k: v for k, v in data.items() if k != "access_token"}

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
