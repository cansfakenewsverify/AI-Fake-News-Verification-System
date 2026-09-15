"""FR-18 / FN-14 清洗腳本（D-03：知識庫規則 1、2；D-04：熱門規則 3、4、--apply 冪等）。
全離線：Cofacts GraphQL 與 safe_url.safe_get 以 mock 取代，requests 被封鎖；資料全在 tmp_path。"""
import hashlib
import importlib.util
import json
from pathlib import Path

import pandas as pd
import pytest

from fixtures.clean_fixture import (
    COFACTS_FLAKY,
    COFACTS_REPLIED,
    COFACTS_UNANSWERED,
    default_kb_rows,
    kb_row,
    make_kb_parquet,
    make_trending_db,
    trending_rows_d04,
)
from app.utils.safe_url import FetchTimeout, SafeResponse  # noqa: E402

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "clean_sources_2026_09.py"
_spec = importlib.util.spec_from_file_location("clean_sources_script", _SCRIPT)
clean = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(clean)

from app.services.news_fetcher import _is_real_claim  # noqa: E402

REPLIES = {
    COFACTS_REPLIED: ("has_reply", ["RUMOR"]),
    COFACTS_UNANSWERED: ("no_reply", []),
}


class FakeCofacts:
    def __init__(self, answers=None):
        self.answers = dict(REPLIES if answers is None else answers)
        self.calls = []

    def __call__(self, article_id):
        self.calls.append(article_id)
        return self.answers.get(article_id, ("error", []))


RESOLVED_OK = "https://www.cna.com.tw/news/aipl/202609010001.aspx"
RESOLVED_DUP = "https://tfc-taiwan.org.tw/articles/1234"
GOOGLE_ANSWERS = {
    "https://news.google.com/rss/articles/dup": RESOLVED_DUP,
    "https://news.google.com/rss/articles/ok": RESOLVED_OK,
    "https://news.google.com/rss/articles/stay": "https://news.google.com/articles/stay?hl=zh-TW",
    "https://news.google.com/rss/articles/rule-stay": "https://news.google.com/rss/articles/rule-stay",
    # default fixture row: unresolvable
}


class FakeSafeGet:
    """Stands in for app.utils.safe_url.safe_get: known urls resolve, the rest time out."""

    def __init__(self, answers=None):
        self.answers = dict(GOOGLE_ANSWERS if answers is None else answers)
        self.calls = []

    def __call__(self, url, method="GET", **kwargs):
        self.calls.append((method, url))
        if url in self.answers:
            return SafeResponse(status_code=200, url=self.answers[url])
        raise FetchTimeout("mock timeout")


@pytest.fixture
def fake_cofacts(monkeypatch):
    fake = FakeCofacts()

    def _no_network(*a, **k):
        raise AssertionError("network access in offline test")

    monkeypatch.setattr(clean.requests, "post", _no_network)
    monkeypatch.setattr(clean.requests, "request", _no_network)
    monkeypatch.setattr(clean, "query_cofacts", fake)
    monkeypatch.setattr(clean, "safe_get", FakeSafeGet())
    return fake


@pytest.fixture
def fake_resolver(monkeypatch, fake_cofacts):
    fake = FakeSafeGet()
    monkeypatch.setattr(clean, "safe_get", fake)
    return fake


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _rows_from_parquet(path: Path):
    return {r["id"]: r for r in pd.read_parquet(path).to_dict("records")}


def _checker(tmp_path, fake, retry=False):
    return clean.CofactsChecker(tmp_path / clean.CACHE_FILE, retry_failed=retry, query=fake)


