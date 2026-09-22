"""熱門牆補抓的安全性（離線、零 AI）。

- _cleanup_legacy_strings 不得把 Cofacts 已查核的謠言退回未查證（Cofacts 的判定來自 RUMOR 回覆，
  標題本來就沒有【錯誤】標籤）；MyGoPen／TFC 沒有不實標籤的 MISINFO 仍照既有規則退回。
- fetch_rss_items 擋下非查核文章（徵才、闢謠 TOP10、小考題），並可略過 Cofacts。
- POST /api/trending/refresh 把 analyze／per_feed／cofacts 傳給背景工作。
"""
import asyncio

import pytest
from fastapi import BackgroundTasks
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.api.trending as trending_api
import app.services.news_fetcher as nf
import app.services.search_service as ss
from app.database_sql import Base
from app.models.fact_check_record import FactCheckRecord


@pytest.fixture
def db(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)
    monkeypatch.setattr(nf, "SessionLocal", session)
    indexed = []
    monkeypatch.setattr(nf, "_index_factcheck_claim", lambda url, title, source: indexed.append(url))
    return session, indexed


def _add(session, url, title, risk_type, label_source="rule"):
    s = session()
    s.add(FactCheckRecord(source_url=url, news_title=title, risk_type=risk_type, is_trending=True,
                          label_source=label_source, verified=True))
    s.commit()
    s.close()


def _risk(session, url):
    s = session()
    try:
        return s.query(FactCheckRecord).filter_by(source_url=url).one().risk_type
    finally:
        s.close()


def test_cleanup_keeps_cofacts_rumours_and_still_fixes_fact_checker_records(db):
    session, indexed = db
    cofacts = "https://cofacts.tw/article/abc123"
    untagged = "https://www.mygopen.com/2026/09/news.html"
    tagged = "https://www.mygopen.com/2026/09/false.html"
    _add(session, cofacts, "辦理過程中不會讓您出一分錢", "MISINFO")
    _add(session, untagged, "一篇沒有判定標籤的說明文章", "MISINFO", label_source="ai")
    _add(session, tagged, "【錯誤】網傳喝檸檬水能殺死癌細胞？", "PENDING", label_source=None)

    nf._cleanup_legacy_strings()

    assert _risk(session, cofacts) == "MISINFO"
    assert _risk(session, untagged) == "PENDING"
    assert _risk(session, tagged) == "MISINFO" and indexed == [tagged]


@pytest.mark.parametrize("title", [
    "【徵才】台灣事實查核中心 – 誠徵資深查核記者 / 特約查核記者",
    "【2026/9/14-2026/9/20】闢謠TOP10",
    "本週闢謠 top 10",
    "【活動】全民查核小考題",
])
def test_non_factcheck_posts_are_recognised(title):
    assert ss._is_non_factcheck_post(title)


@pytest.mark.parametrize("title", [
    "【錯誤】網傳紅豆營養比牛肉高？不同類別不應直接比較！",
    "娃娃菜冰3週不壞的秘密 關鍵是採後處理、冷鏈技術",
    "【事實查核】「中國拒絕烏克蘭延後償債」的消息，源自可信度低的中國社群文章",
    "",
])
def test_fact_check_articles_are_kept(title):
    assert not ss._is_non_factcheck_post(title)


RSS = """<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel>
<item><title>【錯誤】網傳某說法？</title><link>https://www.mygopen.com/2026/09/a.html</link></item>
<item><title>【徵才】誠徵查核記者</title><link>https://www.mygopen.com/2026/09/job.html</link></item>
<item><title>【2026/9/14-2026/9/20】闢謠TOP10</title><link>https://www.mygopen.com/2026/09/top10.html</link></item>
</channel></rss>""".encode("utf-8")


def test_fetch_drops_non_factcheck_posts_and_can_skip_cofacts(monkeypatch):
    class Resp:
        status_code = 200
        content = RSS

    def no_cofacts(num=5):
        raise AssertionError("include_cofacts=False 不得呼叫 Cofacts")

    monkeypatch.setattr(ss.requests, "get", lambda url, **kwargs: Resp())
    monkeypatch.setattr(ss.SearchService, "_fetch_cofacts", staticmethod(no_cofacts))

    items = ss.SearchService.fetch_rss_items(num_per_feed=10, include_cofacts=False)

    assert [i["title"] for i in items] == ["【錯誤】網傳某說法？"]


def test_refresh_passes_its_options_to_the_background_fetch():
    tasks = BackgroundTasks()
    body = asyncio.run(trending_api.trigger_refresh(tasks, analyze=False, per_feed=25, cofacts=False))
    assert body["analyze"] is False and body["per_feed"] == 25 and body["cofacts"] is False
    assert tasks.tasks[0].kwargs == {"analyze_pending": False, "per_feed": 25, "include_cofacts": False}
