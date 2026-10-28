"""信心程度驗證與模型比較的腳本（scripts/research_common.py、confidence_validation.py、model_benchmark.py）。

全部離線、零 AI：CGU 用量、embedding 與判讀都換成假的，資料寫在 tmp_path。
驗證額度護欄（保留額、每 100 題重讀用量、讀不到就不跑、週日不跑）、時間切分的最近鄰、分群、
重複內容的處理、開發組定門檻、四項過關標準，以及報告與逐題 CSV 不含訊息原文。
"""
import importlib.util
import json
import sys
from argparse import Namespace
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))


def _load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


rc = _load("research_common")
cv = _load("confidence_validation")
mb = _load("model_benchmark")


def _usage(remaining, cost=0.0):
    return {"cost_usd": cost, "quota_usd": 10.0, "remaining_usd": remaining}


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    """研究資料夾與結果資料夾都換到 tmp_path。"""
    research = tmp_path / "data" / "research"
    results = tmp_path / "docs" / "test" / "results"
    research.mkdir(parents=True)
    results.mkdir(parents=True)
    monkeypatch.setattr(rc, "REPO", tmp_path)
    monkeypatch.setattr(rc, "RESEARCH", research)
    monkeypatch.setattr(rc, "RAW", research / "raw")
    monkeypatch.setattr(rc, "CORPUS", research / "corpus.parquet")
    monkeypatch.setattr(rc, "RESULTS", results)
    monkeypatch.setattr(rc, "WEEKLY", results / "weekly")
    monkeypatch.setattr(rc, "STATUS", results / "research_status.json")
    monkeypatch.setattr(rc, "PF2_SETS", [])
    monkeypatch.setattr(cv, "QUESTIONS", research / "questions.parquet")
    monkeypatch.setattr(mb, "ITEMS", results / "model_benchmark_items.csv")
    monkeypatch.setattr(mb, "RUNS", results / "model_benchmark")
    return tmp_path


# ── 額度護欄 ─────────────────────────────────────────────────

def test_budget_keeps_the_reserve_for_site_users():
    b = rc.Budget(6.0, usage_fn=lambda: _usage(5.0))
    assert b.allowed == pytest.approx(2.0)          # min(6, 5 − 3)
    assert b.guard(1.5)
    b.record(1.5, 10)
    assert not b.guard(1.0)
    assert b.stop_reason == "budget"


def test_budget_refuses_when_usage_is_unreadable_or_reserve_reached():
    with pytest.raises(rc.BudgetError):
        rc.Budget(1.0, usage_fn=lambda: _usage(-1.0))
    with pytest.raises(rc.BudgetError):
        rc.Budget(1.0, usage_fn=lambda: _usage(2.5))


def test_budget_rereads_usage_every_100_items():
    calls = []
    values = iter([_usage(9.0), _usage(3.05)])

    def usage():
        calls.append(1)
        return next(values)

    b = rc.Budget(5.0, usage_fn=usage)
    for _ in range(4):
        assert b.guard(0.01, 25)
        b.record(0.01, 25)
    assert len(calls) == 1
    assert not b.guard(0.1, 25)                     # 第 100 題：重讀，剩 3.05 − 0.1 < 保留額
    assert b.stop_reason == "reserve" and len(calls) == 2


def test_budget_without_price_uses_usage_delta():
    values = iter([_usage(9.0, cost=1.0), _usage(8.0, cost=2.0)])
    b = rc.Budget(1.5, price_known=False, usage_fn=lambda: next(values))
    b.record(0.0, 20)
    assert not b.guard(0.6, 20)                     # 實際已花 1.0，再 0.6 就超過 1.5
    assert b.spent == pytest.approx(1.0)


def test_free_models_still_stop_at_the_reserve():
    values = iter([_usage(9.0), _usage(2.0)])
    b = rc.Budget(0.0, free=True, usage_fn=lambda: next(values))
    b.record(0, 100)
    assert not b.guard(0, 20)
    assert b.stop_reason == "reserve"