def test_kb_dry_run_does_not_touch_files(tmp_path, fake_cofacts):
    kb = make_kb_parquet(tmp_path)
    db = make_trending_db(tmp_path)
    before = {p: (p.stat().st_mtime_ns, _sha(p)) for p in (kb, db)}

    assert clean.main(["--data-dir", str(tmp_path)]) == 0
    assert clean.main(["--only=kb", "--dry-run", "--data-dir", str(tmp_path)]) == 0

    for p, (mtime, sha) in before.items():
        assert p.stat().st_mtime_ns == mtime
        assert _sha(p) == sha
    assert not list(tmp_path.glob("*.bak-*"))
    report = (tmp_path / clean.REPORT_FILE).read_text(encoding="utf-8")
    assert f"知識庫總筆數：{len(default_kb_rows())}" in report
    assert "label_source=rule 被降級：0 筆" in report
    assert "DRY-RUN" in report


def test_kb_rule_label_never_downgraded(tmp_path, fake_cofacts):
    rows = [
        kb_row("r-tier3", "網傳政府將發放每人一萬元補助金",
               sources=[{"title": "一般新聞", "url": "https://news.example.com/b"}], label_source="rule"),
        kb_row("r-chat", "ok 好", sources=[], label_source="rule"),
        kb_row("r-cofacts", "網傳某銀行帳戶即將凍結請點連結", label_source="rule",
               source_url=f"https://cofacts.tw/article/{COFACTS_UNANSWERED}"),
        kb_row("g-none", "網傳某地區明天將全面停水一整天", sources=[], label_source="gold"),
    ]
    kb = make_kb_parquet(tmp_path, rows)
    checker = _checker(tmp_path, fake_cofacts)
    for row in _rows_from_parquet(kb).values():
        new, _ = clean.clean_kb_row(row, checker, _is_real_claim)
        assert new["verified"] is True, row["id"]
        assert new["content_vector"] is not None, row["id"]

    clean.main(["--only=kb", "--data-dir", str(tmp_path)])
    report = (tmp_path / clean.REPORT_FILE).read_text(encoding="utf-8")
    assert "label_source=rule 被降級：0 筆" in report
    assert "label_source in (rule, gold, admin) 被降級：0 筆" in report
    # QA-5 evidence: the check states how many protected rows it examined
    assert "QA-5 檢核範圍：label_source rule=3, gold=1, admin=0（共 4 筆受保護）" in report
    assert "QA-5 注意" not in report


def test_kb_qa5_report_flags_vacuous_check_and_groups_by_domain(tmp_path, fake_cofacts):
    # legacy seed shape: no label_source column at all -> every row defaults to ai
    rows = [{k: v for k, v in r.items() if k != "label_source"}
            for r in default_kb_rows() if r["id"] != "kb-rule"]
    make_kb_parquet(tmp_path, rows)
    clean.main(["--only=kb", "--data-dir", str(tmp_path)])
    report = (tmp_path / clean.REPORT_FILE).read_text(encoding="utf-8")
    assert "（共 0 筆受保護）" in report
    assert "QA-5 注意" in report
    assert "依 source_url 網域分組" in report
    assert "  cofacts.tw: 1 / 1" in report
    assert "  tfc-taiwan.org.tw: 1 / 1" in report
    assert "  (無 source_url): 2 / 2" in report


