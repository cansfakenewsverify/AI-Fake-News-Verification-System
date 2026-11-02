"""算不出向量時存下的結果（2026-10-28 Render 的 EMBED_API_KEY 失效約 11 小時）。

- generate_embedding 把每次呼叫的結果記下來，/health 讀它（狀態碼，不含網址與金鑰）；
- 快取命中的列，存下的證據沒有最近相似度也沒有話術差距時，重新比對知識庫：拿到現在應有的信心與相似查證。
全 mock、離線、零 AI。
"""
import asyncio

import numpy as np
import pytest
import requests

import app.services.ai_service as ai_service
import app.workers.pandas_task_processor as proc
from app.config import settings
from app.services.cache_service import CacheService
from app.services.pandas_store import PandasStore
from app.services.task_store import TaskStore

USER_TEXT = "台灣軍人若效忠中共取消退休金，這守護台灣的法案本週竟被國民黨擋下了"
FACTCHECK = "當你以為守護台灣是基本常識，結果國民黨卻再次讓人失望。軍人若效忠中共將取消退休金的法案竟然被國民黨聯手擋下"
TFC = {"title": "網傳國民黨本週擋下軍人效忠中共取消退休金法案？舊聞", "tier": 1,
       "url": "https://tfc-taiwan.org.tw/fact-check-reports/outdated-claim-kmt-blocked-military-pension-bill/"}
NO_VECTOR_EVIDENCE = {"level": "低", "basis": "ai_only", "note": "只有 AI 判斷，沒有相近的查核案例",
                      "nearest_similarity": None, "nearest_degrees": None, "pattern_margin": None}


def _vec(seed):
    v = np.random.default_rng(seed).normal(size=1536)
    return list(v / np.linalg.norm(v))


def _mix(base, other, cosine):
    a, b = np.asarray(base), np.asarray(other)
    b = b - a * float(a @ b)
    b = b / np.linalg.norm(b)
    return list(cosine * a + np.sqrt(1 - cosine ** 2) * b)


def _ai(risk_type, sources=(), evidence=None):
    ai = {"is_risk": risk_type != "SAFE", "risk_type": risk_type, "category": "Test", "confidence_score": 0.8,
          "summary": f"{risk_type} 摘要", "explanation": "說明", "sources": list(sources)}
    if evidence is not None:
        ai["evidence"] = dict(evidence)
    return ai


class NoAI:
    def analyze_content(self, *args, **kwargs):
        raise AssertionError("快取命中不得呼叫判讀模型")


class NoCrawler:
    async def process_input(self, *args, **kwargs):
        raise AssertionError("文字輸入不得爬取")


class FakeVector:
    seen = []
    result = []

    def vectorize_content(self, text):
        FakeVector.seen.append(text)
        return FakeVector.result


@pytest.fixture
def env(tmp_path, monkeypatch):
    FakeVector.seen, FakeVector.result = [], []
    monkeypatch.setattr(proc, "TaskStore", lambda: TaskStore(data_dir=str(tmp_path)))
    monkeypatch.setattr(proc, "PandasStore", lambda: PandasStore(data_dir=str(tmp_path)))
    monkeypatch.setattr(proc, "AIService", NoAI)
    monkeypatch.setattr(proc, "CrawlerService", NoCrawler)
    monkeypatch.setattr(proc, "VectorService", FakeVector)
    return tmp_path


def _save(env, text, ai, vector, label_source="ai"):
    return PandasStore(data_dir=str(env)).save_record(
        data_type="TEXT", raw_content=text, content_hash=CacheService.generate_hash(text),
        content_vector=vector, ai_result=ai, label_source=label_source,
    )


def _run(env, text=USER_TEXT):
    tasks = TaskStore(data_dir=str(env))
    tid = tasks.create_task("analyze_text", text)
    return asyncio.run(proc.process_analysis_task_async(tid, text, "text"))


# ── 快取命中時重新比對 ──────────────────────────────────────

