"""查核結果回補（pandas_task_processor._newer_factcheck）。

URL／hash 層不過濾 verified：一字不差的重複查詢會一直拿到當初「尚無查核機構證實」的結果。
命中的是未證實列時，改以它的內容到向量層只找確定性標記（rule／gold／admin）；對得上就回那一筆。
全 mock、離線、零 AI。
"""
import asyncio

import numpy as np
import pytest

import app.workers.pandas_task_processor as proc
from app.services.cache_service import CacheService
from app.services.pandas_store import DETERMINISTIC_LABEL_SOURCES, PandasStore
from app.services.task_store import TaskStore

USER_TEXT = "網傳每天喝檸檬水可以殺死癌細胞，醫生都不告訴你"
CLAIM = "喝檸檬水可以殺死癌細胞"
MYGOPEN = {"title": "【錯誤】網傳喝檸檬水能殺死癌細胞？", "url": "https://www.mygopen.com/2026/09/lemon.html"}


def _vec(seed):
    v = np.random.default_rng(seed).normal(size=1536)
    return list(v / np.linalg.norm(v))


def _mix(base, other, cosine):
    """與 base 的 cosine similarity 為指定值的單位向量。"""
    a = np.asarray(base)
    b = np.asarray(other)
    b = b - a * float(a @ b)
    b = b / np.linalg.norm(b)
    return list(cosine * a + np.sqrt(1 - cosine ** 2) * b)


def _ai(risk_type, sources=()):
    return {
        "is_risk": risk_type != "SAFE", "risk_type": risk_type, "category": "Test",
        "confidence_score": 0.8, "summary": f"{risk_type} 摘要", "explanation": "說明",
        "sources": list(sources),
    }


class NoAI:
    def analyze_content(self, *args, **kwargs):
        raise AssertionError("快取命中不得呼叫判讀模型")


class NoCrawler:
    async def process_input(self, *args, **kwargs):
        raise AssertionError("文字輸入不得爬取")


class CountingVector:
    calls = 0
    result = []

    def vectorize_content(self, text):
        CountingVector.calls += 1
        return CountingVector.result


@pytest.fixture
def env(tmp_path, monkeypatch):
    CountingVector.calls = 0
    CountingVector.result = []
    monkeypatch.setattr(proc, "TaskStore", lambda: TaskStore(data_dir=str(tmp_path)))
    monkeypatch.setattr(proc, "PandasStore", lambda: PandasStore(data_dir=str(tmp_path)))
    monkeypatch.setattr(proc, "AIService", NoAI)
    monkeypatch.setattr(proc, "CrawlerService", NoCrawler)
    monkeypatch.setattr(proc, "VectorService", CountingVector)
    return tmp_path


def _save(env, text, ai, vector, label_source="ai"):
    return PandasStore(data_dir=str(env)).save_record(
        data_type="TEXT", raw_content=text, content_hash=CacheService.generate_hash(text),
        content_vector=vector, ai_result=ai, label_source=label_source,
    )


def _run(env, text=USER_TEXT):
    tasks = TaskStore(data_dir=str(env))
    tid = tasks.create_task("analyze_text", text)
    result = asyncio.run(proc.process_analysis_task_async(tid, text, "text"))
    return result, tasks.get_task(tid)


def test_unverified_hash_hit_is_replaced_by_a_matching_factcheck(env):
    base = _vec(1)
    old = _save(env, USER_TEXT, _ai("SAFE"), base)
    assert old["verified"] is False
    fact = _save(env, CLAIM, _ai("MISINFO", [MYGOPEN]), _mix(base, _vec(2), 0.85), label_source="rule")
    assert fact["verified"] is True

    result, task = _run(env)

    assert result["risk_type"] == "MISINFO"
    assert result["cached"] is True and result["cache_layer"] == "vector"
    assert [s["url"] for s in result["sources"]] == [MYGOPEN["url"]]
    assert task["kb_id"] == fact["id"]
    assert CountingVector.calls == 0          # 本機列帶著向量，不必再算


def test_ai_verified_rows_do_not_replace_an_unverified_hash_hit(env):
    base = _vec(3)
    old = _save(env, USER_TEXT, _ai("SAFE"), base)
    _save(env, "長得很像的另一則", _ai("SCAM", [MYGOPEN]), _mix(base, _vec(4), 0.95))

    result, task = _run(env)

    assert result["cache_layer"] == "hash" and result["risk_type"] == "SAFE"
    assert task["kb_id"] == old["id"]


def test_factcheck_below_threshold_keeps_the_old_result(env):
    base = _vec(5)
    old = _save(env, USER_TEXT, _ai("SAFE"), base)
    _save(env, CLAIM, _ai("MISINFO", [MYGOPEN]), _mix(base, _vec(6), 0.60), label_source="rule")

    result, task = _run(env)

    assert result["cache_layer"] == "hash" and task["kb_id"] == old["id"]


def test_verified_hash_hit_is_served_without_a_vector_lookup(env, monkeypatch):
    base = _vec(7)
    row = _save(env, USER_TEXT, _ai("MISINFO", [MYGOPEN]), base)
    assert row["verified"] is True

    def no_lookup(self, *args, **kwargs):
        raise AssertionError("已證實的快取列不必再查向量層")

    monkeypatch.setattr(PandasStore, "find_similar_by_vector", no_lookup)
    result, _ = _run(env)

    assert result["cache_layer"] == "hash" and result["risk_type"] == "MISINFO"
    assert CountingVector.calls == 0


def test_row_without_a_stored_vector_embeds_its_text(env):
    base = _vec(8)
    _save(env, USER_TEXT, _ai("SAFE"), None)
    fact = _save(env, CLAIM, _ai("MISINFO", [MYGOPEN]), _mix(base, _vec(9), 0.90), label_source="rule")
    CountingVector.result = base

    result, task = _run(env)

    assert CountingVector.calls == 1
    assert result["cache_layer"] == "vector" and task["kb_id"] == fact["id"]


def test_embedding_unavailable_keeps_the_old_result(env):
    old = _save(env, USER_TEXT, _ai("SAFE"), None)
    CountingVector.result = []

    result, task = _run(env)

    assert result["cache_layer"] == "hash" and task["kb_id"] == old["id"]


def test_lookup_error_serves_the_cached_row_instead_of_failing(env, monkeypatch):
    old = _save(env, USER_TEXT, _ai("SAFE"), _vec(12))

    def broken(self, *args, **kwargs):
        raise RuntimeError("database hiccup")

    monkeypatch.setattr(PandasStore, "find_similar_by_vector", broken)
    result, task = _run(env)

    assert result["cache_layer"] == "hash" and task["status"] == "completed"
    assert task["kb_id"] == old["id"]


def test_store_label_filter_only_matches_deterministic_rows(tmp_path):
    store = PandasStore(data_dir=str(tmp_path))
    base = _vec(10)
    ai_row = store.save_record(
        data_type="TEXT", raw_content="AI 判定", content_hash="h1", content_vector=base,
        ai_result=_ai("SCAM", [MYGOPEN]),
    )
    rule_row = store.save_record(
        data_type="TEXT", raw_content="查核主張", content_hash="h2",
        content_vector=_mix(base, _vec(11), 0.90), ai_result=_ai("MISINFO", [MYGOPEN]), label_source="rule",
    )

    assert store.find_similar_by_vector(base)["id"] == ai_row["id"]
    assert store.find_similar_by_vector(base, label_sources=DETERMINISTIC_LABEL_SOURCES)["id"] == rule_row["id"]
    assert store.find_similar_by_vector(base, label_sources=("gold",)) is None
