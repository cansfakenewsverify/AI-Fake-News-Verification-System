"""T-02：ThreadsService 從 data/threads_token.json 載入 token、計算剩餘天數、遮蔽 token。

全部離線：只寫 tmp 檔、monkeypatch settings 與 requests，不打任何網路。
"""
import json
from datetime import datetime, timedelta, timezone

import pytest
import requests

from app.config import settings
from app.services import threads_service as ts
from app.services.threads_service import (
    ThreadsAPIError,
    ThreadsService,
    load_token_file,
    redact_token,
)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


@pytest.fixture
def env_token(monkeypatch):
    monkeypatch.setattr(settings, "THREADS_ACCESS_TOKEN", "ENV_TOKEN", raising=False)
    monkeypatch.setattr(settings, "THREADS_USER_ID", "env-user", raising=False)
    monkeypatch.setattr(settings, "THREADS_BASE_URL", "https://graph.threads.net/v1.0", raising=False)


def _write(tmp_path, **fields):
    p = tmp_path / "threads_token.json"
    p.write_text(json.dumps(fields), encoding="utf-8")
    return p


def test_token_file_takes_priority_over_env(tmp_path, env_token):
    now = datetime.now(timezone.utc)
    p = _write(
        tmp_path,
        access_token="FILE_TOKEN",
        obtained_at=_iso(now),
        expires_at=_iso(now + timedelta(days=60, hours=1)),
        authorized_at=_iso(now),
        user_id="file-user",
    )
    svc = ThreadsService(token_path=p)
    assert svc.token == "FILE_TOKEN"
    assert svc.user_id == "file-user"
    assert svc.token_source == "file"
    assert svc.token_days_left == 60
    assert svc.available is True
    assert svc.invalid_reason is None


def test_missing_or_empty_file_falls_back_to_env(tmp_path, env_token):
    svc = ThreadsService(token_path=tmp_path / "nope.json")
    assert svc.token == "ENV_TOKEN"
    assert svc.user_id == "env-user"
    assert svc.token_days_left is None
    assert svc.available is True

    empty = _write(tmp_path, access_token="", user_id="x")
    assert load_token_file(empty) is None
    assert ThreadsService(token_path=empty).token == "ENV_TOKEN"

    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    assert load_token_file(broken) is None


def test_default_path_is_module_token_path(tmp_path, monkeypatch, env_token):
    p = _write(tmp_path, access_token="DEFAULT_PATH_TOKEN", user_id="u")
    monkeypatch.setattr(ts, "TOKEN_PATH", p)
    assert ThreadsService().token == "DEFAULT_PATH_TOKEN"


def test_expired_token_is_unavailable(tmp_path, env_token):
    now = datetime.now(timezone.utc)
    p = _write(
        tmp_path,
        access_token="OLD",
        obtained_at=_iso(now - timedelta(days=61)),
        expires_at=_iso(now - timedelta(hours=2)),
        authorized_at=_iso(now - timedelta(days=61)),
        user_id="file-user",
    )
    svc = ThreadsService(token_path=p)
    assert svc.token_days_left < 0
    assert svc.available is False
    assert svc.invalid_reason == "token_invalid"


def test_auth_days_left_is_90_days_from_authorized_at(tmp_path, env_token):
    now = datetime.now(timezone.utc)
    p = _write(
        tmp_path,
        access_token="T",
        expires_at=_iso(now + timedelta(days=41, hours=1)),
        authorized_at=_iso(now - timedelta(days=19, hours=-1)),
        user_id="u",
    )
    svc = ThreadsService(token_path=p)
    assert svc.auth_days_left == 71
    assert svc.token_days_left == 41

    # 沒有 authorized_at → None（不猜）
    p2 = _write(tmp_path, access_token="T", user_id="u")
    assert ThreadsService(token_path=p2).auth_days_left is None


def test_redact_replaces_access_token_param():
    assert redact_token("https://x/me?access_token=abc&fields=id") == "https://x/me?access_token=***&fields=id"
    assert redact_token("access_token=abc") == "access_token=***"
    assert "abc" not in redact_token("boom ACCESS_TOKEN=abc end")
    assert redact_token("token abc123 leaked", token="abc123") == "token *** leaked"


def test_http_error_message_does_not_leak_token(tmp_path, monkeypatch, env_token):
    secret = "SUPERSECRET123"
    p = _write(tmp_path, access_token=secret, user_id="u")

    def fake_get(url, params=None, timeout=None):
        resp = requests.Response()
        resp.status_code = 401
        resp.url = f"{url}?access_token={params['access_token']}&fields=id"
        return resp

    monkeypatch.setattr(ts.requests, "get", fake_get)
    svc = ThreadsService(token_path=p)
    with pytest.raises(ThreadsAPIError) as ei:
        svc.get_profile()
    assert ei.value.status_code == 401
    assert secret not in str(ei.value)
    assert "access_token=***" in str(ei.value)
    assert ei.value.__cause__ is None
    assert ei.value.__context__ is None
    assert ei.value.body is None or secret not in ei.value.body


def test_refresh_error_does_not_leak_token(tmp_path, monkeypatch, env_token):
    secret = "REFRESHSECRET456"
    p = _write(tmp_path, access_token=secret, user_id="u")

    def fake_get(url, params=None, timeout=None):
        raise requests.ConnectionError(f"failed {url}?access_token={params['access_token']}")

    monkeypatch.setattr(ts.requests, "get", fake_get)
    svc = ThreadsService(token_path=p)
    with pytest.raises(ThreadsAPIError) as ei:
        svc.refresh_token()
    assert secret not in str(ei.value)
    assert ei.value.__cause__ is None
    assert ei.value.__context__ is None