def test_no_spending_on_sunday_taipei():
    assert rc.spending_block_reason(datetime(2026, 11, 1, 10, tzinfo=rc.TZ_TAIPEI))      # 週日
    assert rc.spending_block_reason(datetime(2026, 10, 29, 10, tzinfo=rc.TZ_TAIPEI)) is None


def test_embed_and_run_refuse_on_sunday(sandbox, monkeypatch):
    monkeypatch.setattr(rc, "spending_block_reason", lambda now=None: "週日")
    assert cv.cmd_embed(Namespace(model="text-embedding-3-small", limit=50, max_usd=1.0, batch=50, latency_probe=0)) == 2
    assert mb.cmd_run(Namespace(model="gpt-5.6-luna", effort="medium", api="responses", limit=50, max_usd=1.0,
                                max_minutes=1)) == 2


# ── 語料與日期 ───────────────────────────────────────────────

def test_dated_query_adds_reply_dates_and_restores():
    original = rc.fc.COFACTS_QUERY
    with rc.dated_cofacts_query():
        assert "createdAt positiveFeedbackCount" in rc.fc.COFACTS_QUERY
    assert rc.fc.COFACTS_QUERY == original


def test_cofacts_verdict_date_is_first_endorsed_reply():
    node = {"id": "a1", "createdAt": "2025-01-01T00:00:00Z", "articleReplies": [
        {"createdAt": "2025-03-01T00:00:00Z", "positiveFeedbackCount": 2, "negativeFeedbackCount": 0, "reply": {"type": "RUMOR"}},
        {"createdAt": "2025-02-01T00:00:00Z", "positiveFeedbackCount": 0, "negativeFeedbackCount": 1, "reply": {"type": "RUMOR"}},
        {"createdAt": "2025-01-15T00:00:00Z", "positiveFeedbackCount": 3, "negativeFeedbackCount": 0, "reply": {"type": "OPINIONATED"}},
    ]}
    bare = {"id": "a2", "createdAt": "2025-05-05T00:00:00Z", "articleReplies": []}
    dates = rc.cofacts_verdict_dates([node, bare], "RUMOR")
    assert dates == {"https://cofacts.tw/article/a1": "2025-03-01", "https://cofacts.tw/article/a2": "2025-05-05"}


def test_nearest_earlier_only_sees_older_fact_checks():
    E = np.eye(4, dtype=np.float32)
    Q = np.array([[1, 0, 0, 0], [0.6, 0.8, 0, 0], [1, 0, 0, 0]], dtype=np.float32)
    sims, idx = rc.nearest_earlier(Q, ["2026-01-10", "2026-01-10", ""], ["q0", "q1", "q2"],
                                   E, ["2026-01-01", "2026-01-10", "2026-01-05", "2025-12-01"], ["e0", "e1", "q0", "e3"], k=2)
    assert idx[0].tolist() == [0, 3]                 # e1 同一天、q0 是自己 → 排除
    assert idx[1, 0] == 0 and sims[1, 0] == pytest.approx(0.6)   # e1（0.8）同一天發布，不能用
    assert idx[2].tolist() == [-1, -1]               # 沒有日期：不比對


def test_group_ids_join_same_url_and_near_duplicates():
    v = np.array([[1, 0], [0.95, np.sqrt(1 - 0.95 ** 2)], [0, 1], [0, 1]], dtype=np.float32)
    groups = rc.group_ids(["u1", "u2", "u3", "u1"], v, 0.90)
    assert groups[0] == groups[1] == groups[3]       # 0 與 1 相似、0 與 3 同網址
    assert groups[2] == groups[0]                    # 2 與 3 完全相同 → 也連進來
    assert rc.group_ids(["a", "b", "c"], np.eye(3, dtype=np.float32), 0.9) == [0, 1, 2]