def test_kb_source_url_backfill_and_items_carry_tier(tmp_path, fake_cofacts):
    kb = make_kb_parquet(tmp_path)
    checker = _checker(tmp_path, fake_cofacts)
    out = {rid: clean.clean_kb_row(row, checker, _is_real_claim) for rid, row in _rows_from_parquet(kb).items()}

    new, rules = out["kb-backfill"]
    assert new["sources"] == [{
        "title": "網傳喝熱水可以殺死病毒是假的",
        "url": "https://www.mygopen.com/2026/05/hot-water.html",
        "tier": 1, "tier_label": "查核機構",
    }]
    assert new["source_tier"] == 1 and new["verified"] is True and "rule1" in rules

    new, _ = out["kb-mixed"]
    assert [s["url"] for s in new["sources"]] == ["https://tfc-taiwan.org.tw/articles/1"]
    assert all(s["tier"] in (1, 2) and s["tier_label"] for s in new["sources"])
    related = json.loads(new["related_discussions"])
    assert [(r["url"], r["tier"]) for r in related] == [("https://blog.example.com/p/2", 3)]

    new, _ = out["kb-tier3-ai"]
    assert new["sources"] == [] and new["source_tier"] is None and new["verified"] is False

    # Cofacts with a reply stays Tier 1 (the offline grader alone would say 3)
    new, _ = out["kb-cofacts-yes"]
    assert new["sources"][0]["tier"] == 1 and new["verified"] is True
    assert new["content_vector"] is not None

    # rule 2: unanswered Cofacts and chat fragments are not indexed
    for rid in ("kb-cofacts-no", "kb-chat"):
        new, rules = out[rid]
        assert new["verified"] is False and new["content_vector"] is None and "rule2" in rules

    # rerunning on already-cleaned values changes nothing (idempotent grading)
    cleaned = dict(_rows_from_parquet(kb)["kb-mixed"])
    cleaned.update(out["kb-mixed"][0])
    again, rules = clean.clean_kb_row(cleaned, checker, _is_real_claim)
    assert rules == [] and again["sources"] == out["kb-mixed"][0]["sources"]

    # rule 1 (Tier 1 backfill) + rule 2 (not a claim): verified ends false, and a second
    # pass over the cleaned values must not re-flag rule 1 (final values drive detection)
    new, rules = out["kb-tier1-nonclaim"]
    assert new["source_tier"] == 1 and new["verified"] is False and new["content_vector"] is None
    assert set(rules) == {"rule1", "rule2"}
    cleaned = dict(_rows_from_parquet(kb)["kb-tier1-nonclaim"])
    cleaned.update(new)
    again, rules = clean.clean_kb_row(cleaned, checker, _is_real_claim)
    assert rules == [], rules


def test_cofacts_cache_reused_no_network(tmp_path, fake_cofacts, monkeypatch):
    make_kb_parquet(tmp_path)
    clean.main(["--only=kb", "--data-dir", str(tmp_path)])
    assert sorted(set(fake_cofacts.calls)) == sorted([COFACTS_REPLIED, COFACTS_UNANSWERED])
    assert len(fake_cofacts.calls) == 2  # one lookup per article even if referenced twice
    cache = json.loads((tmp_path / clean.CACHE_FILE).read_text(encoding="utf-8"))
    assert cache[COFACTS_REPLIED]["status"] == "has_reply"
    assert cache[COFACTS_UNANSWERED]["status"] == "no_reply"

    second = FakeCofacts(answers={})
    monkeypatch.setattr(clean, "query_cofacts", second)
    clean.main(["--only=kb", "--data-dir", str(tmp_path)])
    assert second.calls == []
    report = (tmp_path / clean.REPORT_FILE).read_text(encoding="utf-8")
    assert "本次網路查詢 0 次" in report
    assert f"{COFACTS_REPLIED} | 有回覆" in report
    assert f"{COFACTS_UNANSWERED} | 無回覆" in report


