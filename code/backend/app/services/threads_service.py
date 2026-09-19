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
- 發佈是兩段式＋狀態檢查（spec §7.6；T-12）：create_reply_container → wait_container
  （每 5 秒查一次、最多 60 秒）→ status=FINISHED 才 publish_container。live 與 sim 共用
  TwoStepPublishing 的 wait_container／reply_to／publish_text，差別只在三個原子操作的實作。
- 錯誤（spec §7.10；T-13）：非 2xx 一律把 body 以 repr() 寫 log（token 已遮蔽）後丟
  ThreadsApiError(status, body)；5xx／逾時／連線失敗丟其子類 ThreadsTransientError。
  分流（429 backoff、未知 4xx 標 failed…）在 app/workers/threads_bot.py，以 HTTP 狀態碼為主。
"""
import json
import logging
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Protocol, Union, runtime_checkable

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

logger = logging.getLogger("threads_service")

# ── container 狀態（spec §7.6；官方值：IN_PROGRESS／FINISHED／PUBLISHED／ERROR／EXPIRED）──
CONTAINER_IN_PROGRESS = "IN_PROGRESS"
CONTAINER_FINISHED = "FINISHED"      # 可以 publish 的唯一狀態
CONTAINER_PUBLISHED = "PUBLISHED"    # 已發佈過：不可再 publish（防重複回覆）
CONTAINER_ERROR = "ERROR"
CONTAINER_EXPIRED = "EXPIRED"
CONTAINER_TIMEOUT = "TIMEOUT"        # 非官方值：wait_container 等到上限仍未 FINISHED
CONTAINER_TERMINAL = (CONTAINER_FINISHED, CONTAINER_PUBLISHED, CONTAINER_ERROR, CONTAINER_EXPIRED)
# 官方建議每分鐘查一次、最多 5 分鐘；文字貼文通常數秒即 FINISHED，故縮短（spec §7.6）
CONTAINER_POLL_INTERVAL_SECONDS = 5.0
CONTAINER_POLL_TIMEOUT_SECONDS = 60.0

# spec §7.10「連結超限」：2025-12-22 起連結 >5 個會回這個錯誤字串
LINK_LIMIT_MARKER = "THREADS_API__LINK_LIMIT_EXCEEDED"

_LOG_CODEC = "cp950"   # Windows 主控台編碼：log 內無法編碼的字元（emoji）以 \\U 跳脫（CLAUDE.md §7）

_TOKEN_PARAM_RE = re.compile(r"(access_token=)[^&\s'\"]+", re.IGNORECASE)


def _log_repr(value: Any) -> str:
    return repr(value).encode(_LOG_CODEC, "backslashreplace").decode(_LOG_CODEC)


def _default_sleep(seconds: float) -> None:
    """wait_container 預設的等待。呼叫當下才解析 time.sleep：測試可 monkeypatch 這個函式或 time.sleep。"""
    time.sleep(seconds)


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


class ThreadsTransientError(ThreadsAPIError):
    """暫時性失敗（spec §7.10「5xx／逾時」）：HTTP 5xx、逾時、連線失敗、2xx 但回應不是 JSON。
    呼叫端不標記該 mention、下輪重試；status 為 5xx 或 None。"""


def is_link_limit_error(exc: BaseException) -> bool:
    """回應 body 是否含 THREADS_API__LINK_LIMIT_EXCEEDED（spec §7.10「連結超限」）。"""
    body = getattr(exc, "body", None)
    if body is None:
        return False
    if not isinstance(body, str):
        try:
            body = json.dumps(body, ensure_ascii=False)
        except (TypeError, ValueError):
            body = str(body)
    return LINK_LIMIT_MARKER in body


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

    # 兩段式發佈（spec 7.6；T-12）。threads_bot 逐步呼叫，才能在 publish 之前先寫 pending_publish
    def create_reply_container(self, media_id: str, text: str) -> Optional[str]: ...

    def get_container_status(self, container_id: str) -> Dict[str, Any]: ...

    def wait_container(self, container_id: str) -> str: ...

    def publish_container(self, container_id: str) -> Optional[str]: ...


class TwoStepPublishing:
    """兩段式發佈的共用流程（spec §7.6）：live（ThreadsService）與 sim（FakeThreadsService）共用，
    子類只需實作 create_reply_container／create_post_container／get_container_status／publish_container。

    wait_container 的等待可注入：sleep 參數、實例屬性 container_sleep，或 monkeypatch time.sleep；
    間隔與上限可用實例屬性 container_poll_interval／container_poll_timeout 覆寫（測試不會真的睡）。"""

    container_poll_interval: float = CONTAINER_POLL_INTERVAL_SECONDS
    container_poll_timeout: float = CONTAINER_POLL_TIMEOUT_SECONDS
    container_sleep: Optional[Callable[[float], None]] = None   # None → _default_sleep（time.sleep）

    def wait_container(
        self,
        container_id: str,
        interval: Optional[float] = None,
        timeout: Optional[float] = None,
        sleep: Optional[Callable[[float], None]] = None,
    ) -> str:
        """輪詢 container 狀態直到 FINISHED／PUBLISHED／ERROR／EXPIRED，或超過 timeout 回 TIMEOUT。
        先查再睡：文字貼文通常第一次就 FINISHED，不增加回覆延遲。查詢次數有上限
        （timeout // interval + 1，預設 13 次）。API 錯誤（ThreadsApiError）直接往外丟，由呼叫端分流。"""
        interval = float(self.container_poll_interval if interval is None else interval)
        timeout = float(self.container_poll_timeout if timeout is None else timeout)
        sleep = sleep or self.container_sleep or _default_sleep
        attempts = int(timeout // interval) + 1 if interval > 0 else 1
        status = ""
        for attempt in range(max(1, attempts)):
            if attempt:
                sleep(interval)
            info = self.get_container_status(container_id)  # type: ignore[attr-defined]
            info = info if isinstance(info, dict) else {}
            status = str(info.get("status") or "").strip().upper()
            if status in CONTAINER_TERMINAL:
                if status in (CONTAINER_ERROR, CONTAINER_EXPIRED):
                    logger.warning(
                        "threads container %s status=%s error_message=%s",
                        _log_repr(container_id), status, _log_repr(info.get("error_message")),
                    )
                return status
        logger.warning(
            "threads container %s still %s after %ss: TIMEOUT",
            _log_repr(container_id), _log_repr(status or CONTAINER_IN_PROGRESS), int(timeout),
        )
        return CONTAINER_TIMEOUT

    def _publish_when_finished(self, container_id: Optional[str]) -> Optional[str]:
        """status=FINISHED 才 publish；其餘狀態（ERROR／EXPIRED／TIMEOUT／PUBLISHED）不 publish、回 None。"""
        if not container_id:
            return None
        if self.wait_container(container_id) != CONTAINER_FINISHED:
            return None
        return self.publish_container(container_id)  # type: ignore[attr-defined]

    def reply_to(self, media_id: str, text: str, **kwargs: Any) -> Optional[str]:
        """回覆指定貼文（三步串接）。回傳發佈後的 media id；container 沒有 FINISHED 回 None。
        機器人不走這個捷徑，而是逐步呼叫以便在 publish 前先寫 pending_publish（threads_bot）。"""
        container_id = self.create_reply_container(media_id, text, **kwargs)  # type: ignore[attr-defined]
        return self._publish_when_finished(container_id)

    def publish_text(self, text: str) -> Optional[str]:
        """發佈一般貼文（模式 1：自動發佈查核結果時可用）；同樣三步。"""
        container_id = self.create_post_container(text)  # type: ignore[attr-defined]
        return self._publish_when_finished(container_id)


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


class ThreadsService(TwoStepPublishing):
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
    def _response_body(self, resp: Any) -> Any:
        """非 2xx 回應的 body：先遮蔽 token，再盡量解析成 JSON（分流只看 HTTP 狀態碼；
        body 供 log 與「連結超限」判斷）。空 body → None。"""
        try:
            text = redact_token(resp.text, self.token)
        except Exception:
            return None
        if not text:
            return None
        try:
            parsed = json.loads(text)
        except ValueError:
            return text
        return parsed if isinstance(parsed, (dict, list)) else text

    def _request(self, method: str, path: str, params: Dict[str, Any]) -> Dict[str, Any]:
        # token 一律走 access_token 查詢／表單參數（spec 7.6；Authorization: Bearer 未文件化，不採用）
        params["access_token"] = self.token
        url = f"{self.base}/{path}"
        msg: Optional[str] = None
        status: Optional[int] = None
        body: Any = None
        transient = False
        resp: Any = None
        try:
            if method == "GET":
                resp = requests.get(url, params=params, timeout=30)
            else:
                resp = requests.post(url, data=params, timeout=30)
        except requests.RequestException as e:
            # 逾時／連線失敗：拿不到回應 → 暫時性
            msg = redact_token(f"{type(e).__name__}: {e}", self.token)
            transient = True
        if resp is not None:
            status = resp.status_code
            if 200 <= status < 300:
                try:
                    data = resp.json()
                except ValueError:
                    data = None
                if isinstance(data, dict):
                    return data
                msg = f"HTTP {status} but the response is not a JSON object"
                transient = True
            else:
                # 不用 raise_for_status()：自己組訊息，狀態碼與 body 交給呼叫端分流（spec 7.10）
                msg = redact_token(f"HTTP {status} for url: {getattr(resp, 'url', None) or url}", self.token)
                transient = status >= 500
            body = self._response_body(resp)
        logger.warning(
            "threads api %s %s failed: status=%s error=%s body=%s",
            method, _log_repr(path), status, _log_repr(msg), _log_repr(body),
        )
        # 在 except 區塊外才 raise：__cause__ 與 __context__ 皆為 None，
        # 任何會走訪 __context__ 的錯誤回報都拿不到含 token 的原始例外 / URL
        error_cls = ThreadsTransientError if transient else ThreadsAPIError
        raise error_cls(msg or "request failed", status_code=status, body=body)

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

    # ── 發佈（兩段式＋狀態檢查，spec 7.6）────────────────────────
    # reply_to()／publish_text()／wait_container() 由 TwoStepPublishing 串接以下原子操作；
    # auto_publish_text 單步發佈為候選路徑（D-11），未實作。
    def create_reply_container(self, media_id: str, text: str) -> Optional[str]:
        """第一步：建立回覆用的 container，回傳 container id（creation_id）。"""
        container = self._post(
            f"{self.user_id}/threads",
            media_type="TEXT",
            text=text[:THREADS_TEXT_LIMIT],
            reply_to_id=media_id,
        )
        cid = container.get("id")
        return str(cid) if cid else None

    def create_post_container(self, text: str) -> Optional[str]:
        """第一步（一般貼文）：建立 container，回傳 container id。"""
        container = self._post(
            f"{self.user_id}/threads",
            media_type="TEXT",
            text=text[:THREADS_TEXT_LIMIT],
        )
        cid = container.get("id")
        return str(cid) if cid else None

    def get_container_status(self, container_id: str) -> Dict[str, Any]:
        """第二步：查 container 狀態，回 {"status": IN_PROGRESS|FINISHED|PUBLISHED|ERROR|EXPIRED, "error_message"?}。"""
        return self._get(str(container_id), fields="status,error_message")

    def publish_container(self, container_id: str) -> Optional[str]:
        """第三步：發佈 container（只在 status=FINISHED 後呼叫），回傳發佈後的 media id。"""
        published = self._post(f"{self.user_id}/threads_publish", creation_id=container_id)
        pid = published.get("id")
        return str(pid) if pid else None
