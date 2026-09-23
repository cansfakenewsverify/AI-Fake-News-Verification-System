"""FR-17 知識庫寫入門檻（FN-13 / FN-11 / OP-7）。全部離線、零 AI、零網路。"""
import numpy as np
import pandas as pd
import pytest
import requests

from app.services.cache_service import CacheService
from app.services.pandas_store import PandasStore


def _vec(seed=7):
    return list(np.random.default_rng(seed).normal(size=1536).astype(float))


def _ai(sources, risk_type="SCAM"):
    return {
        "is_risk": risk_type != "SAFE", "risk_type": risk_type, "category": "Test",
        "confidence_score": 0.9, "summary": "摘要", "explanation": "解釋",
        "sources": sources,
    }


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    def _boom(*a, **k):
        raise AssertionError("save_record must not make network requests")
    monkeypatch.setattr(requests, "post", _boom)
    monkeypatch.setattr(requests, "get", _boom)


def _save(store, text, sources, **kwargs):
    h = CacheService.generate_hash(text)
    rec = store.save_record(
        data_type="TEXT", raw_content=text, content_hash=h,
        content_vector=kwargs.pop("vector", None), ai_result=_ai(sources), **kwargs,
    )
    return rec, h


def test_tier1_source_verified_true(tmp_path):
    store = PandasStore(data_dir=str(tmp_path))
    rec, _ = _save(store, "假冒165詐騙", [{"title": "165", "url": "https://165.npa.gov.tw/x"}])
    assert rec["id"]
    assert rec["verified"] is True
    assert rec["source_tier"] == 1
    assert rec["label_source"] == "ai"
    row = store.get_all_records().iloc[0]
    assert bool(row["verified"]) is True


def test_tier3_only_verified_false_and_vector_miss(tmp_path):
    store = PandasStore(data_dir=str(tmp_path))
    vec = _vec()
    rec, h = _save(
        store, "某部落格說法",
        [{"title": "部落格", "url": "https://blog.example.com/p"},
         {"title": "社群", "url": "https://www.facebook.com/x"}],
        vector=vec,
    )
    assert rec["verified"] is False
    assert rec["source_tier"] is None
    # 相似度 1.0（同一向量）仍不命中向量層
    assert store.find_similar_by_vector(vec, threshold=0.5) is None
    # L1 hash 層仍命中，且帶 verified=False
    hit = store.find_by_hash(h)
    assert hit is not None and bool(hit["verified"]) is False


def test_rule_label_empty_sources_verified_true(tmp_path):
    store = PandasStore(data_dir=str(tmp_path))
    rec, _ = _save(store, "規則命中的謠言", [], label_source="rule")
    assert rec["verified"] is True
    assert rec["label_source"] == "rule"


def test_explicit_verified_override(tmp_path):
    store = PandasStore(data_dir=str(tmp_path))
    rec, _ = _save(store, "覆寫", [{"title": "t", "url": "https://mygopen.com/a"}], verified=False)
    assert rec["verified"] is False
    rec2, _ = _save(store, "覆寫二", [], verified=True)
    assert rec2["verified"] is True


def test_source_url_backfilled_into_sources(tmp_path):
    store = PandasStore(data_dir=str(tmp_path))
    text = "網傳喝熱水可以殺死病毒這是一段超過四十個字的謠言內容，用來測試標題截斷是否正確運作喔"
    url = "https://tfc-taiwan.org.tw/articles/123"
    rec, h = _save(store, text, [], source_url=url, label_source="rule")
    assert rec["sources"] == [
        {"title": text[:40], "url": url, "tier": 1, "tier_label": "查核機構"}
    ]
    assert rec["source_tier"] == 1
    # Tier 3 的 source_url 不補
    rec3, _ = _save(store, "一般新聞", [], source_url="https://news.example.com/a")
    assert list(rec3["sources"]) == []
    assert rec3["verified"] is False