def test_hash_hit_saved_without_a_vector_gets_fresh_evidence(env):
    base = _vec(1)
    _save(env, USER_TEXT, _ai("MISINFO", evidence=NO_VECTOR_EVIDENCE), None)
    _save(env, FACTCHECK, _ai("MISINFO", [TFC]), _mix(base, _vec(2), 0.70), label_source="rule")
    FakeVector.result = base                     # 現在 embedding 正常了

    result = _run(env)

    # 0.70 不到語意快取的 0.75（不改回查核那一筆），但夠「相近案例」：信心「中」並列出相似查證
    assert result["cache_layer"] == "hash" and result["risk_type"] == "MISINFO"
    assert result["confidence_basis"] == "similar_case" and result["confidence_level"] == "中"
    assert result["evidence"]["nearest_similarity"] == pytest.approx(0.70, abs=1e-4)
    assert [s["url"] for s in result["similar_news"]] == [TFC["url"]]
    assert FakeVector.seen == [USER_TEXT]        # 回補查核與重新比對共用同一次 embedding


def test_still_no_vector_keeps_the_stored_evidence(env):
    _save(env, USER_TEXT, _ai("MISINFO", evidence=NO_VECTOR_EVIDENCE), None)
    _save(env, FACTCHECK, _ai("MISINFO", [TFC]), _vec(3), label_source="rule")
    FakeVector.result = []                       # 金鑰還是壞的

    result = _run(env)

    assert result["confidence_basis"] == "ai_only" and result["similar_news"] == []


def test_evidence_saved_with_a_vector_is_not_recomputed(env):
    stored = {**NO_VECTOR_EVIDENCE, "nearest_similarity": 0.52, "nearest_degrees": 58.7, "pattern_margin": -0.03}
    _save(env, USER_TEXT, _ai("MISINFO", [TFC], evidence=stored), _vec(4))   # 有查核來源 → 已證實列
    FakeVector.result = _vec(5)

    result = _run(env)

    assert result["cache_layer"] == "hash"
    assert result["evidence"]["nearest_similarity"] == 0.52 and result["similar_news"] == []
    assert FakeVector.seen == []


# ── generate_embedding 記下呼叫結果 ─────────────────────────

class _Resp:
    def __init__(self, status, body=None):
        self.status_code, self._body = status, body or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} Client Error: for url: https://example.invalid/v1/embeddings",
                                     response=self)

    def json(self):
        return self._body


@pytest.fixture
def embed_settings(monkeypatch):
    monkeypatch.setattr(settings, "EMBED_RELAY_URL", "https://example.invalid/v1")
    monkeypatch.setattr(settings, "EMBED_API_KEY", "dummy-key")
    monkeypatch.setattr(ai_service, "_EMBED_STATUS", {"ok": None, "checked_at": None, "error": None})


def test_embedding_failure_is_recorded_without_the_url(monkeypatch, embed_settings):
    monkeypatch.setattr(ai_service.requests, "post", lambda *a, **k: _Resp(401))
    assert ai_service.AIService().generate_embedding("測試") == []
    status = ai_service.embedding_status()
    assert status["ok"] is False and status["error"] == "HTTP 401" and status["checked_at"]

    monkeypatch.setattr(ai_service.requests, "post", lambda *a, **k: _Resp(200, {"data": [{"embedding": [0.1, 0.2]}]}))
    assert ai_service.AIService().generate_embedding("測試") == [0.1, 0.2]
    assert ai_service.embedding_status()["ok"] is True
    assert ai_service.embedding_status()["error"] is None


def test_embedding_timeout_is_recorded_by_class_name(monkeypatch, embed_settings):
    def timeout(*args, **kwargs):
        raise requests.Timeout("read timed out")

    monkeypatch.setattr(ai_service.requests, "post", timeout)
    ai_service.AIService().generate_embedding("測試")
    assert ai_service.embedding_status()["error"] == "Timeout"