def test_stats_helpers():
    assert rc.mcnemar_exact(5, 0) == pytest.approx(0.0625)     # 同 model_switch_2026-09-30.md
    assert rc.mcnemar_exact(0, 0) == 1.0
    assert rc.auroc([0.1, 0.4, 0.35, 0.8], [False, False, True, True]) == pytest.approx(0.75)
    assert rc.auroc([0.5, 0.5], [True, True]) is None


def test_embedding_store_roundtrip(sandbox):
    store = rc.EmbeddingStore("text-embedding-3-small")
    store.add("h1", [3.0, 4.0])
    store.save()
    again = rc.EmbeddingStore("text-embedding-3-small")
    assert "h1" in again and len(again) == 1
    assert again.matrix(["h1"])[0] == pytest.approx([0.6, 0.8], abs=1e-3)


def test_embed_call_splits_batches_the_model_rejects(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "CGU_API_KEY", "k")
    sent = []

    class Resp:
        def __init__(self, status, body):
            self.status_code, self._body = status, body

        def raise_for_status(self):
            if self.status_code >= 400:
                raise requests.HTTPError(response=self)

        def json(self):
            return self._body

    def post(url, headers, json, timeout):
        sent.append(len(json["input"]))
        if len(json["input"]) > 1:
            return Resp(400, {})
        return Resp(200, {"data": [{"index": 0, "embedding": [1.0, 0.0]}], "usage": {"total_tokens": 3}})

    monkeypatch.setattr(rc.requests, "post", post)
    vectors, tokens = rc.embed_call("bge-m3:latest", ["甲", "乙"])
    assert sent == [2, 1, 1] and len(vectors) == 2 and tokens == 6

    monkeypatch.setattr(rc.requests, "post", lambda url, headers, json, timeout: Resp(400, {}))
    assert rc.embed_call("bge-m3:latest", ["甲", "乙"]) == ([None, None], 0)   # 單筆仍被拒：回 None，不中斷整批


def test_run_embedding_skips_rejected_texts(sandbox):
    store = rc.EmbeddingStore("bge-m3:latest")
    budget = rc.Budget(0.0, free=True, usage_fn=lambda: _usage(9.0))
    got = cv.run_embedding("bge-m3:latest", [("a", "甲"), ("b", "乙")], store, budget, batch=2,
                           embed=lambda model, texts: ([np.ones(3), None], 0))
    assert got["rejected"] == 1 and "a" in store and "b" not in store


# ── 信心驗證：題目 ───────────────────────────────────────────

def _weekly_rows():
    base = {"part": "history", "source": "Cofacts", "published": "", "usd": "0.001"}
    return pd.DataFrame([
        {**base, "run_date": "2026-10-19", "url": "u1", "content_hash": "h1", "gold": "MISINFO", "predicted": "MISINFO",
         "fallback": "False", "confidence_score": "0.9", "correct_risk": "True", "correct_exact": "True"},
        {**base, "run_date": "2026-10-26", "url": "u1", "content_hash": "h1", "gold": "MISINFO", "predicted": "UNVERIFIABLE",
         "fallback": "False", "confidence_score": "0.8", "correct_risk": "False", "correct_exact": "False"},
        {**base, "run_date": "2026-10-19", "url": "u2", "content_hash": "h2", "gold": "SAFE", "predicted": "SAFE",
         "fallback": "False", "confidence_score": "0.9", "correct_risk": "True", "correct_exact": "True"},
        {**base, "run_date": "2026-10-26", "url": "u2", "content_hash": "h2", "gold": "MISINFO", "predicted": "SAFE",
         "fallback": "False", "confidence_score": "0.9", "correct_risk": "False", "correct_exact": "False"},
        {**base, "run_date": "2026-10-26", "url": "u3", "content_hash": "h3", "gold": "MISINFO", "predicted": "",
         "fallback": "True", "confidence_score": "", "correct_risk": "", "correct_exact": ""},
        {**base, "run_date": "2026-10-26", "url": "u4", "content_hash": "h4", "gold": "MISINFO", "predicted": "MISINFO",
         "fallback": "False", "confidence_score": "0.9", "correct_risk": "True", "correct_exact": "True"},
    ])


