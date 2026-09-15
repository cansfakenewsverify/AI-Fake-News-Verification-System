"""
SSRF 防護：所有「由使用者或 AI 決定的網址」對外請求都必須經過本模組（spec §9 安全：SSRF）。

- check_url(url)：只允許 http/https、port 80/443；拒絕 localhost、*.local；
  DNS 解析後所有 A/AAAA 位址都不得是 loopback/private/link-local/multicast/reserved。
  被拒 raise BlockedURL（此時保證尚未發出任何 HTTP 請求）。
- safe_get(url, method, timeout=None)：allow_redirects=False 自行跟隨 <=3 次轉址、每跳重檢；
  預設連線逾時 10 s、讀取逾時與牆鐘總時限 CRAWLER_TIMEOUT；回應超過 2 MB 中止（TooLarge）。
  可傳 timeout=(connect, total) 覆寫（url_validator 存活檢查用 (3, 3)）。

牆鐘總時限如何真正守住（urllib3 的 read timeout 是「每次 recv」重新計時，
逐位元組滴流的伺服器可以無限拖延；一次 read(n) 也會阻塞到湊滿 n 或 EOF）：
  1. deadline 在任何 IO 之前建立；DNS 解析（getaddrinfo 本身沒有逾時）在 daemon 執行緒跑，
     主執行緒最多等 min(剩餘時間, DNS_TIMEOUT)；
  2. 連線 + 讀回應標頭也在 daemon 執行緒跑、最多等剩餘時間；每跳 connect / read 逾時取
     min(設定值, 剩餘時間)，較晚開始的轉址跳不會再拿到完整的 10 s + 30 s；
  3. 讀內文期間有看門狗 Timer，到 deadline 就 shutdown 底層 socket 並 close 回應，
     阻塞中的 read 立即返回，一律轉成 FetchTimeout（不會把被截斷的內文當成功）。
  逾時而被放棄的背景執行緒是 daemon，會在自身 socket 逾時後結束，屆時產生的回應會被關閉；
  它只佔一條執行緒，不會讓呼叫端超過總時限。

已知限制：check_url 與 requests 各自解析 DNS，理論上存在 DNS rebinding 的 TOCTOU 空窗；
demo 規模接受此風險（每跳重檢已擋掉轉址型 SSRF）。單獨呼叫 check_url（例如 analyze API
的預檢）時 DNS 最多等 DNS_TIMEOUT 秒，逾時 raise FetchTimeout。
"""
from __future__ import annotations

import ipaddress
import socket
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional, Tuple
from urllib.parse import urljoin, urlparse

import requests

from app.config import settings

ALLOWED_SCHEMES = ("http", "https")
ALLOWED_PORTS = (80, 443)
CONNECT_TIMEOUT = 10
DNS_TIMEOUT = 10.0
READ_CHUNK = 8192
MAX_BYTES = 2 * 1024 * 1024
MAX_REDIRECTS = 3
REDIRECT_STATUSES = (301, 302, 303, 307, 308)
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}


class SafeFetchError(Exception):
    """safe_url 所有錯誤的基底；code 對應 crawler 的 error_code。"""

    code = "http_error"

    def __init__(self, reason: str = ""):
        super().__init__(reason)
        self.reason = reason


class BlockedURL(SafeFetchError):
    """網址被 SSRF 規則拒絕（協定 / port / 主機 / 私網位址 / 轉址到私網）。"""

    code = "blocked_url"


class UnresolvableURL(SafeFetchError):
    """主機名稱 DNS 解析失敗：不是 SSRF，屬一般爬取失敗（不應回 blocked_url）。"""

    code = "http_error"


class FetchTimeout(SafeFetchError):
    code = "timeout"


class TooLarge(SafeFetchError):
    code = "too_large"


class TooManyRedirects(SafeFetchError):
    code = "http_error"


@dataclass
class SafeResponse:
    status_code: int
    url: str
    content: bytes = b""
    headers: Dict[str, str] = field(default_factory=dict)
    encoding: Optional[str] = None

    @property
    def ok(self) -> bool:
        return 200 <= self.status_code < 300

    @property
    def text(self) -> str:
        return self.content.decode(self.encoding or "utf-8", errors="replace")


# ---- 牆鐘時限工具 ----

def _remaining(deadline: float) -> float:
    return max(0.0, deadline - time.monotonic())


