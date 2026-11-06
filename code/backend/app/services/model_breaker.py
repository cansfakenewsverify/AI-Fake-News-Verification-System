"""
判讀模型的斷路器：閘道滿載（逾時、排隊、502／503）太多次就先換備援模型，隔一陣子再放一個請求試探主模型。

為什麼：學校 Mercury 閘道的人越來越多，尖峰時常滿載。滿載時一直重打主模型只會讓每次查證都卡到逾時。
只算「滿載」類錯誤；金鑰錯、額度用完、模型不存在換模型也沒用，不算（照原樣往外丟）。

狀態只存在這個行程的記憶體（重啟歸零），每個模型各一份。
"""
from __future__ import annotations

import threading
import time
from collections import deque
from typing import Any, Deque, Dict, Optional

import requests

from app.config import settings

_lock = threading.Lock()
_failures: Dict[str, Deque[float]] = {}
_last_probe: Dict[str, float] = {}
_last_reason: Dict[str, str] = {}


def is_overload(exc: BaseException) -> bool:
    """這個例外算不算「閘道滿載」。額度用完（insufficient_quota）不算。"""
    if isinstance(exc, (requests.exceptions.Timeout, requests.exceptions.ConnectionError)):
        return True
    if isinstance(exc, requests.exceptions.HTTPError):
        resp = getattr(exc, "response", None)
        status = getattr(resp, "status_code", None)
        text = getattr(resp, "text", "") or ""
        if "insufficient_quota" in text:
            return False
        if status in (502, 503):
            return True
        if status == 429:
            return True   # rate_limit_exceeded、queue_timeout、queue_full
    return False


def _prune(model: str, now: float) -> Deque[float]:
    q = _failures.setdefault(model, deque())
    window = float(settings.BREAKER_WINDOW_SECONDS)
    while q and now - q[0] > window:
        q.popleft()
    return q


def record_failure(model: str, reason: str = "") -> None:
    now = time.monotonic()
    with _lock:
        q = _prune(model, now)
        q.append(now)
        if len(q) >= int(settings.BREAKER_FAILURE_THRESHOLD) and model not in _last_probe:
            _last_probe[model] = now   # 剛斷路：等滿 PROBE 秒才放第一個試探
        if reason:
            _last_reason[model] = reason


def record_success(model: str) -> None:
    with _lock:
        _failures.pop(model, None)
        _last_probe.pop(model, None)
        _last_reason.pop(model, None)


def is_open(model: str) -> bool:
    """斷路中 = 最近視窗內滿載失敗次數達門檻。"""
    now = time.monotonic()
    with _lock:
        return len(_prune(model, now)) >= int(settings.BREAKER_FAILURE_THRESHOLD)


def allow_request(model: str) -> bool:
    """斷路中的模型每隔 BREAKER_PROBE_SECONDS 放一個請求試探；其餘直接跳過。"""
    if not is_open(model):
        return True
    now = time.monotonic()
    with _lock:
        last = _last_probe.get(model)
        if last is None or now - last >= float(settings.BREAKER_PROBE_SECONDS):
            _last_probe[model] = now
            return True
    return False


def status(models: Optional[list] = None) -> Dict[str, Any]:
    """給 /api/health 看：每個模型現在是否斷路、最近失敗次數與原因。"""
    now = time.monotonic()
    out: Dict[str, Any] = {}
    with _lock:
        names = models or sorted(set(_failures) | set(_last_reason))
        for m in names:
            n = len(_prune(m, now))
            out[m] = {
                "open": n >= int(settings.BREAKER_FAILURE_THRESHOLD),
                "recent_failures": n,
                "last_reason": _last_reason.get(m),
            }
    return out


def reset() -> None:
    """測試用。"""
    with _lock:
        _failures.clear()
        _last_probe.clear()
        _last_reason.clear()