def test_duplicates_count_once_with_the_earliest_verdict():
    unique, stats = cv.dedupe_questions(_weekly_rows())
    assert sorted(unique["content_hash"]) == ["h1", "h4"]          # h2 真值矛盾剔除、h3 AI 不可用
    assert unique.set_index("content_hash").loc["h1", "predicted"] == "MISINFO"   # 取較早那一週
    assert stats["repeated"] == 1 and stats["verdict_changed"] == 1 and stats["correctness_changed"] == 1
    assert stats["conflicting_gold"] == 1 and stats["fallback_rows"] == 1


def test_load_weekly_starts_at_calibration_v4(sandbox):
    rc.WEEKLY.mkdir(parents=True)
    rows = _weekly_rows()
    rows.iloc[:2].to_csv(rc.WEEKLY / "weekly_eval_2026-10-12.csv", index=False)
    rows.to_csv(rc.WEEKLY / "weekly_eval_2026-10-19.csv", index=False)
    assert len(cv.load_weekly("2026-10-19", rc.WEEKLY)) == len(rows)


def test_attach_texts_from_corpus_or_cofacts_article():
    corpus = pd.DataFrame([{"content_hash": rc.text_hash("語料裡的謠言內容文字"), "text": "語料裡的謠言內容文字",
                            "published": "2025-01-02", "verdict_date": "2025-01-03"}])
    body = "語料外的 Cofacts 訊息內容"
    questions = pd.DataFrame([
        {"content_hash": rc.text_hash("語料裡的謠言內容文字"), "source": "MyGoPen", "url": "m", "gold": "MISINFO", "published": ""},
        {"content_hash": rc.text_hash(body), "source": "Cofacts", "url": "https://cofacts.tw/article/xyz", "gold": "MISINFO",
         "published": "2026-10-20"},
        {"content_hash": "nope", "source": "TFC", "url": "t", "gold": "MISINFO", "published": ""},
    ])
    article = {"data": {"GetArticle": {"id": "xyz", "text": body, "createdAt": "2026-10-18T00:00:00Z", "articleReplies": [
        {"createdAt": "2026-10-19T00:00:00Z", "positiveFeedbackCount": 1, "negativeFeedbackCount": 0, "reply": {"type": "RUMOR"}}]}}}
    out, stats = cv.attach_texts(questions, corpus, cache=lambda name, fetch: article)
    assert out["found"].tolist() == ["corpus", "cofacts_article", "missing"]
    assert out["q_date"].tolist()[:2] == ["2025-01-02", "2026-10-18"]
    assert out["verdict_date"].tolist()[1] == "2026-10-19"
    assert stats["TFC:missing"] == 1


def test_texts_to_embed_puts_questions_first(sandbox):
    corpus = pd.DataFrame([{"use": "kb", "label": "MISINFO", "text": "乙"}, {"use": "analysis", "label": "SAFE", "text": "丙"}])
    questions = pd.DataFrame([{"text": "甲"}, {"text": None}, {"text": "乙"}])
    assert [t for _, t in cv.texts_to_embed(corpus, questions)] == ["甲", "乙", "丙"]


def test_run_embedding_stops_at_budget_and_saves(sandbox):
    store = rc.EmbeddingStore("text-embedding-3-large")
    budget = rc.Budget(0.001, usage_fn=lambda: _usage(9.0))
    todo = [(f"h{i}", "字" * 400) for i in range(10)]
    got = cv.run_embedding("text-embedding-3-large", todo, store, budget, batch=2,
                           embed=lambda model, texts: ([np.ones(3)] * len(texts), 400 * len(texts)))
    assert budget.stop_reason == "budget" and 0 < len(store) < 10
    assert got["tokens"] == 400 * len(store)
    assert rc.EmbeddingStore("text-embedding-3-large").vectors.keys() == store.vectors.keys()


