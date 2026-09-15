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


def test_related_discussions_stored_as_json(tmp_path):
    store = PandasStore(data_dir=str(tmp_path))
    rec, _ = _save(store, "相關討論", [], related_discussions=[{"title": "x", "url": "https://line.me/x"}])
    assert isinstance(rec["related_discussions"], str)
    assert "line.me" in store.get_all_records().iloc[0]["related_discussions"]