def test_saved_sources_carry_tier_and_label(tmp_path):
    store = PandasStore(data_dir=str(tmp_path))
    sources = [
        {"title": "MyGoPen", "url": "https://www.mygopen.com/2026/09/x.html"},
        {"title": "查核：網傳喝鹽水治新冠是假的", "url": "https://www.ettoday.net/news/1"},
        {"title": "一般新聞", "url": "https://www.ettoday.net/news/2"},
        {"title": "已分級", "url": "https://cofacts.tw/article/abc", "tier": 1},
    ]
    rec, h = _save(store, "分級測試", sources)
    assert rec["source_tier"] == 1

    for reloaded in (store.find_by_hash(h), store.get_all_records().iloc[0].to_dict()):
        for container in (reloaded["sources"], reloaded["ai_analysis"]["sources"]):
            items = list(container)
            assert len(items) == 4
            tiers = [int(s["tier"]) for s in items]
            assert tiers == [1, 2, 3, 1]
            for s in items:
                assert s["tier_label"] in ("查核機構", "媒體查核報導", "相關討論（未查證）")
    # 呼叫端的 dict 不被修改
    assert "tier" not in sources[0]


def test_load_old_parquet_defaults(tmp_path):
    old_cols = [
        "id", "data_type", "raw_content", "data_hash", "content_vector",
        "is_risk", "risk_type", "category", "confidence_score",
        "summary", "explanation", "sources", "ai_analysis",
        "created_at", "last_accessed_at", "hit_count",
    ]
    rows = []
    for i in range(3):
        rows.append({
            "id": f"old-{i}", "data_type": "TEXT", "raw_content": f"舊資料{i}",
            "data_hash": CacheService.generate_hash(f"舊資料{i}"),
            "content_vector": _vec(i), "is_risk": True, "risk_type": "MISINFO",
            "category": "Health", "confidence_score": 0.9, "summary": "s",
            "explanation": "e",
            "sources": [{"title": "t", "url": "https://mygopen.com/a"}],
            "ai_analysis": {"risk_type": "MISINFO", "summary": "s"},
            "created_at": pd.Timestamp("2026-07-01"),
            "last_accessed_at": pd.Timestamp("2026-07-01"), "hit_count": 1,
        })
    pd.DataFrame(rows, columns=old_cols).to_parquet(tmp_path / "knowledge_base.parquet", index=False)

    store = PandasStore(data_dir=str(tmp_path))
    df = store.get_all_records()
    assert len(df) == 3
    assert (df["label_source"] == "ai").all()
    assert (df["origin"] == "web").all()
    assert df["last_result_id"].isna().all()
    assert df["source_tier"].isna().all()
    assert (df["verified"] == False).all()  # noqa: E712
    assert df["related_discussions"].isna().all()
    assert df["source_url"].isna().all()
    # 舊列未清洗 → 不參與向量命中；hash 仍命中
    assert store.find_similar_by_vector(_vec(0), threshold=0.5) is None
    assert store.find_by_hash(CacheService.generate_hash("舊資料0")) is not None

    # 舊檔上再寫新列：筆數 +1、新欄位保留
    rec, _ = _save(store, "新資料", [{"title": "165", "url": "https://165.npa.gov.tw/"}], vector=_vec(99))
    df2 = store.get_all_records()
    assert len(df2) == 4
    new_row = df2[df2["id"] == rec["id"]].iloc[0]
    assert bool(new_row["verified"]) is True
    assert int(new_row["source_tier"]) == 1
    assert store.find_similar_by_vector(_vec(99), threshold=0.88)["id"] == rec["id"]


# ── B-15：任務處理器接上來源分級、verdict 與結果 v2 欄位 ─────────────────
import asyncio  # noqa: E402
import json  # noqa: E402

import app.workers.pandas_task_processor as proc  # noqa: E402
from app.services.ai_service import _default_fallback_result  # noqa: E402
from app.services.task_store import TaskStore  # noqa: E402

TIER1 = {"title": "165 反詐騙", "url": "https://165.npa.gov.tw/x"}
TIER2 = {"title": "查核：網傳喝鹽水治新冠是假的", "url": "https://www.ettoday.net/news/1"}
TIER3 = {"title": "部落格", "url": "https://blog.example.com/p"}


class _FakeAI:
    def __init__(self, result):
        self.result = result
        self.calls = 0

    def analyze_content(self, content, url=None, context=None, use_web_search=None):
        self.calls += 1
        return json.loads(json.dumps(self.result, ensure_ascii=False))


class _NoCrawler:
    async def process_input(self, data, input_type):
        raise AssertionError("文字輸入不得呼叫爬蟲")


