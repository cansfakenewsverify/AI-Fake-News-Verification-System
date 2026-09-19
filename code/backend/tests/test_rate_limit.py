"""每 IP 速率限制（spec §5.7 rate_limited）。離線、零 AI 點數。"""
import json

import pytest
from starlette.requests import Request

from app.utils import rate_limit
from app.utils.rate_limit import SlidingWindowLimiter, client_ip, rate_limited_response


class Clock:
    def __init__(self, start=1000.0):
        self.t = start

    def __call__(self):
        return self.t


def _request(headers=None, client=("203.0.113.9", 50000)):
    raw = [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]
    return Request({"type": "http", "method": "POST", "path": "/", "headers": raw, "client": client})


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def limiter(clock):
    return SlidingWindowLimiter(clock=clock)


def test_allows_up_to_limit_then_blocks_with_wait(limiter, clock):
    limits = [(3, 60.0)]
    assert [limiter.check("a", limits) for _ in range(3)] == [0, 0, 0]
    assert limiter.check("a", limits) == 60
    clock.t += 45
    assert limiter.check("a", limits) == 15
    clock.t += 15.5           # 第一批三筆都離開視窗
    assert limiter.check("a", limits) == 0


def test_blocked_requests_are_not_recorded(limiter, clock):
    limits = [(2, 60.0)]
    assert limiter.check("a", limits) == 0            # t=0
    clock.t += 10
    assert limiter.check("a", limits) == 0            # t=10
    clock.t += 10
    assert limiter.check("a", limits) == 40           # t=20：被擋，不記
    clock.t += 10
    assert limiter.check("a", limits) == 30           # t=30：等待時間沒有因為重試而變長
    clock.t += 31
    assert limiter.check("a", limits) == 0            # t=61：t=0 那筆已過期
    clock.t += 1
    assert limiter.check("a", limits) == 8            # t=62：要等 t=10 那筆過期（70-62）


def test_hour_window_applies_even_when_minute_window_is_free(limiter, clock):
    limits = [(2, 60.0), (3, 3600.0)]
    assert limiter.check("a", limits) == 0
    assert limiter.check("a", limits) == 0
    clock.t += 120
    assert limiter.check("a", limits) == 0            # 每分鐘視窗是空的，但這是本小時第 3 筆
    clock.t += 120
    assert limiter.check("a", limits) == 3600 - 240   # 第 4 筆被每小時視窗擋下


def test_keys_are_independent(limiter):
    limits = [(1, 60.0)]
    assert limiter.check("a", limits) == 0
    assert limiter.check("b", limits) == 0
    assert limiter.check("a", limits) > 0


@pytest.mark.parametrize("limits", [[], [(0, 60.0)], [(0, 60.0), (-1, 3600.0)]])
def test_zero_or_missing_limits_disable_the_limiter(limiter, limits):
    assert all(limiter.check("a", limits) == 0 for _ in range(200))


def test_tracked_keys_are_bounded(clock):
    small = SlidingWindowLimiter(clock=clock, max_keys=5)
    for i in range(50):
        assert small.check(f"ip-{i}", [(10, 60.0)]) == 0
    assert len(small._hits) <= 5


def test_client_ip_prefers_leftmost_forwarded_for():
    req = _request({"X-Forwarded-For": "198.51.100.7, 10.0.0.1, 10.0.0.2"})
    assert client_ip(req) == "198.51.100.7"


def test_client_ip_falls_back_to_peer_then_unknown():
    assert client_ip(_request()) == "203.0.113.9"
    assert client_ip(_request(client=None)) == rate_limit.UNKNOWN_CLIENT


def test_client_ip_groups_ipv6_by_64_and_unwraps_mapped_ipv4():
    a = client_ip(_request({"X-Forwarded-For": "2001:db8:1:2:aaaa:bbbb:cccc:dddd"}))
    b = client_ip(_request({"X-Forwarded-For": "2001:db8:1:2::1"}))
    other = client_ip(_request({"X-Forwarded-For": "2001:db8:1:3::1"}))
    assert a == b == "2001:db8:1:2::"
    assert other != a
    assert client_ip(_request({"X-Forwarded-For": "::ffff:198.51.100.7"})) == "198.51.100.7"


def test_client_ip_truncates_garbage():
    assert len(client_ip(_request({"X-Forwarded-For": "x" * 500}))) == 64


@pytest.fixture
def fresh_global_limiter(monkeypatch, clock):
    monkeypatch.setattr(rate_limit, "limiter", SlidingWindowLimiter(clock=clock))
    monkeypatch.setattr(rate_limit.settings, "RATE_LIMIT_PER_MINUTE", 2)
    monkeypatch.setattr(rate_limit.settings, "RATE_LIMIT_PER_HOUR", 0)


def test_response_is_429_with_code_and_retry_after(fresh_global_limiter):
    req = _request({"X-Forwarded-For": "198.51.100.7"})
    assert rate_limited_response(req) is None
    assert rate_limited_response(req) is None
    resp = rate_limited_response(req)
    assert resp.status_code == 429
    assert resp.headers["Retry-After"] == "60"
    body = json.loads(resp.body)
    assert body == {"detail": "查證太頻繁，請 60 秒後再試。", "code": "rate_limited"}


def test_scopes_and_clients_do_not_share_buckets(fresh_global_limiter):
    req = _request({"X-Forwarded-For": "198.51.100.7"})
    assert [rate_limited_response(req, "analyze") for _ in range(2)] == [None, None]
    assert rate_limited_response(req, "analyze") is not None
    assert rate_limited_response(req, "feedback") is None
    assert rate_limited_response(_request({"X-Forwarded-For": "198.51.100.8"}), "analyze") is None


def test_settings_zero_disables(monkeypatch, clock):
    monkeypatch.setattr(rate_limit, "limiter", SlidingWindowLimiter(clock=clock))
    monkeypatch.setattr(rate_limit.settings, "RATE_LIMIT_PER_MINUTE", 0)
    monkeypatch.setattr(rate_limit.settings, "RATE_LIMIT_PER_HOUR", 0)
    req = _request()
    assert all(rate_limited_response(req) is None for _ in range(100))
