"""T-03：scripts/threads_auth.py 的 OAuth 交換與 --refresh（requests 全 mock，離線零成本）。"""
import importlib.util
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.config import settings

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "threads_auth.py"
_spec = importlib.util.spec_from_file_location("threads_auth_script", _SCRIPT)
auth = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(auth)

NOW = datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc)
SIXTY_DAYS = 60 * 86400


class FakeResp:
    def __init__(self, status, payload):
        self.status_code = status
        self._payload = payload
        self.text = json.dumps(payload)

    def json(self):
        return self._payload


@pytest.fixture
def cfg(monkeypatch):
    monkeypatch.setattr(settings, "THREADS_APP_ID", "APPID123", raising=False)
    monkeypatch.setattr(settings, "THREADS_APP_SECRET", "SECRET456", raising=False)
    monkeypatch.setattr(settings, "PUBLIC_BASE_URL", "https://demo.example.app/", raising=False)


@pytest.fixture
def calls(monkeypatch):
    """記錄所有 requests 呼叫；每個測試自行設定 responses。"""
    rec = {"calls": [], "responses": {}}

    def fake_post(url, data=None, timeout=None):
        rec["calls"].append(("POST", url, data))
        return rec["responses"][url]

    def fake_get(url, params=None, timeout=None):
        rec["calls"].append(("GET", url, params))
        return rec["responses"][url]

    monkeypatch.setattr(auth.requests, "post", fake_post)
    monkeypatch.setattr(auth.requests, "get", fake_get)
    return rec


def test_authorize_url_has_scopes_and_redirect(cfg):
    url = auth.build_authorize_url("APPID123", "https://demo.example.app/")
    assert url.startswith("https://threads.com/oauth/authorize?")
    assert "client_id=APPID123" in url
    assert "redirect_uri=https://demo.example.app/oauth/callback" in url
    assert (
        "scope=threads_basic,threads_content_publish,threads_manage_replies,threads_manage_mentions" in url
    )
    assert "response_type=code" in url


@pytest.mark.parametrize(
    "raw",
    ["ABC#_", "  ABC#_\n", "ABC", "https://demo.example.app/oauth/callback?code=ABC#_"],
)
def test_clean_code(raw):
    assert auth.clean_code(raw) == "ABC"


def test_exchange_writes_complete_json(tmp_path, cfg, calls, capsys):
    calls["responses"] = {
        auth.SHORT_TOKEN_URL: FakeResp(200, {"access_token": "SHORT_TOK", "user_id": 987}),
        auth.LONG_TOKEN_URL: FakeResp(200, {"access_token": "LONG_TOK", "token_type": "bearer", "expires_in": SIXTY_DAYS}),
    }
    path = tmp_path / "threads_token.json"
    rc = auth.main([f"--token-file={path}"], input_fn=lambda _p: "CODE_X#_", now=NOW)
    assert rc == 0

    data = json.loads(path.read_text(encoding="utf-8"))
    assert set(data) == {"access_token", "obtained_at", "expires_at", "authorized_at", "user_id"}
    assert data["access_token"] == "LONG_TOK"
    assert data["user_id"] == "987"
    assert datetime.fromisoformat(data["obtained_at"]) == NOW
    assert datetime.fromisoformat(data["authorized_at"]) == NOW
    assert datetime.fromisoformat(data["expires_at"]) == NOW + timedelta(days=60)

    # 呼叫參數正確：code 去掉 #_、redirect_uri 一致、第二段帶短效 token
    method, url, form = calls["calls"][0]
    assert (method, url) == ("POST", auth.SHORT_TOKEN_URL)
    assert form == {
        "client_id": "APPID123",
        "client_secret": "SECRET456",
        "grant_type": "authorization_code",
        "redirect_uri": "https://demo.example.app/oauth/callback",
        "code": "CODE_X",
    }
    method, url, params = calls["calls"][1]
    assert (method, url) == ("GET", auth.LONG_TOKEN_URL)
    assert params["grant_type"] == "th_exchange_token"
    assert params["access_token"] == "SHORT_TOK"

    out = capsys.readouterr().out
    assert "user_id=987" in out and "token_days_left=60" in out
    assert "LONG_TOK" not in out and "SHORT_TOK" not in out and "SECRET456" not in out


