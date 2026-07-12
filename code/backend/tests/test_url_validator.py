"""URL 驗證測試：AI 幻覺連結過濾（monkeypatch 網路呼叫，離線可跑）。"""
import app.utils.url_validator as uv


def test_filter_valid_sources_drops_dead(monkeypatch):
    alive = {"https://ok.example.com/", "https://good.example.com/x"}
    monkeypatch.setattr(uv, "_is_url_alive", lambda u, timeout=3.0: u in alive)

    sources = [
        {"title": "活的", "url": "https://ok.example.com/"},
        {"title": "幻覺", "url": "https://hallucinated.example.com/404"},
        "https://good.example.com/x",
    ]
    kept = uv.filter_valid_sources(sources)
    assert len(kept) == 2
    assert {"title": "活的", "url": "https://ok.example.com/"} in kept
    assert "https://good.example.com/x" in kept


def test_filter_valid_sources_empty():
    assert uv.filter_valid_sources([]) == []


def test_is_url_alive_rejects_non_http():
    assert uv._is_url_alive("") is False
    assert uv._is_url_alive("ftp://x") is False