def _close_quietly(resp: Any) -> None:
    close = getattr(resp, "close", None)
    if callable(close):
        try:
            close()
        except Exception:
            pass


def _abort_response(resp: Any) -> None:
    """從另一條執行緒中斷阻塞中的讀取：先 shutdown 底層 socket，再 close 回應。"""
    raw = getattr(resp, "raw", None)
    for path in (("_fp", "fp", "raw", "_sock"), ("_connection", "sock")):
        obj = raw
        for attr in path:
            obj = getattr(obj, attr, None)
            if obj is None:
                break
        if obj is not None and hasattr(obj, "shutdown"):
            try:
                obj.shutdown(socket.SHUT_RDWR)
            except Exception:
                pass
            break
    _close_quietly(resp)


def _call_bounded(
    fn: Callable[[], Any],
    timeout: float,
    on_abandoned: Optional[Callable[[Any], None]] = None,
) -> Any:
    """
    在 daemon 執行緒跑 fn，主執行緒最多等 timeout 秒；逾時 raise FetchTimeout。
    fn 的例外原樣拋回。逾時後 fn 才完成時，把結果交給 on_abandoned 收尾（例如關閉回應）。
    """
    if timeout <= 0:
        raise FetchTimeout("total_timeout")
    lock = threading.Lock()
    done = threading.Event()
    box: Dict[str, Any] = {}
    state = {"abandoned": False}

    def run():
        try:
            box["value"] = fn()
        except BaseException as e:  # noqa: BLE001 - 交回主執行緒處理
            box["error"] = e
        with lock:
            done.set()
            abandoned = state["abandoned"]
        if abandoned and on_abandoned is not None and "value" in box:
            try:
                on_abandoned(box["value"])
            except Exception:
                pass

    worker = threading.Thread(target=run, name="safe_url-io", daemon=True)
    worker.start()
    done.wait(timeout)
    with lock:
        if not done.is_set():
            state["abandoned"] = True
            raise FetchTimeout("total_timeout")
    if "error" in box:
        raise box["error"]
    return box["value"]


# ---- SSRF 規則 ----

def _ip_is_forbidden(addr: str) -> bool:
    ip = ipaddress.ip_address(addr.split("%", 1)[0])
    mapped = getattr(ip, "ipv4_mapped", None)
    if mapped is not None:
        ip = mapped
    return (
        ip.is_loopback
        or ip.is_private
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
        or not ip.is_global
    )


def check_url(url: str, dns_timeout: Optional[float] = None) -> None:
    """
    合法回 None；違反 SSRF 規則 raise BlockedURL；DNS 失敗 raise UnresolvableURL。
    DNS 解析最多等 min(dns_timeout, DNS_TIMEOUT) 秒，逾時 raise FetchTimeout。
    """
    if not isinstance(url, str) or not url.strip():
        raise BlockedURL("empty_url")
    parsed = urlparse(url.strip())
    scheme = (parsed.scheme or "").lower()
    if scheme not in ALLOWED_SCHEMES:
        raise BlockedURL("scheme_not_allowed")
    host = (parsed.hostname or "").strip().rstrip(".").lower()
    if not host:
        raise BlockedURL("missing_host")
    try:
        port = parsed.port
    except ValueError:
        raise BlockedURL("invalid_port")
    if port is None:
        port = 443 if scheme == "https" else 80
    if port not in ALLOWED_PORTS:
        raise BlockedURL("port_not_allowed")
    if host == "localhost" or host.endswith(".localhost") or host.endswith(".local"):
        raise BlockedURL("host_not_allowed")

    wait = DNS_TIMEOUT if dns_timeout is None else min(float(dns_timeout), DNS_TIMEOUT)
    try:
        infos = _call_bounded(
            lambda: socket.getaddrinfo(host, port, type=socket.SOCK_STREAM), wait
        )
    except FetchTimeout:
        raise
    except (socket.gaierror, UnicodeError, OSError) as e:
        raise UnresolvableURL(f"dns_resolution_failed: {e}")
    addrs = {info[4][0] for info in infos}
    if not addrs:
        raise UnresolvableURL("dns_no_address")
    for addr in addrs:
        try:
            forbidden = _ip_is_forbidden(addr)
        except ValueError:
            forbidden = True
        if forbidden:
            raise BlockedURL("private_address")


