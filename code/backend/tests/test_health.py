"""B-22：/health 與 /api/health（spec §5.1、§8.2；測試 FN-3）。

離線、零 AI 點數：相關設定全部 monkeypatch，不依賴本機 .env 的值；
TestClient 不進 lifespan（不動 SQLite、不啟排程）。
"""
import socket

import pytest
import requests
from fastapi.testclient import TestClient

from app.config import settings
from app.main import APP_VERSION, app
from app.services.ai_service import AIService

HEALTH_KEYS = {"status", "ai_available", "threads_mode", "scheduler", "daily_ai_calls"}
_LOOPBACK = ("127.0.0.1", "::1", "localhost")


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def cgu_only(monkeypatch):
    """provider 鏈只剩 cgu（金鑰為假值；/health 不得真的打它）。"""
    monkeypatch.setattr(settings, "MYAI_API_KEY", "")
    monkeypatch.setattr(settings, "CGU_API_KEY", "dummy-key")
    monkeypatch.setattr(settings, "CGU_BASE_URL", "https://example.invalid/v1")
    monkeypatch.setattr(settings, "AI_PROVIDER", "cgu")


@pytest.fixture
def base_settings(monkeypatch, cgu_only):
    monkeypatch.setattr(settings, "ENABLE_SCHEDULER", False)
    monkeypatch.setattr(settings, "TRENDING_FETCH_INTERVAL_HOURS", 6)
    monkeypatch.setattr(settings, "DEMO_MODE", False)
    monkeypatch.setattr(settings, "THREADS_MODE", "off")
    monkeypatch.setattr(settings, "ENABLE_THREADS_BOT", False)


@pytest.fixture
def network_calls(monkeypatch):
    """記錄並擋下所有對外連線（requests 與非 loopback socket）；AI 呼叫另計。"""
    calls = []

    def fake_request(self, method, url, *args, **kwargs):
        calls.append(("requests", method, url))
        raise AssertionError(f"/health must not make HTTP calls: {method} {url}")

    real_connect = socket.socket.connect

    def guarded_connect(self, address):
        host = address[0] if isinstance(address, tuple) else address
        if host not in _LOOPBACK:
            calls.append(("socket", address))
            raise AssertionError(f"/health must not open sockets: {address}")
        return real_connect(self, address)

    def no_ai(*args, **kwargs):
        calls.append(("ai", args[1:2]))
        raise AssertionError("/health must not call the AI provider")

    monkeypatch.setattr(requests.Session, "request", fake_request)
    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    for name in ("analyze_content", "analyze_image", "_run_analysis", "generate_embedding"):
        monkeypatch.setattr(AIService, name, no_ai)
    return calls


@pytest.mark.parametrize("enabled,hours", [(False, 6), (True, 3)])
def test_health_has_scheduler_block(client, monkeypatch, base_settings, enabled, hours):
    monkeypatch.setattr(settings, "ENABLE_SCHEDULER", enabled)
    monkeypatch.setattr(settings, "TRENDING_FETCH_INTERVAL_HOURS", hours)

    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body) == HEALTH_KEYS
    assert body["status"] == "healthy"
    assert body["scheduler"] == {"enabled": enabled, "interval_hours": hours}
    assert type(body["scheduler"]["enabled"]) is bool
    assert type(body["scheduler"]["interval_hours"]) is int
    assert body["ai_available"] is True
    assert body["threads_mode"] == "off"
    assert body["daily_ai_calls"] is None
    # 驗收 curl 比對的是原始 JSON 字串（compact 格式）
    expected = '"scheduler":{"enabled":%s,"interval_hours":%d}' % (str(enabled).lower(), hours)
    assert expected in resp.text


def test_health_scheduler_follows_lifespan_rule(client, monkeypatch, base_settings):
    # DEMO_MODE 時 lifespan 不啟動熱門排程 → 不得宣稱「每 N 小時自動更新」
    monkeypatch.setattr(settings, "ENABLE_SCHEDULER", True)
    monkeypatch.setattr(settings, "DEMO_MODE", True)
    assert client.get("/health").json()["scheduler"]["enabled"] is False


@pytest.mark.parametrize("mode,legacy,expected", [
    ("off", False, "off"), ("sim", False, "sim"), ("live", False, "live"),
    (None, True, "live"), (None, False, "off"),
])
def test_health_threads_mode_effective(client, monkeypatch, base_settings, mode, legacy, expected):
    monkeypatch.setattr(settings, "THREADS_MODE", mode)
    monkeypatch.setattr(settings, "ENABLE_THREADS_BOT", legacy)
    assert client.get("/health").json()["threads_mode"] == expected


def test_health_ai_available_false_without_provider(client, monkeypatch, base_settings):
    monkeypatch.setattr(settings, "CGU_API_KEY", "")
    monkeypatch.setattr(settings, "MYAI_API_KEY", "")
    body = client.get("/health").json()
    assert body["ai_available"] is False
    assert body["status"] == "healthy"


@pytest.mark.parametrize("enabled,mode", [(False, "off"), (True, "sim")])
def test_api_health_alias_same_payload(client, monkeypatch, base_settings, enabled, mode):
    monkeypatch.setattr(settings, "ENABLE_SCHEDULER", enabled)
    monkeypatch.setattr(settings, "THREADS_MODE", mode)
    plain = client.get("/health")
    alias = client.get("/api/health")
    assert plain.status_code == alias.status_code == 200
    assert alias.json() == plain.json()
    assert set(alias.json()) == HEALTH_KEYS


def test_health_no_network(client, base_settings, network_calls):
    for path in ("/health", "/api/health", "/health"):
        resp = client.get(path)
        assert resp.status_code == 200
        assert resp.json()["ai_available"] is True
    assert network_calls == []


def test_root_version_0_3_0(client):
    assert APP_VERSION == "0.3.0"
    assert app.version == "0.3.0"
    body = client.get("/").json()
    assert body["version"] == "0.3.0"
    assert client.get("/openapi.json").json()["info"]["version"] == "0.3.0"
