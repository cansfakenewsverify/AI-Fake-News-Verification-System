"""證據信心（夾角，app/services/evidence.py）：規則表、知識庫中的相似查證、話術差距與處理器整合。

全部離線、零 AI：向量是固定的隨機向量，知識庫是 tmp_path 的 PandasStore。
規則與門檻的依據見 docs/rebuild/信心程度的產生方式.md。
"""
import asyncio

import numpy as np
import pytest

import app.workers.pandas_task_processor as proc
from app.services import evidence
from app.services.cache_service import CacheService
from app.services.pandas_store import PandasStore
from app.services.task_store import TaskStore


def _n(sim, risk="MISINFO", url="https://www.mygopen.com/a", text="網傳喝鹽水可以治新冠"):
    return {"id": f"kb-{sim}-{risk}", "raw_content": text, "risk_type": risk, "label_source": "rule",
            "source_url": url, "summary": "", "similarity": sim,
            "sources": [{"title": "MyGoPen 查核", "url": url, "tier": 1}]}


# ── 規則表（evidence.py 開頭；先符合者為準）────────────────────────────
@pytest.mark.parametrize("risk, kwargs, expected", [
    ("SCAM", dict(ai_unavailable=True), ("低", "ai_unavailable")),
    ("MISINFO", dict(label_source="rule"), ("高", "factchecked")),
    ("SAFE", dict(label_source="gold"), ("高", "factchecked")),
    ("MISINFO", dict(neighbours=[_n(0.70)]), ("中", "similar_case")),
    ("SCAM", dict(neighbours=[_n(0.60)], margin=0.12), ("中", "pattern")),
    ("SCAM", dict(neighbours=[_n(0.60)], margin=0.05, verification_status="verified"), ("中", "cited_source")),
    ("SCAM", dict(neighbours=[_n(0.64)], margin=0.09), ("低", "ai_only")),
    ("SAFE", dict(neighbours=[_n(0.66)], verification_status="verified"), ("低", "conflict")),
    ("SAFE", dict(margin=0.10), ("低", "conflict")),
    ("SAFE", dict(verification_status="verified"), ("中", "safe_source")),
    ("SAFE", dict(), ("低", "ai_only")),
    ("UNVERIFIABLE", dict(), ("低", "unverifiable")),
])
def test_assess_follows_the_rule_table(risk, kwargs, expected):
    got = evidence.assess(risk, **kwargs)
    assert (got["level"], got["basis"]) == expected
    assert got["note"] == evidence.NOTE_OF_BASIS[got["basis"]]


def test_only_risky_neighbours_count_as_supporting_cases():
    got = evidence.assess("MISINFO", neighbours=[_n(0.9, risk="SAFE"), _n(0.62)])
    assert got["basis"] == "ai_only"                                  # 最近的是「安全」列，不算佐證
    assert got["nearest_similarity"] == 0.62
    assert got["nearest_degrees"] == pytest.approx(51.7, abs=0.1)


def test_thresholds_are_inclusive():
    assert evidence.assess("MISINFO", neighbours=[_n(0.65)])["basis"] == "similar_case"
    assert evidence.assess("SCAM", margin=0.10)["basis"] == "pattern"
    assert evidence.assess("SCAM", margin=0.0999)["basis"] == "ai_only"


def test_degrees_is_the_arccos_angle():
    assert evidence.degrees(0.75) == pytest.approx(41.4, abs=0.1)
    assert evidence.degrees(1.0) == 0.0 and evidence.degrees(None) is None


# ── 知識庫中的相似查證（spec FR-02 similar_news）─────────────────────────
def test_similar_news_lists_up_to_three_close_cases_with_the_fact_check_link():
    neighbours = [_n(0.91, text="網傳" + "很長的謠言內容" * 20), _n(0.72, risk="SCAM", url="https://tfc-taiwan.org.tw/x"),
                  _n(0.61), _n(0.60), _n(0.59)]
    items = evidence.similar_news(neighbours)
    assert [i["similarity"] for i in items] == [0.91, 0.72, 0.61]     # 最多 3 筆、相似度 ≥ 0.60
    first = items[0]
    assert first["url"] == "https://www.mygopen.com/a" and first["source"] == "MyGoPen"
    assert items[1]["source"] == "台灣事實查核中心"
    assert first["title"].endswith("…") and len(first["title"]) == 61
    assert [i["frame_type"] for i in items] == ["red", "red", "red"]  # 燈號由 frame_of 算
    assert first["degrees"] == pytest.approx(24.5, abs=0.1)
    assert evidence.similar_news(None) == [] and evidence.similar_news([_n(0.5)]) == []