def safe_get(
    url: str,
    method: str = "GET",
    headers: Optional[Dict[str, str]] = None,
    max_bytes: int = MAX_BYTES,
    read_body: bool = True,
    timeout: Optional[Tuple[float, float]] = None,
) -> SafeResponse:
    """
    SSRF 安全的 HTTP 請求（同步，async 呼叫端請包 asyncio.to_thread）。
    timeout=(connect, total)：預設 (10, CRAWLER_TIMEOUT)；total 是整次呼叫
    （DNS、所有轉址跳、讀內文）的牆鐘上限，超過一律 raise FetchTimeout。
    read_body=False 時只看狀態碼不讀內文（url_validator 存活檢查用）。
    回傳 SafeResponse（非 2xx 也照常回傳，由呼叫端判斷）；違規 / 逾時 / 過大 raise SafeFetchError 子類。
    """
    if timeout is None:
        connect_limit, total = float(CONNECT_TIMEOUT), float(settings.CRAWLER_TIMEOUT)
    else:
        connect_limit, total = float(timeout[0]), float(timeout[1])
    deadline = time.monotonic() + total
    hdrs = dict(DEFAULT_HEADERS)
    if headers:
        hdrs.update(headers)
    method = method.upper()
    current = url

    for hop in range(MAX_REDIRECTS + 1):
        check_url(current, dns_timeout=_remaining(deadline))
        remaining = _remaining(deadline)
        if remaining <= 0:
            raise FetchTimeout("total_timeout")
        req_timeout = (min(connect_limit, remaining), min(total, remaining))

        def do_request(u=current, m=method, t=req_timeout):
            return requests.request(
                m, u, headers=hdrs, allow_redirects=False, stream=True, timeout=t,
            )

        try:
            # 連線 + 讀回應標頭也受牆鐘限制（逐位元組回標頭的伺服器拖不過 deadline）
            resp = _call_bounded(do_request, _remaining(deadline), on_abandoned=_close_quietly)
        except SafeFetchError:
            raise
        except requests.exceptions.Timeout as e:
            raise FetchTimeout(f"timeout: {e}")
        except requests.exceptions.RequestException as e:
            raise SafeFetchError(f"request_failed: {e}")

        # 看門狗：到 deadline 強制中斷 socket，讓阻塞中的 read 立刻返回
        aborted = threading.Event()

        def abort(r=resp, flag=aborted):
            flag.set()
            _abort_response(r)

        watchdog = threading.Timer(_remaining(deadline), abort)
        watchdog.daemon = True
        watchdog.start()
        try:
            location = resp.headers.get("Location") if resp.headers else None
            if resp.status_code in REDIRECT_STATUSES and location:
                if hop >= MAX_REDIRECTS:
                    raise TooManyRedirects("too_many_redirects")
                current = urljoin(current, location)
                if resp.status_code == 303 and method != "HEAD":
                    method = "GET"
                continue

            body = bytearray()
            if method != "HEAD" and read_body:
                declared = resp.headers.get("Content-Length") if resp.headers else None
                if declared and str(declared).isdigit() and int(declared) > max_bytes:
                    raise TooLarge("content_length_over_limit")
                for chunk in resp.iter_content(chunk_size=READ_CHUNK):
                    if aborted.is_set() or time.monotonic() >= deadline:
                        raise FetchTimeout("total_timeout")
                    if not chunk:
                        continue
                    body.extend(chunk)
                    if len(body) > max_bytes:
                        raise TooLarge("body_over_limit")
                # 看門狗 shutdown 後 read 可能回「假 EOF」：內文不完整，視為逾時
                if aborted.is_set():
                    raise FetchTimeout("total_timeout")
            return SafeResponse(
                status_code=resp.status_code,
                url=current,
                content=bytes(body),
                headers=dict(resp.headers or {}),
                encoding=getattr(resp, "encoding", None),
            )
        except SafeFetchError:
            raise
        except Exception as e:
            if aborted.is_set():
                raise FetchTimeout("total_timeout")
            if isinstance(e, requests.exceptions.Timeout):
                raise FetchTimeout(f"timeout: {e}")
            if isinstance(e, requests.exceptions.RequestException):
                raise SafeFetchError(f"request_failed: {e}")
            raise
        finally:
            watchdog.cancel()
            _close_quietly(resp)

    raise TooManyRedirects("too_many_redirects")
