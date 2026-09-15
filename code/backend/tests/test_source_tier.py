"""來源分級測試（FN-12）：全離線，Cofacts GraphQL 一律 mock，零網路、零 AI 點數。"""
import asyncio
import time

import pytest
import requests

import app.utils.source_tier as st


class _FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def _article_payload(types):
    return {"data": {"GetArticle": {
        "id": "abc",
        "articleReplies": [{"reply": {"type": t}} for t in types],
    }}}


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    """預設任何 requests.post 都視為測試失敗（確保離線），並清 LRU 避免案例互相污染。"""
    st.cofacts_has_verdict.cache_clear()

    def _boom(*a, **kw):
        raise AssertionError("unexpected network call")

    monkeypatch.setattr(st.requests, "post", _boom)
    yield
    st._cofacts_verdict_cached.cache_clear()


TIER_CASES = [
    pytest.param("https://gov.tw.evil.com/x", "", 3, id="gov_tw_evil_com_tier3"),
    pytest.param("https://news.google.com/rss/articles/abc", "查核：網傳疫苗有晶片是假的", 3,
                 id="google_news_rss_tier3"),
    pytest.param("https://www.mygopen.com/2026/09/post.html", "某某活動資訊整理", 1,
                 id="mygopen_any_title_tier1"),
    pytest.param("https://www.ettoday.net/news/20260901/1.htm", "查核：網傳換SIM卡會被盜帳號是假的", 2,
                 id="ettoday_factcheck_title_tier2"),
    pytest.param("https://www.ettoday.net/news/20260901/2.htm", "颱風明天登陸 北部停班停課", 3,
                 id="ettoday_plain_title_tier3"),
    pytest.param("https://tfc-taiwan.org.tw/articles/1234", "", 1, id="tfc_tier1"),
    pytest.param("https://165.npa.gov.tw/#/article/1", "", 1, id="gov_tw_subdomain_tier1"),
    pytest.param("https://gov.tw/", "", 1, id="gov_tw_apex_tier1"),
    pytest.param("https://www.cdc.gov.tw/Category/1", "", 1, id="cdc_gov_tw_tier1"),
    pytest.param("https://www.who.int/news", "", 1, id="who_int_tier1"),
    pytest.param("https://www.cdc.gov/flu", "", 1, id="cdc_gov_tier1"),
    pytest.param("https://notgov.tw/x", "", 3, id="notgov_tw_suffix_tier3"),
    pytest.param("https://mygopen.com.evil.io/x", "", 3, id="mygopen_lookalike_tier3"),
    pytest.param("https://www.threads.com/@x/post/1", "澄清：網傳消息不實", 3, id="threads_tier3"),
    pytest.param("https://www.facebook.com/p/1", "闢謠：假的", 3, id="facebook_tier3"),
    pytest.param("https://line.me/R/ti/p/x", "網傳謠言", 3, id="line_me_tier3"),
    pytest.param("https://cofacts.tw/article/abc", "", 3, id="cofacts_offline_tier3"),
    pytest.param("", "查核：網傳是假的", 3, id="empty_url_tier3"),
    pytest.param("ftp://gov.tw/x", "", 3, id="non_http_scheme_tier3"),
    pytest.param("https://example.com/a", "", 3, id="no_title_tier3"),
]


@pytest.mark.parametrize("url,title,expected", TIER_CASES)
def test_tier_table(url, title, expected):
    # offline=True：表格測試保證不發請求（Cofacts 有/無回覆另以 mock 測）
    assert st.tier_of(url, title, offline=True) == expected


def test_tier_labels():
    assert st.TIER_LABELS == {1: "查核機構", 2: "媒體查核報導", 3: "相關討論（未查證）"}


def test_cofacts_with_reply_mock_tier1(monkeypatch):
    monkeypatch.setattr(st.requests, "post",
                        lambda *a, **kw: _FakeResp(_article_payload(["RUMOR"])))
    assert st.tier_of("https://cofacts.tw/article/abc") == 1
    st.cofacts_has_verdict.cache_clear()
    monkeypatch.setattr(st.requests, "post",
                        lambda *a, **kw: _FakeResp(_article_payload(["NOT_RUMOR"])))
    assert st.tier_of("https://cofacts.g0v.tw/article/xyz") == 1


def test_cofacts_no_reply_tier3(monkeypatch):
    monkeypatch.setattr(st.requests, "post",
                        lambda *a, **kw: _FakeResp(_article_payload([])))
    assert st.tier_of("https://cofacts.tw/article/abc") == 3
    st.cofacts_has_verdict.cache_clear()
    # 只有意見回覆（OPINIONATED / NOT_ARTICLE）也不算判定
    monkeypatch.setattr(st.requests, "post",
                        lambda *a, **kw: _FakeResp(_article_payload(["OPINIONATED", "NOT_ARTICLE"])))
    assert st.tier_of("https://cofacts.tw/article/def") == 3


def test_cofacts_timeout_tier3(monkeypatch):
    def _timeout(*a, **kw):
        raise requests.Timeout("slow")

    monkeypatch.setattr(st.requests, "post", _timeout)
    assert st.tier_of("https://cofacts.tw/article/abc") == 3
    assert st.cofacts_has_verdict("abc") is False


