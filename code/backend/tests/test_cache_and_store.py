"""快取層單元測試：hash、Parquet 三層快取（URL / Hash / 向量）。全部離線、零 AI 呼叫。"""
import numpy as np

from app.services.cache_service import CacheService
from app.services.pandas_store import PandasStore
from app.services.task_store import TaskStore


AI_RESULT = {
    "is_risk": True, "risk_type": "SCAM", "category": "Investment",
    "confidence_score": 0.95, "summary": "測試摘要", "explanation": "測試解釋",
    "sources": [{"title": "165", "url": "https://165.npa.gov.tw/"}],
}


def test_generate_hash_deterministic():
    a = CacheService.generate_hash("同一段文字")
    b = CacheService.generate_hash("同一段文字")
    c = CacheService.generate_hash("不同文字")
    assert a == b
    assert a != c
    assert len(a) == 64  # SHA-256 hex


def _make_store(tmp_path, vector=None):
    store = PandasStore(data_dir=str(tmp_path))
    h = CacheService.generate_hash("投資穩賺不賠")
    store.save_record(
        data_type="TEXT", raw_content="投資穩賺不賠", content_hash=h,
        content_vector=vector, ai_result=AI_RESULT, source_url="https://example.com/a",
    )
    return store, h


def test_find_by_hash_hit_and_miss(tmp_path):
    store, h = _make_store(tmp_path)
    hit = store.find_by_hash(h)
    assert hit is not None
    assert hit["risk_type"] == "SCAM"
    assert store.find_by_hash("0" * 64) is None


def test_find_by_url_hit_updates_hit_count(tmp_path):
    store, _ = _make_store(tmp_path)
    hit = store.find_by_url("https://example.com/a")
    assert hit is not None
    again = store.find_by_url("https://example.com/a")
    assert again["hit_count"] >= hit["hit_count"]
    assert store.find_by_url("https://example.com/nope") is None


def test_vector_search_exact_hit(tmp_path):
    vec = list(np.random.default_rng(7).normal(size=1536).astype(float))
    store, _ = _make_store(tmp_path, vector=vec)
    hit = store.find_similar_by_vector(vec, threshold=0.88)
    assert hit is not None and hit["risk_type"] == "SCAM"


def test_vector_search_below_threshold_none(tmp_path):
    rng = np.random.default_rng(7)
    vec = list(rng.normal(size=1536).astype(float))
    store, _ = _make_store(tmp_path, vector=vec)
    other = list(rng.normal(size=1536).astype(float))  # 隨機向量 ~ 正交
    assert store.find_similar_by_vector(other, threshold=0.88) is None


def test_vector_search_guards(tmp_path):
    vec = list(np.random.default_rng(7).normal(size=1536).astype(float))
    store, _ = _make_store(tmp_path, vector=vec)
    assert store.find_similar_by_vector([], threshold=0.88) is None          # 空向量（層停用）
    assert store.find_similar_by_vector([0.0] * 1536, threshold=0.88) is None  # 零向量
    assert store.find_similar_by_vector([0.1, 0.2], threshold=0.88) is None    # 維度不符


def test_task_store_lifecycle(tmp_path):
    ts = TaskStore(data_dir=str(tmp_path))
    tid = ts.create_task("analyze_text", "測試輸入")
    task = ts.get_task(tid)
    assert task["status"] == "pending"
    ts.update_task(tid, status="completed", result_data="{}")
    assert ts.get_task(tid)["status"] == "completed"
    assert ts.get_task("no-such-id") is None