def test_retry_cofacts_only_failed(tmp_path, fake_cofacts, monkeypatch):
    rows = default_kb_rows() + [
        kb_row("kb-flaky", "網傳某疫苗含有追蹤晶片",
               source_url=f"https://cofacts.tw/article/{COFACTS_FLAKY}", sources=[]),
    ]
    make_kb_parquet(tmp_path, rows)
    cache_path = tmp_path / clean.CACHE_FILE
    cache_path.write_text(json.dumps({
        COFACTS_REPLIED: {"status": "has_reply", "types": ["RUMOR"], "url": ""},
        COFACTS_UNANSWERED: {"status": "no_reply", "types": [], "url": ""},
        COFACTS_FLAKY: {"status": "timeout", "types": [], "url": ""},
    }), encoding="utf-8")

    # without --retry-cofacts the failed entry is reused as-is (zero network)
    clean.main(["--only=kb", "--data-dir", str(tmp_path)])
    assert fake_cofacts.calls == []
    report = (tmp_path / clean.REPORT_FILE).read_text(encoding="utf-8")
    assert f"{COFACTS_FLAKY} | 查詢失敗(timeout)" in report

    # retry that fails again: entry is NOT overwritten
    failing = FakeCofacts(answers={COFACTS_FLAKY: ("error", [])})
    monkeypatch.setattr(clean, "query_cofacts", failing)
    clean.main(["--only=kb", "--retry-cofacts", "--data-dir", str(tmp_path)])
    assert failing.calls == [COFACTS_FLAKY]
    assert json.loads(cache_path.read_text(encoding="utf-8"))[COFACTS_FLAKY]["status"] == "timeout"

    # retry that succeeds: only the failed article is queried and the cache is overwritten
    ok = FakeCofacts(answers={COFACTS_FLAKY: ("has_reply", ["NOT_RUMOR"])})
    monkeypatch.setattr(clean, "query_cofacts", ok)
    clean.main(["--only=kb", "--retry-cofacts", "--data-dir", str(tmp_path)])
    assert ok.calls == [COFACTS_FLAKY]
    cache = json.loads(cache_path.read_text(encoding="utf-8"))
    assert cache[COFACTS_FLAKY]["status"] == "has_reply"
    assert cache[COFACTS_REPLIED]["status"] == "has_reply"
    report = (tmp_path / clean.REPORT_FILE).read_text(encoding="utf-8")
    assert f"{COFACTS_FLAKY} | 有回覆" in report


# ──────────────────────────────────────────
# D-04: trending rules 3, 4 and --apply
# ──────────────────────────────────────────
def _db_rows(path: Path):
    import sqlite3

    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    try:
        return {r["id"]: dict(r) for r in con.execute("SELECT * FROM fact_check_records")}
    finally:
        con.close()


def _report(tmp_path):
    return (tmp_path / clean.REPORT_FILE).read_text(encoding="utf-8")


def test_google_news_resolved_overwrite_and_dedupe(tmp_path, fake_resolver):
    db = make_trending_db(tmp_path, trending_rows_d04())
    checker = _checker(tmp_path, clean.query_cofacts)
    plan = clean.plan_trending(list(_db_rows(db).values()), checker, clean.GoogleNewsResolver(checker))

    assert plan["new_url"]["tr-google-ok"] == RESOLVED_OK
    assert "tr-google-ok" not in plan["delete"]
    # same (normalised title, domain) as the earlier TFC row -> the later resolved row is dropped
    assert "tr-google-dup" in plan["delete"] and "tr-tfc-early" not in plan["delete"]
    assert clean.normalize_title("網傳喝檸檬水治癌 查核：錯誤 - 台灣事實查核中心") == \
        clean.normalize_title("網傳喝檸檬水治癌 查核：錯誤")

    assert clean.main(["--only=trending", "--apply", "--data-dir", str(tmp_path)]) == 0
    rows = _db_rows(db)
    assert rows["tr-google-ok"]["source_url"] == RESOLVED_OK
    assert "tr-google-dup" not in rows and "tr-tfc-early" in rows
    assert not any("news.google.com" in (r["source_url"] or "") for r in rows.values())
    report = _report(tmp_path)
    assert f"tr-google-ok | 某地停電原因說明 | 解析成功→{RESOLVED_OK}" in report
    assert "tr-google-dup | " in report and "去重→刪除（保留 tr-tfc-early）" in report
    # resolver tried HEAD first; every call went through the mocked safe_get
    assert ("HEAD", "https://news.google.com/rss/articles/ok") in fake_resolver.calls


