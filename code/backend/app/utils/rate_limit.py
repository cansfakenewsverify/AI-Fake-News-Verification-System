"""
每 IP 速率限制（spec §5.7 `rate_limited`；公開上線前必備）。

- 行程內記憶體、滑動視窗：雲端（Render 免費方案）是單一行程，不需要 Redis。重啟後歸零可接受——
  真正守住 AI 預算的是 app/services/ai_budget.py 的每日次數上限（存在資料庫，重啟不歸零）。
- 兩個視窗都沒超過才放行：每分鐘 RATE_LIMIT_PER_MINUTE、每小時 RATE_LIMIT_PER_HOUR；設 0 = 關閉該視窗。
  預設值刻意寬鬆：同一間教室／校園 Wi-Fi 的所有人對外是同一個 IP。
- 被擋下的請求不計入視窗（一直重試不會把自己鎖得更久）。
- 用戶端 IP 取 X-Forwarded-For 最左邊（Vercel 代理會填真實 IP，Render 再往後附加）。
  直接打 Render 網址的人可以偽造這個標頭來躲每 IP 限制，但躲不掉每日總上限。
"""
import ipaddress
import logging
import math
import threading
import time
from collections import deque
from typing import Callable, Deque, Dict, Optional, Sequence, Tuple

from fastapi import Request
from fastapi.responses import JSONResponse

from app.config import settings

logger = logging.getLogger(__name__)

MSG_RATE_LIMITED = "查證太頻繁，請 {n} 秒後再試。"   # spec §8.7 err_rate
UNKNOWN_CLIENT = "unknown"
MAX_TRACKED_KEYS = 20000

Limit = Tuple[int, float]   # (視窗內最多幾次, 視窗秒數)


class SlidingWindowLimiter:
    """以 key 分桶的滑動視窗計數器（執行緒安全）。"""

    def __init__(self, clock: Callable[[], float] = time.monotonic, max_keys: int = MAX_TRACKED_KEYS):
        self._hits: Dict[str, Deque[float]] = {}
        self._lock = threading.Lock()
        self._clock = clock
        self._max_keys = max_keys

    def check(self, key: str, limits: Sequence[Limit]) -> int:
        """放行回 0 並記下這次請求；超過任一視窗回「還要等幾秒」（≥1），且不記這次請求。"""
        limits = [(int(n), float(w)) for n, w in limits if n and n > 0 and w > 0]
        if not limits:
            return 0
        longest = max(w for _, w in limits)
        now = self._clock()
        with self._lock:
            hits = self._hits.get(key)
            if hits is None:
                if len(self._hits) >= self._max_keys:
                    self._evict(now, longest)
                hits = self._hits[key] = deque()
            while hits and hits[0] <= now - longest:
                hits.popleft()

            wait = 0.0
            for max_hits, window in limits:
                in_window = [t for t in hits if t > now - window]
                if len(in_window) >= max_hits:
                    # 視窗內「倒數第 max_hits 筆」離開視窗後才有空位
                    wait = max(wait, in_window[-max_hits] + window - now)
            if wait > 0:
                return max(1, math.ceil(wait))
            hits.append(now)
            return 0

    def _evict(self, now: float, longest: float) -> None:
        """key 太多時清掉已經沒有有效紀錄的桶；還是太多就全部清空（寧可放行，不讓記憶體無限長大）。"""
        stale = [k for k, h in self._hits.items() if not h or h[-1] <= now - longest]
        for k in stale:
            del self._hits[k]
        if len(self._hits) >= self._max_keys:
            logger.warning("rate limiter: %d keys tracked, clearing all buckets", len(self._hits))
            self._hits.clear()

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


limiter = SlidingWindowLimiter()


def client_ip(request: Request) -> str:
    """限速用的用戶端識別：X-Forwarded-For 最左邊，沒有就用連線來源；IPv6 以 /64 為單位。"""
    forwarded = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip()
    raw = forwarded or (request.client.host if request.client else "")
    if not raw:
        return UNKNOWN_CLIENT
    try:
        ip = ipaddress.ip_address(raw)
    except ValueError:
        return raw[:64]
    if ip.version == 6:
        if ip.ipv4_mapped is not None:
            return str(ip.ipv4_mapped)
        return str(ipaddress.ip_network(f"{ip}/64", strict=False).network_address)
    return str(ip)


def configured_limits() -> Sequence[Limit]:
    return (
        (int(settings.RATE_LIMIT_PER_MINUTE), 60.0),
        (int(settings.RATE_LIMIT_PER_HOUR), 3600.0),
    )


def rate_limited_response(request: Request, scope: str = "analyze") -> Optional[JSONResponse]:
    """
    超過限制回 429 `rate_limited`（附 Retry-After 秒數），否則回 None。
    scope 讓不同用途各自計數（查證與回饋互不影響）。
    """
    wait = limiter.check(f"{scope}:{client_ip(request)}", configured_limits())
    if not wait:
        return None
    logger.info("rate_limited: scope=%s wait=%ss", scope, wait)
    return JSONResponse(
        status_code=429,
        content={"detail": MSG_RATE_LIMITED.format(n=wait), "code": "rate_limited"},
        headers={"Retry-After": str(wait)},
    )