# ── 信心驗證：門檻與標準 ─────────────────────────────────────

def test_derive_threshold_picks_the_lowest_qualifying_value():
    values = np.array([0.5] * 40 + [0.7] * 40)
    positive = np.array([False] * 40 + [True] * 37 + [False] * 3)
    mask = np.ones(80, bool)
    assert cv.derive_threshold(values, positive, mask, [0.5, 0.6, 0.7], 0.9) == 0.6
    assert cv.derive_threshold(values, positive, mask, [0.5, 0.6, 0.7], 0.99) == float("inf")


def _frame(rows):
    f = pd.DataFrame(rows, columns=["gold", "predicted", "level", "basis", "final", "cache_hit"])
    f["correct"] = cv.risk_correct(f["final"], f["gold"])
    return f


def test_criteria_pass_and_fail():
    rows = ([("MISINFO", "MISINFO", "中", "similar_case", "MISINFO", False)] * 95
            + [("SAFE", "MISINFO", "中", "similar_case", "MISINFO", False)] * 5
            + [("MISINFO", "MISINFO", "低", "ai_only", "MISINFO", False)] * 70
            + [("SAFE", "MISINFO", "低", "ai_only", "MISINFO", False)] * 30
            + [("MISINFO", "MISINFO", "高", "factchecked", "MISINFO", True)] * 50
            + [("MISINFO", "SAFE", "低", "conflict", "SAFE", False)] * 6
            + [("SAFE", "SAFE", "低", "conflict", "SAFE", False)] * 4
            + [("MISINFO", "SAFE", "低", "ai_only", "SAFE", False)] * 2
            + [("SAFE", "SAFE", "低", "ai_only", "SAFE", False)] * 18)
    c = cv.criteria(_frame(rows), np.ones(len(rows), bool))
    assert c["c1"]["mid"] == (95, 100) and c["c1"]["pass"]
    assert c["c2"]["hit"] == (50, 50) and c["c2"]["pass"]
    assert c["c3"]["ratio"] == pytest.approx(0.6 / 0.1) and c["c3"]["pass"]
    assert c["c4"]["share"] == (150, 250) and c["c4"]["pass"]
    assert c["all_pass"]
    worse = rows[:95] + [("SAFE", "MISINFO", "中", "similar_case", "MISINFO", False)] * 20 + rows[100:]
    assert not cv.criteria(_frame(worse), np.ones(len(worse), bool))["c1"]["pass"]   # 中 95/115 < 90%


def _synthetic(seed=3, dims=16):
    """10 個謠言主題（可入庫語料）＋5 個正常訊息主題；題目散在各主題附近。"""
    rng = np.random.default_rng(seed)
    centers = rng.normal(size=(15, dims))
    centers /= np.linalg.norm(centers, axis=1, keepdims=True)
    corpus, vectors, questions = [], {}, []

    def vec(c, noise):
        v = centers[c] + rng.normal(scale=noise, size=dims)
        return v / np.linalg.norm(v)

    for c in range(15):
        for j in range(8):
            text = f"原文標記{c}-{j}這是一段語料內容"
            h = rc.text_hash(text)
            risky = c < 10
            corpus.append({"source": "MyGoPen" if risky else "Cofacts", "kind": "x", "use": "kb" if risky else "analysis",
                           "label": "MISINFO" if risky else "SAFE", "verdict_raw": "", "text": text, "content_hash": h,
                           "url": f"https://example.org/{c}/{j}", "title": "", "published": f"2026-0{1 + j % 5}-01",
                           "requests": None, "scam_topic": False, "extra": "", "verdict_date": f"2026-0{1 + j % 5}-01"})
            vectors[h] = vec(c, 0.15)
    for i in range(240):
        c = i % 15
        risky = c < 10
        text = f"題目原文標記{i}請勿外流"
        h = rc.text_hash(text)
        vectors[h] = vec(c, 0.3 if i % 4 else 0.08)
        wrong = i % 9 == 0
        pred = ("SAFE" if wrong else "MISINFO") if risky else ("MISINFO" if wrong else ("UNVERIFIABLE" if i % 5 == 0 else "SAFE"))
        questions.append({"run_date": "2026-10-19", "part": "history", "source": "Cofacts", "url": f"https://cofacts.tw/article/q{i}",
                          "content_hash": h, "published": "", "gold": "MISINFO" if risky else "SAFE", "predicted": pred,
                          "fallback": "False", "confidence_score": "0.9", "correct_risk": "", "correct_exact": "", "usd": "",
                          "repeats": 1, "text": text, "q_date": "2026-07-01", "verdict_date": None, "found": "corpus"})
    return pd.DataFrame(corpus), pd.DataFrame(questions), vectors