def test_google_news_unresolved_row_deleted(tmp_path, fake_resolver):
    db = make_trending_db(tmp_path, trending_rows_d04())
    before = _sha(db)
    assert clean.main(["--only=trending", "--data-dir", str(tmp_path)]) == 0  # dry-run first
    assert _sha(db) == before and not list(tmp_path.glob("*.bak-*"))
    report = _report(tmp_path)
    assert "tr-google-bad | 無法解析的新聞 | 失敗→刪除" in report
    assert "tr-google-stay | 仍在 Google 的新聞 | 失敗→刪除" in report
    assert "tr-google-rule | 【錯誤】網傳某地淹水照片 | 失敗→刪除" in report
    # HEAD failed -> GET retried before giving up
    assert [m for m, u in fake_resolver.calls if u.endswith("/bad")] == ["HEAD", "GET"]

    # deletions are reported by label_source: a deleted rule row is never hidden
    assert "熱門 label_source=rule 被降級：0 筆" in report
    assert "熱門 label_source=rule 被刪除：1 筆" in report
    assert "熱門 label_source in (rule, gold, admin) 被刪除：1 筆" in report
    assert "熱門刪除依 label_source／risk_type 分組：共 4 筆" in report
    assert "  ai: 3（MISINFO=1, SAFE=1, UNVERIFIABLE=1）" in report
    assert "  rule: 1（MISINFO=1）" in report
    assert "注意（D-05 前需負責人決定）" in report

    # "still Google" is not a definitive outcome: never cached, retried next run
    cache = json.loads((tmp_path / clean.CACHE_FILE).read_text(encoding="utf-8"))
    google_cache = cache.get(clean.GOOGLE_CACHE_KEY, {})
    assert not any("news.google.com" in (v.get("final_url") or "") for v in google_cache.values())
    assert "https://news.google.com/rss/articles/stay" not in google_cache
    fake_resolver.calls.clear()
    clean.main(["--only=trending", "--data-dir", str(tmp_path)])
    assert ("HEAD", "https://news.google.com/rss/articles/stay") in fake_resolver.calls

    # a legacy cache entry that stored a Google final_url is ignored (re-resolved)
    cache[clean.GOOGLE_CACHE_KEY] = {"https://news.google.com/rss/articles/rule-stay": {
        "final_url": "https://news.google.com/rss/articles/rule-stay", "reason": "GET 200"}}
    (tmp_path / clean.CACHE_FILE).write_text(json.dumps(cache), encoding="utf-8")
    fake_resolver.calls.clear()
    clean.main(["--only=trending", "--data-dir", str(tmp_path)])
    assert ("HEAD", "https://news.google.com/rss/articles/rule-stay") in fake_resolver.calls

    clean.main(["--only=trending", "--apply", "--data-dir", str(tmp_path)])
    rows = _db_rows(db)
    assert "tr-google-bad" not in rows and "tr-google-stay" not in rows and "tr-google-rule" not in rows
    assert len(rows) == len(trending_rows_d04()) - 4


def test_trending_rule_label_verified_true(tmp_path, fake_resolver):
    db = make_trending_db(tmp_path, trending_rows_d04())
    clean.main(["--only=trending", "--apply", "--data-dir", str(tmp_path)])
    rows = _db_rows(db)
    assert rows["tr-rule"]["verified"] == 1 and rows["tr-rule"]["source_tier"] == 3
    assert rows["tr-ai-mygopen"]["verified"] == 1 and rows["tr-ai-mygopen"]["source_tier"] == 1
    assert rows["tr-cofacts-yes"]["verified"] == 1 and rows["tr-cofacts-yes"]["source_tier"] == 1
    assert rows["tr-cofacts-no"]["verified"] == 0 and rows["tr-cofacts-no"]["source_tier"] == 3
    assert rows["tr-google-ok"]["verified"] == 0 and rows["tr-google-ok"]["source_tier"] == 3
    assert rows["tr-pending"]["verified"] == 0  # no label_source -> false even on a Tier 1 url
    assert "熱門 label_source=rule 被降級：0 筆" in _report(tmp_path)