def test_offline_cofacts_no_request(monkeypatch):
    calls = []
    monkeypatch.setattr(st.requests, "post", lambda *a, **kw: calls.append(1))
    assert st.tier_of("https://cofacts.tw/article/abc", offline=True) == 3
    assert st.tier_of("https://cofacts.g0v.tw/article/abc", "查核：網傳是假的", offline=True) == 3
    assert len(calls) == 0


def test_graphql_endpoint_url(monkeypatch):
    seen = {}

    def _capture(url, *a, **kw):
        seen["url"] = url
        seen["json"] = kw.get("json")
        return _FakeResp(_article_payload(["RUMOR"]))

    monkeypatch.setattr(st.requests, "post", _capture)
    assert st.cofacts_has_verdict("abc123") is True
    assert seen["url"] == "https://api.cofacts.tw/graphql"
    assert st.COFACTS_GRAPHQL_URL == "https://api.cofacts.tw/graphql"
    assert seen["json"]["variables"] == {"id": "abc123"}


def test_cofacts_lru_cache_hits_once(monkeypatch):
    calls = []

    def _post(*a, **kw):
        calls.append(1)
        return _FakeResp(_article_payload(["RUMOR"]))

    monkeypatch.setattr(st.requests, "post", _post)
    assert st.cofacts_has_verdict("same") is True
    assert st.cofacts_has_verdict("same") is True
    assert len(calls) == 1


def test_tier2_delegates_to_news_fetcher(monkeypatch):
    from app.services import news_fetcher

    seen = []

    def _fake(title):
        seen.append(title)
        return True

    monkeypatch.setattr(news_fetcher, "_title_indicates_debunk", _fake)
    assert st.tier_of("https://example.com/news/1", "任意標題") == 2
    assert seen == ["任意標題"]

    monkeypatch.setattr(news_fetcher, "_title_indicates_debunk", lambda t: False)
    assert st.tier_of("https://example.com/news/1", "查核：網傳是假的") == 3


def test_grade_sources_splits_and_labels(monkeypatch):
    monkeypatch.setattr(
        st.requests, "post",
        lambda url, json=None, **kw: _FakeResp(
            _article_payload(["RUMOR"] if json["variables"]["id"] == "yes" else [])),
    )
    sources = [
        {"title": "TFC", "url": "https://tfc-taiwan.org.tw/articles/1"},
        {"title": "查核：網傳換SIM卡是假的", "url": "https://www.ettoday.net/news/1.htm"},
        {"title": "有回覆", "url": "https://cofacts.tw/article/yes"},
        {"title": "無回覆", "url": "https://cofacts.tw/article/no"},
        "https://news.google.com/rss/articles/abc",
    ]
    tiered, related, tier_ms = asyncio.run(st.grade_sources(sources))
    assert [s["tier"] for s in tiered] == [1, 2, 1]
    assert [s["tier_label"] for s in tiered] == ["查核機構", "媒體查核報導", "查核機構"]
    assert [s["url"] for s in related] == [
        "https://cofacts.tw/article/no", "https://news.google.com/rss/articles/abc"]
    assert all(s["tier"] == 3 and s["tier_label"] == "相關討論（未查證）" for s in related)
    assert isinstance(tier_ms, int) and tier_ms >= 0


def test_grade_sources_total_timeout_tier3(monkeypatch):
    monkeypatch.setattr(st, "GRADE_TOTAL_TIMEOUT_SECONDS", 0.05)

    def _slow(article_id):
        time.sleep(0.3)
        return True

    monkeypatch.setattr(st, "cofacts_has_verdict", _slow)
    tiered, related, _ = asyncio.run(st.grade_sources(
        [{"title": "", "url": "https://cofacts.tw/article/slow"}]))
    assert tiered == []
    assert related[0]["tier"] == 3


def test_grade_sources_timeout_keeps_finished_results(monkeypatch):
    """總逾時到時，已完成的快速判定（Tier 1）不得被同批慢查詢拖累降級。"""
    monkeypatch.setattr(st, "GRADE_TOTAL_TIMEOUT_SECONDS", 0.3)

    def _lookup(article_id):
        if article_id == "slow":
            time.sleep(1.0)
            return True
        return True

    monkeypatch.setattr(st, "cofacts_has_verdict", _lookup)
    tiered, related, _ = asyncio.run(st.grade_sources([
        {"title": "", "url": "https://cofacts.tw/article/fast"},
        {"title": "", "url": "https://cofacts.tw/article/slow"},
    ]))
    assert [s["url"] for s in tiered] == ["https://cofacts.tw/article/fast"]
    assert tiered[0]["tier"] == 1
    assert [s["url"] for s in related] == ["https://cofacts.tw/article/slow"]
    assert related[0]["tier"] == 3


def test_grade_sources_empty():
    assert asyncio.run(st.grade_sources([]))[:2] == ([], [])
    assert asyncio.run(st.grade_sources(None))[:2] == ([], [])