def _patch_proc(monkeypatch, tmp_path, fake_ai, vector=None, alive=lambda s: s):
    monkeypatch.setattr(proc, "TaskStore", lambda: TaskStore(data_dir=str(tmp_path)))
    monkeypatch.setattr(proc, "PandasStore", lambda: PandasStore(data_dir=str(tmp_path)))
    monkeypatch.setattr(proc, "CrawlerService", _NoCrawler)
    monkeypatch.setattr(proc, "AIService", lambda: fake_ai)
    monkeypatch.setattr(proc, "filter_valid_sources", alive)

    class _Vec:
        def vectorize_content(self, text):
            return list(vector) if vector is not None else []

    monkeypatch.setattr(proc, "VectorService", _Vec)


def _run_proc(tmp_path, text):
    ts = TaskStore(data_dir=str(tmp_path))
    tid = ts.create_task("analyze_text", text)
    result = asyncio.run(proc.process_analysis_task_async(tid, text, "text"))
    return tid, result, ts.get_task(tid)


def test_validator_dead_tier1_verified_false(tmp_path, monkeypatch):
    # FN-13 iv：AI 給 Tier 1 來源，但 url_validator 判死 → verified=false、KB 列不參與向量命中
    fake = _FakeAI(_ai([TIER1], risk_type="SCAM"))
    vec = _vec(3)
    _patch_proc(monkeypatch, tmp_path, fake, vector=vec, alive=lambda s: [])
    tid, result, task = _run_proc(tmp_path, "假冒165客服要求轉帳")

    assert result["verified"] is False
    assert result["verification_status"] == "unverified"
    assert result["sources"] == [] and result["source_tier"] is None
    row = PandasStore(data_dir=str(tmp_path)).get_all_records().iloc[0]
    assert bool(row["verified"]) is False
    assert row["last_result_id"] == tid
    assert result["kb_id"] == row["id"]
    assert task["verified"] is False and task["kb_id"] == row["id"]
    assert PandasStore(data_dir=str(tmp_path)).find_similar_by_vector(vec, threshold=0.5) is None


@pytest.mark.parametrize(
    "sources,label_source,expected",
    [
        pytest.param([TIER1, TIER3], "ai", "verified", id="tier1_verified"),
        pytest.param([TIER3], "ai", "unverified", id="tier3_only_unverified"),
        pytest.param([], "rule", "rule", id="rule_label_rule"),
        pytest.param([TIER1], "rule", "rule", id="rule_wins_over_tier1"),
    ],
)
def test_result_verification_status_three_values(tmp_path, monkeypatch, sources, label_source, expected):
    if label_source == "ai":
        fake = _FakeAI(_ai(sources, risk_type="SAFE"))
        _patch_proc(monkeypatch, tmp_path, fake)
        _, result, task = _run_proc(tmp_path, f"狀態測試 {expected}")
    else:
        # rule 列來自 news_fetcher 索引：以 hash 命中讀回
        store = PandasStore(data_dir=str(tmp_path))
        text = f"規則命中 {expected}"
        _save(store, text, sources, label_source="rule")
        fake = _FakeAI(_ai([], risk_type="SAFE"))
        _patch_proc(monkeypatch, tmp_path, fake)
        _, result, task = _run_proc(tmp_path, text)
        assert fake.calls == 0 and result["cache_layer"] == "hash"
        assert result["label_source"] == "rule"

    assert result["verification_status"] == expected
    assert result["verified"] is (expected != "unverified")
    assert task["verified"] is result["verified"]
    if expected == "unverified":
        assert result["frame_type"] != "green"
    for key in ("result_id", "ai_unavailable", "similar_news", "category_label",
                "label_source", "analyzed_at", "verified", "verification_status",
                "source_tier", "related_discussions", "kb_id"):
        assert key in result
    assert "timeline" not in result
    assert result["analyzed_at"].endswith("+08:00")


def test_result_sources_have_no_tier3(tmp_path, monkeypatch):
    fake = _FakeAI(_ai([TIER1, TIER2, TIER3], risk_type="MISINFO"))
    _patch_proc(monkeypatch, tmp_path, fake)
    tid, result, task = _run_proc(tmp_path, "網傳喝鹽水可以治新冠")

    assert [s["tier"] for s in result["sources"]] == [1, 2]
    assert [s["tier_label"] for s in result["sources"]] == ["查核機構", "媒體查核報導"]
    assert result["source_tier"] == 1
    assert [s["url"] for s in result["related_discussions"]] == [TIER3["url"]]
    assert result["related_discussions"][0]["tier"] == 3
    assert result["result_id"] == tid
    assert result["frame_type"] == "red" and result["category_label"]
    # tasks.parquet 同步保存 v2 欄位
    assert task["source_tier"] == 1 and task["label_source"] == "ai"
    assert task["ai_unavailable"] is False
    assert TIER3["url"] in task["related_discussions"]
    stored = json.loads(task["result_data"])
    assert all(s["tier"] in (1, 2) for s in stored["sources"])