def test_source_name_uses_the_fact_checker_name():
    assert evidence.source_name("https://cofacts.tw/article/abc") == "Cofacts"
    assert evidence.source_name("https://www.mohw.gov.tw/cp-1.html") == "政府機關"
    assert evidence.source_name("https://www.cna.com.tw/news/1") == "cna.com.tw"
    assert evidence.source_name("https://gov.tw.evil.com/x") == "gov.tw.evil.com"   # 尾綴比對，不是子字串
    assert evidence.source_name(None) == "知識庫"


def test_similar_news_without_a_tier_1_or_2_source_has_no_link():
    n = _n(0.8)
    n["sources"] = [{"title": "PTT", "url": "https://www.ptt.cc/x", "tier": 3}]
    item = evidence.similar_news([n])[0]
    assert item["url"] is None and item["source"] == "知識庫"


# ── 話術差距（話術原型與正常訊息原型）──────────────────────────────────
def test_pattern_margin_reads_the_prototype_file(tmp_path, monkeypatch):
    identity = np.eye(4, 1536, dtype=np.float32)
    path = tmp_path / "protos.npz"
    np.savez(path, risk=identity[:2], safe=identity[2:])     # 話術原型 e0、e1；正常訊息原型 e2、e3
    monkeypatch.setattr(evidence, "PROTOTYPES_PATH", path)
    evidence._prototypes.cache_clear()
    try:
        q = np.zeros(1536, dtype=np.float32)
        q[0], q[2] = 0.8, 0.6
        assert evidence.pattern_margin(q) == pytest.approx(0.2, abs=1e-4)
        assert evidence.pattern_margin(np.zeros(1536)) is None
        assert evidence.pattern_margin([1.0, 2.0]) is None
        assert evidence.pattern_margin(None) is None
        monkeypatch.setattr(evidence, "PROTOTYPES_PATH", tmp_path / "missing.npz")
        evidence._prototypes.cache_clear()
        assert evidence.pattern_margin(q) is None                   # 缺檔不影響判讀，只少一個證據
    finally:
        evidence._prototypes.cache_clear()


def test_shipped_prototypes_have_the_expected_shape():
    evidence._prototypes.cache_clear()
    protos = evidence._prototypes()
    assert protos is not None
    risk, safe = protos
    assert risk.shape == (40, 1536) and safe.shape == (12, 1536)


# ── 處理器整合 ──────────────────────────────────────────────────────
RUMOR = "網傳喝鹽水可以預防新冠肺炎，醫師證實有效"
USER_TEXT = "有人說每天喝鹽水就不會得新冠，是真的嗎"
FACT_CHECK_URL = "https://www.mygopen.com/2026/09/salt.html"


def _vec(seed):
    return np.random.default_rng(seed).normal(size=1536)


def _mix(base, other, cosine):
    """與 base 的 cosine similarity 為指定值的向量。"""
    a = base / np.linalg.norm(base)
    b = other - a * float(a @ other)
    b = b / np.linalg.norm(b)
    return list(cosine * a + np.sqrt(1 - cosine ** 2) * b)


BASE, OTHER = _vec(1), _vec(2)


class _CloseVector:
    """使用者原文與知識庫那一則謠言相似 0.70：不到語意快取門檻 0.75，但可當「相近的已查核案例」。"""

    def vectorize_content(self, text):
        return _mix(BASE, OTHER, 0.70)


class _FakeAI:
    def __init__(self, risk="MISINFO"):
        self.risk = risk
        self.calls = 0

    def analyze_content(self, content, url=None, context=None, use_web_search=None):
        self.calls += 1
        return {"is_risk": self.risk != "SAFE", "risk_type": self.risk, "category": "Test",
                "confidence_score": 0.99, "summary": "摘要", "explanation": "解釋", "sources": []}