def test_owner_drop_ids_removes_rows_and_is_idempotent(tmp_path, fake_resolver):
    kb = make_kb_parquet(tmp_path)
    db = make_trending_db(tmp_path, trending_rows_d04())
    kb_ids = list(_rows_from_parquet(kb))
    drop_file = tmp_path / "drop.txt"
    drop_file.write_text(f"kb\t{kb_ids[0]}\ntrending\ttr-ai-mygopen\ntrending\ttr-google-bad\nbogus line\n",
                         encoding="utf-8")

    # dry-run: nothing written, report lists the owner-approved deletions
    kb_sha, db_sha = _sha(kb), _sha(db)
    assert clean.main(["--drop-ids", str(drop_file), "--data-dir", str(tmp_path)]) == 0
    assert _sha(kb) == kb_sha and _sha(db) == db_sha
    report = _report(tmp_path)
    assert "負責人核准刪除（D-05 決定 2）：1 筆" in report
    assert "負責人核准刪除（D-05 決定 2，不含規則 3 已刪者）：1 筆" in report  # tr-google-bad already rule 3

    assert clean.main(["--apply", "--drop-ids", str(drop_file), "--data-dir", str(tmp_path)]) == 0
    assert kb_ids[0] not in _rows_from_parquet(kb)
    assert len(_rows_from_parquet(kb)) == len(kb_ids) - 1
    rows = _db_rows(db)
    assert "tr-ai-mygopen" not in rows and "tr-google-bad" not in rows

    kb_after, db_after = _sha(kb), _sha(db)
    assert clean.main(["--apply", "--drop-ids", str(drop_file), "--data-dir", str(tmp_path)]) == 0
    assert "負責人核准刪除（D-05 決定 2）：0 筆" in _report(tmp_path)
    assert len(_rows_from_parquet(kb)) == len(kb_ids) - 1 and len(_db_rows(db)) == len(rows)
    assert _sha(db) == db_after


def test_apply_twice_idempotent_with_backups(tmp_path, fake_resolver, monkeypatch):
    kb = make_kb_parquet(tmp_path)
    db = make_trending_db(tmp_path, trending_rows_d04())

    assert clean.main(["--apply", "--data-dir", str(tmp_path)]) == 0
    first = _report(tmp_path)
    assert "APPLY" in first
    # the row that used to re-flag rule 1 forever (Tier 1 backfill + not a claim) is in play
    assert "kb-tier1-nonclaim | " in first
    backups = sorted(p.name for p in tmp_path.glob("*.bak-*"))
    assert len(backups) == 2
    assert any(b.startswith("knowledge_base.parquet.bak-") for b in backups)
    assert any(b.startswith("factcheck.db.bak-") for b in backups)
    # backups hold the pre-apply data
    assert any("news.google.com" in (r["source_url"] or "")
               for r in _db_rows(tmp_path / [b for b in backups if b.startswith("factcheck")][0]).values())

    kb_after_1 = pd.read_parquet(kb).to_dict("records")
    db_after_1 = _db_rows(db)

    # second run: zero network (Google + Cofacts outcomes cached) and zero impact everywhere
    no_net = FakeSafeGet(answers={})
    monkeypatch.setattr(clean, "safe_get", no_net)
    monkeypatch.setattr(clean, "query_cofacts", FakeCofacts(answers={}))
    assert clean.main(["--apply", "--data-dir", str(tmp_path)]) == 0
    second = _report(tmp_path)
    assert "各規則影響筆數：rule1=0, rule2=0, rule3=0, rule4=0" in second
    assert no_net.calls == []

    assert _db_rows(db) == db_after_1
    kb_after_2 = pd.read_parquet(kb).to_dict("records")
    assert json.dumps(kb_after_2, default=str, sort_keys=True) == json.dumps(kb_after_1, default=str, sort_keys=True)
    assert sorted(p.name for p in tmp_path.glob("*.bak-*")) == backups