def test_cache_hit_sources_have_tier(tmp_path, monkeypatch):
    store = PandasStore(data_dir=str(tmp_path))
    vec_a, vec_b = _vec(11), _vec(12)
    text_a, text_b = "快取列 A 不帶 tier", "快取列 B 帶 Cofacts tier"
    _save(store, text_a, [{"title": "MyGoPen", "url": "https://www.mygopen.com/a"}, TIER3], vector=vec_a)
    _save(store, text_b, [{"title": "Cofacts 回覆", "url": "https://cofacts.tw/article/xyz", "tier": 1}],
          vector=vec_b)

    # 模擬舊列（B-13 之前寫入）：把列 A 的 tier / tier_label 剝掉再存回
    df = store.get_all_records()

    def _strip(sources):
        return [{"title": s["title"], "url": s["url"]} for s in list(sources)]

    idx_a = df.index[df["raw_content"] == text_a][0]
    stripped = _strip(df.at[idx_a, "sources"])
    df.at[idx_a, "sources"] = stripped
    ai_a = dict(df.at[idx_a, "ai_analysis"])
    ai_a["sources"] = stripped
    df.at[idx_a, "ai_analysis"] = ai_a
    store._save_knowledge_base(df)
    raw_a = store.get_all_records()
    assert all(s.get("tier") is None for s in raw_a[raw_a["raw_content"] == text_a].iloc[0]["sources"])

    fake = _FakeAI(_ai([], risk_type="SAFE"))

    def _check(result, layer, cofacts):
        assert result["cached"] is True and result["cache_layer"] == layer
        assert result["sources"], "cache hit must keep Tier 1/2 sources"
        for s in result["sources"]:
            assert s["tier"] in (1, 2) and s["tier_label"] in ("查核機構", "媒體查核報導")
        assert all(s["tier"] == 3 for s in result["related_discussions"])
        if cofacts:
            assert [s["tier"] for s in result["sources"]] == [1]
            assert "cofacts.tw" in result["sources"][0]["url"]
        assert result["verification_status"] == "verified"

    # hash 路徑（兩列）
    _patch_proc(monkeypatch, tmp_path, fake)
    _, res_a, _ = _run_proc(tmp_path, text_a)
    _check(res_a, "hash", cofacts=False)
    assert [s["url"] for s in res_a["related_discussions"]] == [TIER3["url"]]
    _, res_b, _ = _run_proc(tmp_path, text_b)
    _check(res_b, "hash", cofacts=True)

    # vector 路徑（兩列）：換句話說的輸入，查詢向量等於列向量
    _patch_proc(monkeypatch, tmp_path, fake, vector=vec_a)
    _, res_va, _ = _run_proc(tmp_path, "換句話說的 A")
    _check(res_va, "vector", cofacts=False)
    _patch_proc(monkeypatch, tmp_path, fake, vector=vec_b)
    _, res_vb, _ = _run_proc(tmp_path, "換句話說的 B")
    _check(res_vb, "vector", cofacts=True)
    assert fake.calls == 0


def test_cache_hit_ai_row_without_tier12_is_unverified(tmp_path, monkeypatch):
    # KB 列 verified=True 但補完分級後沒有 Tier 1/2 → 本次回應 unverified（不回傳「已證實卻無來源」）
    store = PandasStore(data_dir=str(tmp_path))
    text = "只有部落格來源卻被標已證實"
    _save(store, text, [TIER3], verified=True)
    fake = _FakeAI(_ai([], risk_type="SAFE"))
    _patch_proc(monkeypatch, tmp_path, fake)
    _, result, _ = _run_proc(tmp_path, text)
    assert result["cache_layer"] == "hash"
    assert result["sources"] == []
    assert result["verification_status"] == "unverified" and result["verified"] is False
    assert result["frame_type"] != "green"