def test_reauthorize_keeps_authorized_at(tmp_path, cfg, calls):
    path = tmp_path / "threads_token.json"
    first = "2026-07-01T00:00:00+00:00"
    path.write_text(json.dumps({"access_token": "OLD", "authorized_at": first, "user_id": "1"}), encoding="utf-8")
    calls["responses"] = {
        auth.SHORT_TOKEN_URL: FakeResp(200, {"access_token": "S", "user_id": "1"}),
        auth.LONG_TOKEN_URL: FakeResp(200, {"access_token": "L", "expires_in": SIXTY_DAYS}),
    }
    assert auth.main([f"--token-file={path}"], input_fn=lambda _p: "C", now=NOW) == 0
    assert json.loads(path.read_text(encoding="utf-8"))["authorized_at"] == first


def test_http_400_exits_nonzero_and_writes_nothing(tmp_path, cfg, calls, capsys):
    calls["responses"] = {
        auth.SHORT_TOKEN_URL: FakeResp(400, {"error": {"message": "Invalid code", "code": 100}}),
    }
    path = tmp_path / "threads_token.json"
    rc = auth.main([f"--token-file={path}"], input_fn=lambda _p: "BAD", now=NOW)
    assert rc != 0
    assert not path.exists()
    assert list(tmp_path.iterdir()) == []
    assert "HTTP 400" in capsys.readouterr().out


def test_long_exchange_400_writes_nothing(tmp_path, cfg, calls, capsys):
    calls["responses"] = {
        auth.SHORT_TOKEN_URL: FakeResp(200, {"access_token": "SHORT_TOK", "user_id": "1"}),
        auth.LONG_TOKEN_URL: FakeResp(400, {"error": "bad access_token=SHORT_TOK"}),
    }
    path = tmp_path / "threads_token.json"
    assert auth.main([f"--token-file={path}"], input_fn=lambda _p: "C", now=NOW) != 0
    assert not path.exists()
    assert "SHORT_TOK" not in capsys.readouterr().out


def test_missing_config_exits_nonzero(tmp_path, monkeypatch, calls):
    monkeypatch.setattr(settings, "THREADS_APP_ID", "", raising=False)
    monkeypatch.setattr(settings, "THREADS_APP_SECRET", "", raising=False)
    monkeypatch.setattr(settings, "PUBLIC_BASE_URL", "", raising=False)
    path = tmp_path / "threads_token.json"
    assert auth.main([f"--token-file={path}"], input_fn=lambda _p: "C", now=NOW) == 1
    assert calls["calls"] == [] and not path.exists()


def _seed(path, obtained_at):
    data = {
        "access_token": "OLD_TOK",
        "obtained_at": obtained_at.isoformat(),
        "expires_at": (obtained_at + timedelta(days=60)).isoformat(),
        "authorized_at": "2026-09-01T00:00:00+00:00",
        "user_id": "987",
    }
    path.write_text(json.dumps(data), encoding="utf-8")
    return data


def test_refresh_rejects_token_younger_than_24h(tmp_path, calls, capsys):
    path = tmp_path / "threads_token.json"
    seeded = _seed(path, NOW - timedelta(hours=23))
    rc = auth.main(["--refresh", f"--token-file={path}"], now=NOW)
    assert rc == 2
    assert "token_too_young" in capsys.readouterr().out
    assert calls["calls"] == []
    assert json.loads(path.read_text(encoding="utf-8")) == seeded


def test_refresh_after_24h_extends_expiry_and_keeps_authorized_at(tmp_path, calls, capsys):
    path = tmp_path / "threads_token.json"
    seeded = _seed(path, NOW - timedelta(hours=25))
    calls["responses"] = {
        auth.REFRESH_URL: FakeResp(200, {"access_token": "NEW_TOK", "token_type": "bearer", "expires_in": SIXTY_DAYS}),
    }
    rc = auth.main(["--refresh", f"--token-file={path}"], now=NOW)
    assert rc == 0

    method, url, params = calls["calls"][0]
    assert (method, url) == ("GET", auth.REFRESH_URL)
    assert params == {"grant_type": "th_refresh_token", "access_token": "OLD_TOK"}

    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["access_token"] == "NEW_TOK"
    assert datetime.fromisoformat(data["expires_at"]) > datetime.fromisoformat(seeded["expires_at"])
    assert datetime.fromisoformat(data["expires_at"]) == NOW + timedelta(days=60)
    assert datetime.fromisoformat(data["obtained_at"]) == NOW
    assert data["authorized_at"] == seeded["authorized_at"]
    assert data["user_id"] == "987"
    out = capsys.readouterr().out
    assert "NEW_TOK" not in out and "OLD_TOK" not in out


