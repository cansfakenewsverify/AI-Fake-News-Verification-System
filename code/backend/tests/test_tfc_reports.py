"""台灣事實查核中心的查核報告（app/services/tfc_client.py）接進熱門牆抓取。全部離線、零 AI。

- 判定來自 WordPress「查核結果」分類：錯誤、部分錯誤 → 確定不實（verdict=FALSE）；事實釐清、證據不足不算判定。
- 主張優先用同標題的謠言原文，其次是標題裡看得出的主張（news_fetcher._claim_for_index）；新版標題寫的是
  結論（「健保署不會用 LINE 通知健保卡異常」），抽不出主張的報告不列、不寫知識庫，熱門牆改以「網傳「主張」」呈現。
- REST 失敗時退回 RSS；_cleanup_legacy_strings 不得把沒有【錯誤】標籤的查核報告退回未查證。
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.services.news_fetcher as nf
import app.services.search_service as ss
from app.database_sql import Base
from app.models.fact_check_record import FactCheckRecord
from app.services import tfc_client
from app.services.cache_service import CacheService
from app.services.pandas_store import PandasStore

REPORT_URL = "https://tfc-taiwan.org.tw/fact-check-reports/fine-payment-installments-not-no-jail-misleading-claim/"
REPORT_TITLE = "考量經濟弱勢處境，法務部延長易科罰金分期。 網傳「輕罪不用關、罰金可分期」說法，誤解修訂內容。"
RUMOR = "請問你知道自己在講什麼嗎⋯⋯ 死刑不執行、毒詐氾濫罰金還可分期？？？ 輕罪不要關？少關人、多放人…. 監獄滿了？"
CLASSES = [{"id": 128, "slug": "incorrect"}, {"id": 127, "slug": "partially-incorrect"},
           {"id": 129, "slug": "fact-clarification"}, {"id": 126, "slug": "correct"}]


def _report(link, title, classes, excerpt="<p>社群平台流傳圖卡。</p>"):
    return {"id": 1, "date": "2026-09-22T10:00:00", "link": link, "title": {"rendered": title},
            "excerpt": {"rendered": excerpt}, "fact-check-report-classification": classes}


def _rumor(title, text):
    return {"id": 2, "date": "2026-09-22T09:00:00", "link": "https://tfc-taiwan.org.tw/rumor-sources/x/",
            "title": {"rendered": title}, "content": {"rendered": f"<p>{text}</p>"}}


class _Resp:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"http {self.status_code}")

    def json(self):
        return self._payload


def _fake_api(reports, rumors):
    def get(url, params=None, **kwargs):
        if url.endswith("/fact-check-report-classification"):
            return _Resp(CLASSES)
        if url.endswith("/fact-check-reports"):
            return _Resp(reports)
        if url.endswith("/rumor-sources"):
            return _Resp(rumors)
        raise AssertionError(f"unexpected url {url}")
    return get


@pytest.fixture(autouse=True)
def _fresh_classes():
    tfc_client.classification_slugs.cache_clear()
    yield
    tfc_client.classification_slugs.cache_clear()


# ── tfc_client ─────────────────────────────────────────────────────
def test_label_of_only_counts_definite_verdicts():
    assert tfc_client.label_of(["incorrect"]) == "MISINFO"
    assert tfc_client.label_of(["partially-incorrect"]) == "MISINFO"
    assert tfc_client.label_of(["correct"]) == "SAFE"
    assert tfc_client.label_of(["fact-clarification"]) is None
    assert tfc_client.label_of(["evidence-insufficient"]) is None
    assert tfc_client.label_of(["incorrect", "correct"]) is None       # 互相矛盾
    assert tfc_client.label_of([]) is None


def test_quoted_claim_and_title_matching():
    assert tfc_client.quoted_claim(REPORT_TITLE) == "輕罪不用關、罰金可分期"
    assert tfc_client.quoted_claim("網傳影片不是真的富士山煙火") is None
    assert tfc_client.norm_title(REPORT_TITLE) == tfc_client.norm_title(REPORT_TITLE.rstrip("。") + " ")


def test_latest_reports_reads_the_classification(monkeypatch):
    monkeypatch.setattr(tfc_client.requests, "get", _fake_api([_report(REPORT_URL, REPORT_TITLE, [128])], []))
    [rep] = tfc_client.latest_reports(5)
    assert rep["url"] == REPORT_URL and rep["label"] == "MISINFO"
    assert rep["classification"] == ["incorrect"] and rep["summary"] == "社群平台流傳圖卡。"


def test_short_rumor_captions_are_ignored():
    rows = [_rumor(REPORT_TITLE, "這什麼鬼啦？"), _rumor(REPORT_TITLE, RUMOR)]
    assert tfc_client.rumor_texts_by_title(rows) == {tfc_client.norm_title(REPORT_TITLE): [RUMOR]}


# ── search_service：熱門牆抓取 ────────────────────────────────────────
def test_fetch_uses_tfc_reports_with_rumour_text_as_the_claim(monkeypatch):
    reports = [
        _report(REPORT_URL, REPORT_TITLE, [128]),
        _report("https://tfc-taiwan.org.tw/fact-check-reports/b/", "網傳「颱風天停班一律要補班」說法，事實釐清", [129]),
        _report("https://tfc-taiwan.org.tw/fact-check-reports/c/", "網路流傳「別再買這10款超商麵包」影片，過於誇大", [127]),
        _report("https://tfc-taiwan.org.tw/fact-check-reports/d/", "健保署不會用LINE、電話或簡訊，通知健保卡異常", [128]),
    ]
    monkeypatch.setattr(ss.requests, "get", _fake_api(reports, [_rumor(REPORT_TITLE.rstrip("。"), RUMOR)]))
    items = ss.SearchService._fetch_tfc_reports(4)
    # 事實釐清不是判定；結論句標題抽不出被查核的主張 → 都不列
    assert [i["url"].rsplit("/", 2)[-2] for i in items] == [REPORT_URL.rsplit("/", 2)[-2], "c"]
    assert all(i["verdict"] == "FALSE" and i["source"] == "TFC" for i in items)
    assert items[0]["claim"] == RUMOR and items[0]["title"].startswith("網傳「請問你知道自己在講什麼嗎")
    assert items[1]["claim"] == "別再買這10款超商麵包" and items[1]["title"] == "網傳「別再買這10款超商麵包」"
    assert items[1]["summary"].startswith("網路流傳「別再買這10款超商麵包」影片")      # 報告原標題留在摘要


def test_claim_for_index_only_takes_identifiable_claims():
    assert nf._claim_for_index("【錯誤】網傳紅豆營養比牛肉高？不同類別不應直接比較") == "紅豆營養比牛肉高"
    assert nf._claim_for_index("【錯誤】網傳「出國換SIM卡會被過戶」！查核") == "「出國換SIM卡會被過戶」"   # 與既有索引一致
    assert nf._claim_for_index("【易誤解】普悠瑪本來就沒有安全帶，火車上不適合安全帶設計") == ""      # 說明文字，不是問句
    assert nf._claim_for_index("網傳影片「芋頭的仇人是香蕉」說法不實，兩者同吃不會中毒") == "芋頭的仇人是香蕉"
    assert nf._claim_for_index("蝦皮不會以「簡訊驗證」發送優惠碼") == ""                                # 結論句
    assert nf._claim_for_index("健保署不會用LINE、電話或簡訊，通知健保卡異常") == ""


def test_fetch_skips_tfc_rss_when_the_reports_api_works(monkeypatch):
    seen = []

    def get(url, params=None, **kwargs):
        seen.append(url)
        if "wp-json" in url:
            return _fake_api([_report(REPORT_URL, REPORT_TITLE, [128])], [])(url, params)
        return _Resp(None, status=404)

    monkeypatch.setattr(ss.requests, "get", get)
    monkeypatch.setattr(tfc_client, "latest_rumor_texts",
                        lambda n: {tfc_client.norm_title(REPORT_TITLE): [RUMOR]})
    items = ss.SearchService.fetch_rss_items(num_per_feed=4, include_cofacts=False)
    assert [i["url"] for i in items] == [REPORT_URL]
    assert not any(u.startswith("https://tfc-taiwan.org.tw/feed") or "?feed=" in u for u in seen)


def test_fetch_falls_back_to_rss_when_the_reports_api_fails(monkeypatch):
    rss = ("<?xml version=\"1.0\" encoding=\"UTF-8\"?><rss version=\"2.0\"><channel><item>"
           "<title>【錯誤】網傳某說法？</title><link>https://tfc-taiwan.org.tw/articles/1</link>"
           "</item></channel></rss>").encode("utf-8")

    class Rss:
        status_code = 200
        content = rss

    def get(url, params=None, **kwargs):
        if "wp-json" in url:
            raise ConnectionError("reports api down")
        return Rss()

    monkeypatch.setattr(ss.requests, "get", get)
    items = ss.SearchService.fetch_rss_items(num_per_feed=4, include_cofacts=False)
    assert "https://tfc-taiwan.org.tw/articles/1" in [i["url"] for i in items]


# ── news_fetcher：寫入熱門牆與知識庫 ─────────────────────────────────
@pytest.fixture
def db(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)
    monkeypatch.setattr(nf, "SessionLocal", session)
    return session


def _record(session, url):
    s = session()
    try:
        return s.query(FactCheckRecord).filter_by(source_url=url).one()
    finally:
        s.close()


def test_tfc_false_verdict_is_marked_and_indexed_with_the_rumour_text(db, monkeypatch):
    indexed = []
    monkeypatch.setattr(nf, "_index_factcheck_claim", lambda url, title, source, claim=None: indexed.append(claim))
    nf._save_rss_record({"url": REPORT_URL, "title": REPORT_TITLE, "summary": "摘要", "source": "TFC",
                         "verdict": "FALSE", "claim": RUMOR})
    rec = _record(db, REPORT_URL)
    assert rec.risk_type == "MISINFO" and rec.label_source == "rule"
    assert indexed == [RUMOR]


def test_tfc_report_without_a_verdict_stays_unverified(db, monkeypatch):
    monkeypatch.setattr(nf, "_index_factcheck_claim", lambda *a, **k: pytest.fail("must not index"))
    url = "https://tfc-taiwan.org.tw/fact-check-reports/b/"
    nf._save_rss_record({"url": url, "title": "網傳「颱風天停班一律要補班」說法，事實釐清", "source": "TFC",
                         "verdict": None, "claim": "颱風天停班一律要補班"})
    assert _record(db, url).risk_type in (None, "", "PENDING")


def test_cleanup_keeps_untagged_tfc_reports_marked_false(db, monkeypatch):
    monkeypatch.setattr(nf, "_index_factcheck_claim", lambda *a, **k: None)
    s = db()
    s.add(FactCheckRecord(source_url=REPORT_URL, news_title=REPORT_TITLE, risk_type="MISINFO",
                          is_trending=True, label_source="rule", verified=True))
    s.add(FactCheckRecord(source_url="https://tfc-taiwan.org.tw/articles/2", news_title="一篇沒有判定標籤的說明",
                          risk_type="MISINFO", is_trending=True, label_source="ai", verified=True))
    s.commit()
    s.close()
    nf._cleanup_legacy_strings()
    assert _record(db, REPORT_URL).risk_type == "MISINFO"                              # 判定來自查核結果分類
    assert _record(db, "https://tfc-taiwan.org.tw/articles/2").risk_type == "PENDING"  # 既有規則不變


def test_index_accepts_a_long_rumour_text_with_many_commas(tmp_path, monkeypatch):
    store = PandasStore(data_dir=str(tmp_path))

    class Vec:
        def vectorize_content(self, text):
            return [0.1] * 1536

    monkeypatch.setattr(nf, "_pandas_store", store)
    monkeypatch.setattr(nf, "_vector", Vec())
    rumour = "，".join(["死刑不執行", "毒詐氾濫", "罰金還可分期", "輕罪不要關", "少關人", "多放人", "監獄滿了", "壓力很大",
                        "世界跟不上台灣", "請大家轉傳給親朋好友讓大家都知道這件事情真的太誇張了"])
    assert len(rumour) > 60 and rumour.count("，") >= 8                               # 標題抽主張時會被當成標籤雲
    nf._index_factcheck_claim(REPORT_URL, REPORT_TITLE, {"name": "台灣事實查核中心", "category": "已查核假訊息"},
                              claim=rumour)
    row = store.get_all_records().iloc[0]
    assert row["raw_content"] == rumour and row["data_hash"] == CacheService.generate_hash(rumour)
    assert row["label_source"] == "rule" and bool(row["verified"]) is True
    assert row["summary"].endswith("…」")                                              # 摘要只放前 60 字