def test_fallback_not_written_and_ai_unavailable_true(tmp_path, monkeypatch):
    fake = _FakeAI(_default_fallback_result("cgu HTTP 402: insufficient_credits"))
    _patch_proc(monkeypatch, tmp_path, fake)
    _, result, task = _run_proc(tmp_path, "AI 掛掉時送出的文字")

    assert result["ai_unavailable"] is True
    assert result["frame_type"] == "grey"
    assert result["verification_status"] == "unverified" and result["verified"] is False
    assert result["kb_id"] is None and result["sources"] == []
    assert result["summary"].startswith("AI 分析暫時無法使用")
    assert PandasStore(data_dir=str(tmp_path)).get_all_records().empty
    assert task["status"] == "completed" and task["ai_unavailable"] is True
    assert task["kb_id"] is None


def test_verification_log_line(tmp_path, monkeypatch, caplog):
    fake = _FakeAI(_ai([TIER1], risk_type="SCAM"))
    _patch_proc(monkeypatch, tmp_path, fake)
    with caplog.at_level("INFO", logger=proc.logger.name):
        tid, _, _ = _run_proc(tmp_path, "結構化 log 測試")
    lines = [r.getMessage() for r in caplog.records if r.getMessage().startswith("verification ")]
    assert len(lines) == 1
    payload = json.loads(lines[0][len("verification "):])
    assert set(payload) == {"result_id", "origin", "cache_layer", "provider", "elapsed_ms", "tier_ms", "usd"}
    assert payload["result_id"] == tid and payload["origin"] == "web"
    assert payload["cache_layer"] is None and isinstance(payload["elapsed_ms"], int)
    assert isinstance(payload["tier_ms"], int)


def test_category_label_mapping():
    from app.utils.labels import category_label
    assert category_label("Phishing") == "釣魚詐騙"
    assert category_label("health_rumor") == "健康謠言"
    assert category_label("SomethingNew") == "其他"
    assert category_label(None) == ""


def test_related_discussions_stored_as_json(tmp_path):
    store = PandasStore(data_dir=str(tmp_path))
    rec, _ = _save(store, "相關討論", [], related_discussions=[{"title": "x", "url": "https://line.me/x"}])
    assert isinstance(rec["related_discussions"], str)
    assert "line.me" in store.get_all_records().iloc[0]["related_discussions"]


def test_cache_hit_verified_false_row_with_tier1_is_verified(tmp_path, monkeypatch):
    # 種子資料常見：label_source=ai、存的 verified=False，但 sources 正規化後仍有 Tier 1。
    # 狀態只依 label_source 與 Tier 1/2 清單推導 → verified，不得出現「列出 Tier 1 卻顯示尚無查核機構證實」。
    from app.utils.verdict import LABEL_NO_VERIFIED_SOURCE

    store = PandasStore(data_dir=str(tmp_path))
    text = "舊種子列 verified False 但有 165 來源"
    h = CacheService.generate_hash(text)
    store.save_record(
        data_type="TEXT", raw_content=text, content_hash=h, content_vector=None,
        ai_result=_ai([TIER1], risk_type="SAFE"), verified=False,
    )
    assert bool(store.find_by_hash(h)["verified"]) is False

    fake = _FakeAI(_ai([], risk_type="SAFE"))
    _patch_proc(monkeypatch, tmp_path, fake)
    _, result, task = _run_proc(tmp_path, text)

    assert fake.calls == 0 and result["cache_layer"] == "hash"
    assert [s["tier"] for s in result["sources"]] == [1]
    assert result["verification_status"] == "verified" and result["verified"] is True
    assert result["frame_label"] != LABEL_NO_VERIFIED_SOURCE
    assert result["frame_type"] == "green"
    assert task["verified"] is True


def test_validator_exception_drops_sources_unverified(tmp_path, monkeypatch):
    # FN-13 iv：url_validator 例外 → 來源視為未驗證並丟棄，不得算證實、KB 列不得標 verified
    def _raise(sources):
        raise RuntimeError("validator down")

    fake = _FakeAI(_ai([TIER1, TIER2], risk_type="SCAM"))
    vec = _vec(21)
    _patch_proc(monkeypatch, tmp_path, fake, vector=vec, alive=_raise)
    _, result, task = _run_proc(tmp_path, "驗證器壞掉時的可疑訊息")

    assert result["verification_status"] == "unverified" and result["verified"] is False
    assert result["sources"] == [] and result["source_tier"] is None
    assert result["related_discussions"] == []
    row = PandasStore(data_dir=str(tmp_path)).get_all_records().iloc[0]
    assert bool(row["verified"]) is False
    assert list(row["sources"]) == []
    assert task["verified"] is False
    assert PandasStore(data_dir=str(tmp_path)).find_similar_by_vector(vec, threshold=0.5) is None