def test_analyze_end_to_end_without_raw_text(sandbox, monkeypatch):
    monkeypatch.setattr(cv, "MIN_N", 5)
    corpus, questions, vectors = _synthetic()
    corpus.to_parquet(rc.CORPUS, index=False)
    questions.to_parquet(cv.QUESTIONS, index=False)
    store = rc.EmbeddingStore("text-embedding-3-small")
    for h, v in vectors.items():
        store.add(h, v)
    store.save()
    rc.update_status("confidence_fetch", {"dedupe": {"rows": 240, "unique": 240, "weeks": ["2026-10-19"]}, "matching": {}})
    assert cv.cmd_analyze(Namespace(models="text-embedding-3-small,text-embedding-3-large",
                                    group_model="text-embedding-3-small", since_note="2026-10-19")) == 0
    day = rc.run_date()
    report = (rc.RESULTS / f"confidence_validation_{day}.md").read_text(encoding="utf-8")
    per_q = (rc.RESULTS / f"confidence_validation_{day}.csv").read_text(encoding="utf-8")
    assert "信心驗證結論" in report and "`text-embedding-3-large` | 略過" in report
    assert "原文標記" not in report and "原文標記" not in per_q          # 不含訊息原文
    df = pd.read_csv(rc.RESULTS / f"confidence_validation_{day}.csv")
    assert set(df["split"]) == {"dev", "test"}
    assert df.groupby("group")["split"].nunique().max() == 1             # 同一群一定在同一組
    assert {"level_small", "nn_sim_small"} <= set(df.columns)
    status = json.loads(rc.STATUS.read_text(encoding="utf-8"))
    assert "text-embedding-3-small" in status["confidence_analyze"]["summary"]


# ── 模型比較 ─────────────────────────────────────────────────

def test_pick_items_one_per_group_with_recent_first():
    pool = pd.DataFrame({"content_hash": [f"h{i}" for i in range(10)], "url": [f"u{i}" for i in range(10)],
                         "published": ["2026-10-20", "2026-10-21"] + ["2024-01-01"] * 8})
    v = np.eye(10, dtype=np.float32)
    v[3] = v[2]                                       # 2、3 是同一則
    picked = mb.pick_items(pool, v, 5, date(2026, 10, 28))
    assert len(picked) == 5
    assert not {"h2", "h3"} <= set(picked["content_hash"])
    assert picked["recent"].sum() == 1                # 近期最多兩成（5 題 → 1 題）