def _setup(monkeypatch, tmp_path, ai):
    store = PandasStore(data_dir=str(tmp_path))
    store.save_record(
        data_type="TEXT", raw_content=RUMOR, content_hash=CacheService.generate_hash(RUMOR),
        content_vector=list(BASE),
        ai_result={"is_risk": True, "risk_type": "MISINFO", "category": "已查核假訊息", "confidence_score": 0.95,
                   "summary": "此為已被查核的假訊息", "explanation": "MyGoPen 已查證",
                   "sources": [{"title": "MyGoPen 查核", "url": FACT_CHECK_URL, "tier": 1}]},
        source_url=FACT_CHECK_URL, label_source="rule", origin="factcheck_batch",
    )
    monkeypatch.setattr(proc, "TaskStore", lambda: TaskStore(data_dir=str(tmp_path)))
    monkeypatch.setattr(proc, "PandasStore", lambda: PandasStore(data_dir=str(tmp_path)))
    monkeypatch.setattr(proc, "AIService", lambda: ai)
    monkeypatch.setattr(proc, "VectorService", _CloseVector)
    monkeypatch.setattr(proc.evidence_mod, "pattern_margin", lambda vector: None)
    return store


def _run(tmp_path, text):
    tid = TaskStore(data_dir=str(tmp_path)).create_task("analyze_text", text)
    return asyncio.run(proc.process_analysis_task_async(tid, text, "text"))


def test_ai_result_carries_evidence_and_similar_cases(tmp_path, monkeypatch):
    ai = _FakeAI("MISINFO")
    store = _setup(monkeypatch, tmp_path, ai)
    result = _run(tmp_path, USER_TEXT)

    assert ai.calls == 1 and result["cached"] is False
    assert (result["confidence_level"], result["confidence_basis"]) == ("中", "similar_case")
    assert result["confidence_score"] == 0.99                           # AI 自評仍保留，但不決定信心
    assert result["evidence"]["nearest_similarity"] == pytest.approx(0.70, abs=1e-3)
    assert result["evidence"]["nearest_degrees"] == pytest.approx(45.6, abs=0.1)
    [case] = result["similar_news"]
    assert case["url"] == FACT_CHECK_URL and case["frame_type"] == "red" and case["title"] == RUMOR

    saved = store.get_all_records().iloc[-1]
    assert saved["raw_content"] == USER_TEXT
    assert saved["ai_analysis"]["evidence"]["basis"] == "similar_case"   # 存進知識庫供快取命中沿用


def test_cache_hit_reuses_the_stored_evidence(tmp_path, monkeypatch):
    ai = _FakeAI("MISINFO")
    _setup(monkeypatch, tmp_path, ai)
    first = _run(tmp_path, USER_TEXT)
    again = _run(tmp_path, USER_TEXT)

    assert ai.calls == 1 and again["cached"] is True and again["cache_layer"] == "hash"
    assert (again["confidence_level"], again["confidence_basis"]) == (first["confidence_level"], "similar_case")
    assert again["similar_news"] == []                                  # 快取命中不列相似查證（spec 8.3 S2）


def test_safe_verdict_close_to_a_fact_checked_rumour_is_flagged(tmp_path, monkeypatch):
    _setup(monkeypatch, tmp_path, _FakeAI("SAFE"))
    result = _run(tmp_path, USER_TEXT)
    assert (result["confidence_level"], result["confidence_basis"]) == ("低", "conflict")
    assert result["frame_type"] == "yellow"                              # 燈號規則不變：未證實的安全仍是黃燈


def test_hit_on_a_fact_checked_row_is_high_confidence(tmp_path, monkeypatch):
    ai = _FakeAI("SAFE")
    _setup(monkeypatch, tmp_path, ai)
    result = _run(tmp_path, RUMOR)                                      # 與查核機構那一則一字不差
    assert ai.calls == 0 and result["cache_layer"] == "hash"
    assert (result["confidence_level"], result["confidence_basis"]) == ("高", "factchecked")


def test_evidence_lookup_failure_falls_back_to_sources_only(tmp_path, monkeypatch):
    _setup(monkeypatch, tmp_path, _FakeAI("SCAM"))

    def _boom(self, *args, **kwargs):
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(PandasStore, "nearest_verified", _boom)
    result = _run(tmp_path, USER_TEXT)                                  # 查詢失敗不讓判讀失敗
    assert (result["confidence_level"], result["confidence_basis"]) == ("低", "ai_only")
    assert result["similar_news"] == []
