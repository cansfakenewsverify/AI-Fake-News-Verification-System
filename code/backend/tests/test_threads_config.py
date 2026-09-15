"""T-01：THREADS_MODE 與舊鍵 ENABLE_THREADS_BOT 的生效規則（離線、不讀本機 .env）。"""
import pytest
from pydantic import ValidationError

from app.config import Settings


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    # 系統環境變數優先序高於 .env / 預設值，先清掉以免干擾
    for key in ("THREADS_MODE", "ENABLE_THREADS_BOT", "DEMO_MODE",
                "BOT_HANDLE", "THREADS_MAX_REPLIES_PER_POLL", "THREADS_MAX_REPLIES_PER_DAY"):
        monkeypatch.delenv(key, raising=False)


def make(monkeypatch, **env):
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    return Settings(_env_file=None)


def test_default_is_off(monkeypatch):
    s = make(monkeypatch)
    assert s.THREADS_MODE is None
    assert s.threads_mode_effective == "off"


def test_defaults_for_new_keys(monkeypatch):
    s = make(monkeypatch)
    assert s.THREADS_MAX_REPLIES_PER_POLL == 5
    assert s.THREADS_MAX_REPLIES_PER_DAY == 50
    assert s.BOT_HANDLE == "factcheck_tw_bot"
    assert s.THREADS_APP_ID == "" and s.THREADS_APP_SECRET == ""


def test_legacy_enable_means_live(monkeypatch):
    s = make(monkeypatch, ENABLE_THREADS_BOT="true")
    assert s.threads_mode_effective == "live"


def test_explicit_off_beats_legacy(monkeypatch):
    s = make(monkeypatch, ENABLE_THREADS_BOT="true", THREADS_MODE="off")
    assert s.threads_mode_effective == "off"


def test_sim_beats_legacy(monkeypatch):
    s = make(monkeypatch, ENABLE_THREADS_BOT="true", THREADS_MODE="sim")
    assert s.threads_mode_effective == "sim"


def test_live_explicit(monkeypatch):
    assert make(monkeypatch, THREADS_MODE="live").threads_mode_effective == "live"


def test_demo_mode_does_not_affect_threads(monkeypatch):
    s = make(monkeypatch, THREADS_MODE="sim", DEMO_MODE="true")
    assert s.threads_mode_effective == "sim"


def test_empty_string_treated_as_unset(monkeypatch):
    s = make(monkeypatch, THREADS_MODE="", ENABLE_THREADS_BOT="true")
    assert s.THREADS_MODE is None
    assert s.threads_mode_effective == "live"


def test_invalid_value_rejected(monkeypatch):
    with pytest.raises(ValidationError):
        make(monkeypatch, THREADS_MODE="banana")