def test_verification_log_usd_and_actual_provider(tmp_path, monkeypatch, caplog):
    # AI 回應附 usage／provider／model → log 的 usd 非 null、provider 為實際回應者；meta 不寫進 KB／回應
    ai = _ai([TIER1], risk_type="SCAM")
    ai.update({
        "provider": "openai", "model": "gpt-5.4-mini",
        "usage": {"input_tokens": 2000, "output_tokens": 500},
    })
    fake = _FakeAI(ai)
    fake.providers = ["cgu", "openai", "claude"]
    _patch_proc(monkeypatch, tmp_path, fake)
    with caplog.at_level("INFO", logger=proc.logger.name):
        _, result, _ = _run_proc(tmp_path, "usd 估算測試")

    lines = [r.getMessage() for r in caplog.records if r.getMessage().startswith("verification ")]
    payload = json.loads(lines[-1][len("verification "):])
    assert payload["provider"] == "openai"
    price_in, price_out = proc.MODEL_PRICING_PER_1M["gpt-5.4-mini"]
    assert payload["usd"] is not None
    assert payload["usd"] == pytest.approx((2000 * price_in + 500 * price_out) / 1_000_000)
    for key in ("usage", "provider", "model"):
        assert key not in result
    ai_analysis = PandasStore(data_dir=str(tmp_path)).get_all_records().iloc[0]["ai_analysis"]
    assert not any(ai_analysis.get(k) for k in ("usage", "provider", "model"))


# ── 批次寫入（scripts/ingest_factchecks.py）：與逐筆 save_record 同一套內容與寫入門檻 ──
_COMPARED = ["data_type", "source_url", "raw_content", "data_hash", "is_risk", "risk_type", "category",
             "confidence_score", "summary", "explanation", "label_source", "origin", "source_tier", "verified",
             "related_discussions"]


def _items():
    rule_src = [{"title": "MyGoPen", "url": "https://www.mygopen.com/2026/09/a.html", "tier": 1}]
    return [
        dict(data_type="TEXT", raw_content="喝鹽水可以治新冠", content_hash=CacheService.generate_hash("喝鹽水可以治新冠"),
             content_vector=_vec(1), ai_result=_ai(rule_src, "MISINFO"), source_url=rule_src[0]["url"],
             label_source="rule", origin="factcheck_batch"),
        dict(data_type="TEXT", raw_content="網路上看到的說法", content_hash=CacheService.generate_hash("網路上看到的說法"),
             content_vector=None, ai_result=_ai([{"title": "部落格", "url": "https://blog.example.com/p"}]),
             related_discussions=[{"url": "https://www.ptt.cc/x", "tier": 3}]),
    ]


def test_save_records_matches_save_record(tmp_path):
    one = PandasStore(data_dir=str(tmp_path / "one"))
    bulk = PandasStore(data_dir=str(tmp_path / "bulk"))
    for item in _items():
        one.save_record(**item)
    assert bulk.save_records(_items()) == 2
    a, b = one.get_all_records(), bulk.get_all_records()
    assert len(a) == len(b) == 2
    for col in _COMPARED:
        assert list(a[col].fillna("<na>")) == list(b[col].fillna("<na>")), col
    assert list(b["verified"]) == [True, False]               # rule 列寫入即證實；Tier 3 來源不算
    assert b.iloc[0]["ai_analysis"]["sources"][0]["tier"] == 1
    assert isinstance(b.iloc[1]["related_discussions"], str)
    assert bulk.save_records([]) == 0 and len(bulk.get_all_records()) == 2


def test_save_records_uses_given_created_at(tmp_path):
    from datetime import datetime

    store = PandasStore(data_dir=str(tmp_path))
    at = datetime(2026, 9, 23, 13, 0, 0)
    store.save_records([{**_items()[0], "now": at}])
    row = store.get_all_records().iloc[0]
    assert row["created_at"] == at and row["last_accessed_at"] == at