def _items(n=6):
    return pd.DataFrame({"item_id": [str(i) for i in range(1, n + 1)], "content_hash": [f"h{i}" for i in range(1, n + 1)],
                         "url": [f"u{i}" for i in range(1, n + 1)], "source": ["Cofacts", "MyGoPen"] * (n // 2),
                         "gold": ["MISINFO", "SAFE"] * (n // 2), "published": ["2026-10-20"] * n,
                         "recent": ["True", "False"] * (n // 2), "freeze_date": ["2026-10-28"] * n})


def test_judge_records_errors_and_format_errors():
    item = _items().iloc[0].to_dict()

    def ok(model, effort, prompt):
        assert "【待分析內容】" in prompt
        return {"risk_type": "MISINFO", "usage": {"input_tokens": 1000, "output_tokens": 100}}

    def http(model, effort, prompt):
        raise requests.HTTPError(response=type("R", (), {"status_code": 429})())

    def bad(model, effort, prompt):
        raise ValueError("缺少必要欄位: sources")

    row = mb.judge(item, "內容", "gpt-5.6-luna", "medium", "responses", ok)
    assert row["predicted"] == "MISINFO" and row["usd"] > 0 and not row["error"]
    assert mb.judge(item, "內容", "gpt-5.6-luna", "medium", "responses", http)["error"] == "HTTP 429"
    fmt = mb.judge(item, "內容", "gpt-oss-120b", "none", "chat", bad)
    assert fmt["format_error"] and not fmt["error"] and "sources" in fmt["detail"]
    assert "內容" not in json.dumps(row, ensure_ascii=False)


def test_run_model_resumes_and_retries_failed_items(sandbox):
    items = _items()
    texts = {h: "某段訊息" for h in items["content_hash"]}
    out = mb.RUNS / "x.csv"
    calls = []

    def flaky(model, effort, prompt):
        calls.append(1)
        if len(calls) == 2:
            raise requests.ConnectionError()
        return {"risk_type": "SAFE", "usage": {"input_tokens": 10, "output_tokens": 1}}

    budget = rc.Budget(1.0, usage_fn=lambda: _usage(9.0))
    got = mb.run_model(items, texts, "gpt-5.6-luna", "medium", "responses", 3, budget, out, 5, call=flaky, concurrency=1)
    assert got == {"todo": 3, "answered": 2, "errors": 1}
    got = mb.run_model(items, texts, "gpt-5.6-luna", "medium", "responses", 0, budget, out, 5, call=flaky, concurrency=1)
    assert got["todo"] == 4                           # 失敗的那題重試＋還沒答的 3 題
    res = mb.load_results(out)
    assert len(res) == 6 and res["error"].eq("").all()


def test_report_table_and_mcnemar(sandbox):
    items = _items()
    items.to_csv(mb.ITEMS, index=False)
    mb.RUNS.mkdir(parents=True)

    def results(model, preds):
        rows = []
        for (_, it), p in zip(items.iterrows(), preds):
            rows.append({**{k: it[k] for k in ("item_id", "content_hash", "url", "source", "gold")}, "model": model,
                         "effort": "medium", "api": "responses", "predicted": p, "format_error": "False", "detail": "",
                         "error": "", "sec": "3.0", "input_tokens": "", "output_tokens": "", "usd": "0.001", "run_date": "x"})
        pd.DataFrame(rows, columns=mb.RESULT_COLUMNS).to_csv(mb.RUNS / f"{model}__medium.csv", index=False)

    results("gpt-5.6-luna", ["MISINFO", "SAFE", "SAFE", "SAFE", "UNVERIFIABLE", "SAFE"])
    results("gpt-6-luna", ["MISINFO", "SAFE", "MISINFO", "SAFE", "MISINFO", "MISINFO"])
    assert mb.cmd_report(Namespace()) == 0
    text = next(rc.RESULTS.glob("model_benchmark_*.md")).read_text(encoding="utf-8")
    assert "`gpt-6-luna` medium" in text and "（+2／−0）" in text
    s = mb.summarize(mb.load_results(mb.RUNS / "gpt-5.6-luna__medium.csv"))
    assert s["fn"] == 1 and s["unverifiable"] == 1 and s["correct"] == 4
    assert "完整系統：還沒有" in text                # 沒有語料向量時不硬算