def test_refresh_http_error_keeps_file(tmp_path, calls):
    path = tmp_path / "threads_token.json"
    seeded = _seed(path, NOW - timedelta(days=2))
    calls["responses"] = {auth.REFRESH_URL: FakeResp(400, {"error": "expired"})}
    assert auth.main(["--refresh", f"--token-file={path}"], now=NOW) == 1
    assert json.loads(path.read_text(encoding="utf-8")) == seeded


def test_refresh_without_file_fails(tmp_path, calls):
    assert auth.main(["--refresh", f"--token-file={tmp_path / 'none.json'}"], now=NOW) == 1


def test_refresh_refuses_when_obtained_at_missing(tmp_path, calls, capsys):
    path = tmp_path / "threads_token.json"
    seeded = {"access_token": "OLD_TOK", "expires_at": "2026-10-01T00:00:00+00:00", "user_id": "987"}
    path.write_text(json.dumps(seeded), encoding="utf-8")
    assert auth.main(["--refresh", f"--token-file={path}"], now=NOW) == 1
    assert "token_age_unknown" in capsys.readouterr().out
    assert calls["calls"] == []
    assert json.loads(path.read_text(encoding="utf-8")) == seeded


def test_refresh_refuses_when_obtained_at_unparseable(tmp_path, calls, capsys):
    path = tmp_path / "threads_token.json"
    seeded = {"access_token": "OLD_TOK", "obtained_at": "not-a-date", "user_id": "987"}
    path.write_text(json.dumps(seeded), encoding="utf-8")
    assert auth.main(["--refresh", f"--token-file={path}"], now=NOW) == 1
    assert "token_age_unknown" in capsys.readouterr().out
    assert calls["calls"] == []
    assert json.loads(path.read_text(encoding="utf-8")) == seeded


def test_refresh_missing_expires_in_defaults_to_60_days(tmp_path, calls):
    path = tmp_path / "threads_token.json"
    _seed(path, NOW - timedelta(days=2))
    calls["responses"] = {auth.REFRESH_URL: FakeResp(200, {"access_token": "NEW_TOK", "token_type": "bearer"})}
    assert auth.main(["--refresh", f"--token-file={path}"], now=NOW) == 0
    data = json.loads(path.read_text(encoding="utf-8"))
    assert datetime.fromisoformat(data["expires_at"]) == NOW + timedelta(days=60)


def test_exchange_missing_expires_in_defaults_to_60_days(tmp_path, cfg, calls, capsys):
    calls["responses"] = {
        auth.SHORT_TOKEN_URL: FakeResp(200, {"access_token": "S", "user_id": "1"}),
        auth.LONG_TOKEN_URL: FakeResp(200, {"access_token": "L"}),
    }
    path = tmp_path / "threads_token.json"
    assert auth.main([f"--token-file={path}"], input_fn=lambda _p: "C", now=NOW) == 0
    data = json.loads(path.read_text(encoding="utf-8"))
    assert datetime.fromisoformat(data["expires_at"]) == NOW + timedelta(days=60)
    assert "token_days_left=60" in capsys.readouterr().out


def test_error_body_secret_straddling_300_chars_is_fully_redacted(tmp_path, cfg, calls, capsys):
    secret = "SECRET456"
    # 讓 secret 橫跨第 300 個字元：先截斷再遮蔽會殘留前半段
    body_text = "x" * 295 + secret + "y" * 50

    class RawResp:
        status_code = 400
        text = body_text

        def json(self):
            raise ValueError

    calls["responses"] = {auth.SHORT_TOKEN_URL: RawResp()}
    path = tmp_path / "threads_token.json"
    assert auth.main([f"--token-file={path}"], input_fn=lambda _p: "C", now=NOW) == 1
    out = capsys.readouterr().out
    assert "HTTP 400" in out
    assert "SECRE" not in out
    assert not path.exists()
