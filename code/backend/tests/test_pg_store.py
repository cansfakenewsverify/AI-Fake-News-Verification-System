"""雲端資料層（Supabase Postgres + pgvector）的契約測試：與本機 PandasStore／TaskStore／AuditStore 同一套行為。

需要真的 Postgres，所以預設「整個模組略過」（CI 沒有資料庫）。要跑：

    PowerShell:  $env:RUN_PG_TESTS='1'; .\\venv\\Scripts\\python -m pytest tests\\test_pg_store.py -q
                 Remove-Item Env:RUN_PG_TESTS

條件：環境變數 RUN_PG_TESTS=1 且 settings.SUPABASE_DB_URL 非空（來自 .env；測試不讀、不印連線字串）。

隔離：每次執行建立一個拋棄式 schema test_<8 hex>（search_path 由 connect hook 設定），所有資料表都建在
裡面，結束時 DROP SCHEMA ... CASCADE（測試失敗也會執行），不碰 public 的正式資料。零 AI 呼叫、零 embedding。
"""
import asyncio
import importlib.util
import json
import os
import secrets
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote, urlparse

import numpy as np
import pytest
from sqlalchemy import text

from app.config import settings
from app.services import task_store as ts_mod
from app.services.cache_service import CacheService
from app.services.pandas_store import KB_COLUMNS

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_PG_TESTS") != "1" or not (settings.SUPABASE_DB_URL or "").strip(),
    reason="Postgres tests need RUN_PG_TESTS=1 and a non-empty SUPABASE_DB_URL",
)

ROOT = Path(__file__).resolve().parent.parent
PG_TABLES = ("knowledge_base", "tasks", "admin_overrides", "user_feedback", "fact_check_records")

AI_RESULT = {
    "is_risk": True, "risk_type": "SCAM", "category": "Investment",
    "confidence_score": 0.95, "summary": "測試摘要", "explanation": "測試解釋",
    "sources": [{"title": "165", "url": "https://165.npa.gov.tw/"}],
}


def _vec(seed=7, dim=1536):
    return list(np.random.default_rng(seed).normal(size=dim).astype(float))


def _mix(base, other, cosine):
    """與 base 的 cosine similarity 約為指定值的向量（base、other 為近乎正交的隨機向量）。"""
    a = np.asarray(base) / np.linalg.norm(base)
    b = np.asarray(other) / np.linalg.norm(other)
    b = b - a * float(a @ b)
    b = b / np.linalg.norm(b)
    return list(cosine * a + np.sqrt(1 - cosine ** 2) * b)


def _ai(sources, risk_type="SCAM"):
    return {
        "is_risk": risk_type != "SAFE", "risk_type": risk_type, "category": "Test",
        "confidence_score": 0.9, "summary": "摘要", "explanation": "解釋", "sources": sources,
    }


def _save(store, content, sources=None, **kwargs):
    h = CacheService.generate_hash(content)
    ai = kwargs.pop("ai_result", None) or _ai(list(sources or []))
    rec = store.save_record(
        data_type="TEXT", raw_content=content, content_hash=h,
        content_vector=kwargs.pop("vector", None), ai_result=ai, **kwargs,
    )
    return rec, h


# ── 拋棄式 schema ────────────────────────────────────────────────
def _drop_schema(admin, schema):
    try:
        with admin.begin() as conn:
            conn.exec_driver_sql(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        with admin.connect() as conn:
            left = conn.execute(
                text("SELECT count(*) FROM pg_namespace WHERE nspname = :s"), {"s": schema}
            ).scalar()
    finally:
        admin.dispose()
    assert left == 0, "throwaway schema was not dropped"


@pytest.fixture(scope="module")
def pg():
    from app.database_sql import build_pg_engine
    from app.services.pg_store import ensure_pg_schema

    schema = "test_" + secrets.token_hex(4)
    admin = build_pg_engine()                       # search_path: public, extensions
    engine = None
    try:
        with admin.begin() as conn:
            conn.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
        engine = build_pg_engine(schema=schema)      # search_path: test_xxx, extensions, public
        ensure_pg_schema(engine, force=True)
        with engine.connect() as conn:
            assert conn.execute(text("SELECT current_schema()")).scalar() == schema
        yield {"engine": engine, "schema": schema}
    finally:                                         # 測試失敗、建表失敗都會走到這裡
        if engine is not None:
            engine.dispose()
        _drop_schema(admin, schema)


@pytest.fixture
def clean(pg):
    """每個測試前清空拋棄式 schema 的資料表（一律帶 schema 名稱，絕不會清到 public）。"""
    qualified = ", ".join(f'"{pg["schema"]}".{t}' for t in PG_TABLES)
    with pg["engine"].begin() as conn:
        conn.exec_driver_sql(f"TRUNCATE {qualified}")
    return pg


@pytest.fixture
def kb(clean):
    from app.services.pg_store import PgKnowledgeStore
    return PgKnowledgeStore(engine=clean["engine"])


@pytest.fixture
def tasks(clean):
    from app.services.pg_store import PgTaskStore
    return PgTaskStore(engine=clean["engine"])


@pytest.fixture
def audit(clean):
    from app.services.pg_store import PgAuditStore
    return PgAuditStore(engine=clean["engine"])


def _scalar(pg, sql, **params):
    with pg["engine"].connect() as conn:
        return conn.execute(text(sql), params).scalar()


# ── schema／search_path／pgvector ─────────────────────────────────
def test_schema_tables_extension_and_search_path(clean):
    from app.services.pg_store import ensure_pg_schema

    with clean["engine"].connect() as conn:
        path = conn.execute(text("SHOW search_path")).scalar()
        assert [p.strip().strip('"') for p in path.split(",")] == [clean["schema"], "extensions", "public"]
        assert conn.execute(text("SELECT count(*) FROM pg_extension WHERE extname = 'vector'")).scalar() == 1
        found = set(conn.execute(text(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = :s"
        ), {"s": clean["schema"]}).scalars())
        assert set(PG_TABLES) <= found
        vector_type = conn.execute(text(
            "SELECT format_type(a.atttypid, a.atttypmod) FROM pg_attribute a "
            "WHERE a.attrelid = to_regclass(:t) AND a.attname = 'content_vector'"
        ), {"t": f'{clean["schema"]}.knowledge_base'}).scalar()
        assert vector_type.endswith("vector(1536)")
        # RLS 開啟且沒有 policy：Supabase Data API（anon 金鑰）讀不到；後端是表的擁有者，不受影響
        rls = conn.execute(text(
            "SELECT bool_and(c.relrowsecurity) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = :s AND c.relname = ANY(:tables)"
        ), {"s": clean["schema"], "tables": list(PG_TABLES)}).scalar()
        assert rls is True
    ensure_pg_schema(clean["engine"], force=True)      # 重跑不報錯（idempotent）
    ensure_pg_schema(clean["engine"], force=True)


def test_init_sql_db_on_postgres_is_idempotent_and_trending_model_works(clean):
    from sqlalchemy.orm import sessionmaker
    from app.database_sql import init_sql_db
    from app.models.fact_check_record import FactCheckRecord

    init_sql_db(bind=clean["engine"])
    init_sql_db(bind=clean["engine"])
    session = sessionmaker(bind=clean["engine"])()
    try:
        session.add(FactCheckRecord(
            source_url="https://www.mygopen.com/2026/09/x.html", news_title="【錯誤】測試",
            risk_type="MISINFO", is_trending=True, label_source="rule", verified=True, source_tier=1,
        ))
        session.commit()
        rows = session.query(FactCheckRecord).filter(FactCheckRecord.is_trending == True).all()  # noqa: E712
        assert len(rows) == 1
        body = rows[0].to_dict()
        assert body["verified"] is True and body["source_tier"] == 1 and len(body["id"]) == 36
    finally:
        session.close()


# ── Layer 1／Layer 0 ─────────────────────────────────────────────
def test_find_by_hash_hit_miss_and_hit_count(kb):
    rec, h = _save(kb, "投資穩賺不賠", ai_result=AI_RESULT, source_url="https://example.com/a")
    hit = kb.find_by_hash(h)
    assert hit is not None and hit["id"] == rec["id"] and hit["risk_type"] == "SCAM"
    assert hit["hit_count"] == 2                                  # 寫入時 1，命中 +1
    assert kb.find_by_hash(h)["hit_count"] == 3
    assert kb.find_by_hash("0" * 64) is None
    assert set(hit) == set(KB_COLUMNS)
    assert isinstance(hit["sources"], list) and isinstance(hit["ai_analysis"], dict)
    assert isinstance(hit["created_at"], datetime) and hit["last_accessed_at"] >= hit["created_at"]


def test_find_by_url_hit_updates_hit_count(kb):
    _save(kb, "投資穩賺不賠", ai_result=AI_RESULT, source_url="https://example.com/a")
    hit = kb.find_by_url("https://example.com/a")
    again = kb.find_by_url("https://example.com/a")
    assert hit is not None and again["hit_count"] == hit["hit_count"] + 1
    assert kb.find_by_url("https://example.com/nope") is None
    assert kb.find_by_url(None) is None


def test_duplicate_hash_and_url_return_first_written_row(kb):
    """本機版取檔案中的第一筆（最早寫入）；Postgres 版以 seq 保證同一規則。"""
    first, h = _save(kb, "同一句話", source_url="https://example.com/dup")
    second, _ = _save(kb, "同一句話", source_url="https://example.com/dup")
    assert first["id"] != second["id"]
    assert kb.find_by_hash(h)["id"] == first["id"]
    assert kb.find_by_url("https://example.com/dup")["id"] == first["id"]
    assert list(kb.get_all_records()["id"]) == [first["id"], second["id"]]


# ── Layer 2：向量 ────────────────────────────────────────────────
def test_vector_exact_hit_and_below_threshold(kb):
    vec = _vec(7)
    rec, _ = _save(kb, "向量測試", ai_result=AI_RESULT, vector=vec)
    assert rec["verified"] is True
    hit = kb.find_similar_by_vector(vec, threshold=0.88)
    assert hit is not None and hit["id"] == rec["id"] and hit["hit_count"] == 2
    assert kb.find_similar_by_vector(_vec(8), threshold=0.88) is None      # 隨機向量 ~ 正交
    assert _scalar(kb_pg(kb), "SELECT hit_count FROM knowledge_base WHERE id = :i", i=rec["id"]) == 2


def kb_pg(store):
    return {"engine": store._engine}


def test_vector_hit_only_at_or_above_threshold(kb, monkeypatch):
    base = _vec(1)
    rec, _ = _save(kb, "換句話說的同一謠言", ai_result=AI_RESULT, vector=base)
    near = _mix(base, _vec(2), 0.80)                                       # 改寫帶 0.79~0.82
    far = _mix(base, _vec(3), 0.68)                                        # 不同支謠言 <= 0.68
    assert kb.find_similar_by_vector(near, threshold=0.88) is None
    assert kb.find_similar_by_vector(near, threshold=0.75)["id"] == rec["id"]
    assert kb.find_similar_by_vector(far, threshold=0.75) is None
    # threshold 省略 → settings.SIMILARITY_THRESHOLD
    monkeypatch.setattr(settings, "SIMILARITY_THRESHOLD", 0.75)
    assert kb.find_similar_by_vector(near)["id"] == rec["id"]
    monkeypatch.setattr(settings, "SIMILARITY_THRESHOLD", 0.85)
    assert kb.find_similar_by_vector(near) is None


def test_vector_best_match_wins(kb):
    base = _vec(10)
    far, _ = _save(kb, "較遠", ai_result=AI_RESULT, vector=_mix(base, _vec(11), 0.80))
    near, _ = _save(kb, "較近", ai_result=AI_RESULT, vector=_mix(base, _vec(12), 0.95))
    assert kb.find_similar_by_vector(base, threshold=0.75)["id"] == near["id"]
    assert far["id"] != near["id"]


def test_vector_only_matches_verified_rows(kb):
    vec = _vec(7)
    rec, h = _save(
        kb, "某部落格說法",
        [{"title": "部落格", "url": "https://blog.example.com/p"},
         {"title": "社群", "url": "https://www.facebook.com/x"}],
        vector=vec,
    )
    assert rec["verified"] is False and rec["source_tier"] is None
    assert kb.find_similar_by_vector(vec, threshold=0.5) is None          # 相似度 1.0 仍不命中
    hit = kb.find_by_hash(h)                                              # hash 層不過濾 verified
    assert hit is not None and hit["verified"] is False


def test_vector_guards_never_raise(kb):
    vec = _vec(7)
    _save(kb, "守門", ai_result=AI_RESULT, vector=vec)
    assert kb.find_similar_by_vector([], threshold=0.88) is None             # 空向量（層停用）
    assert kb.find_similar_by_vector(None, threshold=0.88) is None
    assert kb.find_similar_by_vector([0.0] * 1536, threshold=0.88) is None    # 零向量
    assert kb.find_similar_by_vector([0.1, 0.2], threshold=0.88) is None      # 維度不符
    assert kb.find_similar_by_vector(_vec(1, dim=768), threshold=0.0) is None
    assert kb.find_similar_by_vector([float("nan")] * 1536, threshold=0.0) is None


def test_non_1536_vectors_are_stored_as_null(kb):
    rec768, h = _save(kb, "舊的 768 維向量", ai_result=AI_RESULT, vector=_vec(1, dim=768))
    rec3072, _ = _save(kb, "3072 維向量", ai_result=AI_RESULT, vector=_vec(2, dim=3072))
    ok, _ = _save(kb, "正常 1536 維", ai_result=AI_RESULT, vector=_vec(3))
    assert rec768["content_vector"] is None and rec3072["content_vector"] is None
    assert len(ok["content_vector"]) == 1536
    pg_ = kb_pg(kb)
    assert _scalar(pg_, "SELECT count(*) FROM knowledge_base WHERE content_vector IS NULL") == 2
    assert _scalar(pg_, "SELECT count(*) FROM knowledge_base WHERE content_vector IS NOT NULL") == 1
    assert kb.find_by_hash(h)["id"] == rec768["id"]                       # 列本身保留，hash 仍命中


# ── FR-17 寫入門檻（compute_write_gate 與本機版同一個函式）──────────────
def test_write_gate_matches_local_store(kb, tmp_path):
    from app.services.pandas_store import PandasStore

    local = PandasStore(data_dir=str(tmp_path))
    long_text = "網傳喝熱水可以殺死病毒這是一段超過四十個字的謠言內容，用來測試標題截斷是否正確運作喔"
    cases = [
        ("tier1", dict(content="假冒165詐騙", sources=[{"title": "165", "url": "https://165.npa.gov.tw/x"}])),
        ("tier3", dict(content="某部落格說法", sources=[{"title": "部落格", "url": "https://blog.example.com/p"}])),
        ("rule", dict(content="規則命中的謠言", sources=[], label_source="rule")),
        ("forced_false", dict(content="覆寫", sources=[{"title": "t", "url": "https://mygopen.com/a"}], verified=False)),
        ("forced_true", dict(content="覆寫二", sources=[], verified=True)),
        ("backfill", dict(content=long_text, sources=[], source_url="https://tfc-taiwan.org.tw/articles/123",
                          label_source="rule")),
        ("no_backfill", dict(content="一般新聞", sources=[], source_url="https://news.example.com/a")),
    ]
    expected = {
        "tier1": (True, 1), "tier3": (False, None), "rule": (True, None), "forced_false": (False, 1),
        "forced_true": (True, None), "backfill": (True, 1), "no_backfill": (False, None),
    }
    for name, case in cases:
        kwargs = {k: v for k, v in case.items() if k not in ("content", "sources")}
        cloud, _ = _save(kb, case["content"], case["sources"], **kwargs)
        disk, _ = _save(local, case["content"], case["sources"], **kwargs)
        for key in ("verified", "source_tier", "label_source", "sources", "origin", "hit_count"):
            assert cloud[key] == disk[key], (name, key)
        assert (cloud["verified"], cloud["source_tier"]) == expected[name], name
    backfilled = kb.find_by_hash(CacheService.generate_hash(long_text))
    assert backfilled["sources"] == [{
        "title": long_text[:40], "url": "https://tfc-taiwan.org.tw/articles/123",
        "tier": 1, "tier_label": "查核機構",
    }]


def test_saved_sources_carry_tier_in_sources_and_ai_analysis(kb):
    sources = [
        {"title": "MyGoPen", "url": "https://www.mygopen.com/2026/09/x.html"},
        {"title": "查核：網傳喝鹽水治新冠是假的", "url": "https://www.ettoday.net/news/1"},
        {"title": "一般新聞", "url": "https://www.ettoday.net/news/2"},
        {"title": "已分級", "url": "https://cofacts.tw/article/abc", "tier": 1},
    ]
    rec, h = _save(kb, "分級測試", sources)
    assert rec["source_tier"] == 1
    for reloaded in (kb.find_by_hash(h), kb.get_all_records().iloc[0].to_dict()):
        for container in (reloaded["sources"], reloaded["ai_analysis"]["sources"]):
            assert [int(s["tier"]) for s in container] == [1, 2, 3, 1]
            assert all(s["tier_label"] for s in container)
    assert "tier" not in sources[0]                                      # 呼叫端的 dict 不被修改


def test_related_discussions_kept_as_json_string(kb):
    related = [{"title": "PTT", "url": "https://www.ptt.cc/x", "tier": 3, "tier_label": "相關討論（未查證）"}]
    rec, h = _save(kb, "相關討論", ai_result=AI_RESULT, related_discussions=related,
                   origin="threads", last_result_id="task-1")
    assert isinstance(rec["related_discussions"], str)
    hit = kb.find_by_hash(h)
    assert isinstance(hit["related_discussions"], str) and json.loads(hit["related_discussions"]) == related
    assert hit["origin"] == "threads" and hit["last_result_id"] == "task-1"
    plain, h2 = _save(kb, "沒有相關討論", ai_result=AI_RESULT)
    assert kb.find_by_hash(h2)["related_discussions"] is None


# ── get_all_records 形狀 ─────────────────────────────────────────
def test_get_all_records_shape_matches_local(kb, tmp_path):
    from app.services.pandas_store import PandasStore

    empty = kb.get_all_records()
    assert empty.empty and list(empty.columns) == KB_COLUMNS

    local = PandasStore(data_dir=str(tmp_path))
    for store in (kb, local):
        _save(store, "第一筆", ai_result=AI_RESULT, vector=_vec(1), source_url="https://example.com/1")
        _save(store, "第二筆", [{"title": "部落格", "url": "https://blog.example.com/p"}],
              related_discussions=[{"url": "https://www.ptt.cc/x", "tier": 3}])
    cloud, disk = kb.get_all_records(), local.get_all_records()

    assert list(cloud.columns) == KB_COLUMNS and set(disk.columns) == set(KB_COLUMNS)
    assert list(cloud["raw_content"]) == list(disk["raw_content"]) == ["第一筆", "第二筆"]   # 寫入順序
    for col in ("is_risk", "verified", "hit_count", "confidence_score", "source_tier"):
        assert cloud[col].dtype == disk[col].dtype, col
    for col in ("created_at", "last_accessed_at"):
        assert cloud[col].dtype.kind == disk[col].dtype.kind == "M", col
    for col in ("risk_type", "category", "summary", "label_source", "origin", "data_hash", "data_type"):
        assert list(cloud[col]) == list(disk[col]), col
    assert list(cloud["verified"]) == list(disk["verified"]) == [True, False]
    assert cloud["source_tier"].isna().tolist() == disk["source_tier"].isna().tolist() == [False, True]

    row = cloud.iloc[0]
    assert isinstance(row["sources"], list) and isinstance(row["sources"][0], dict)
    assert isinstance(row["ai_analysis"], dict) and row["ai_analysis"]["risk_type"] == "SCAM"
    assert row["content_vector"] is None                                 # 預設不載入向量
    assert isinstance(cloud.iloc[1]["related_discussions"], str)
    assert cloud.iloc[0]["related_discussions"] is None
    assert [list(s) for s in cloud["sources"]] == [list(s) for s in disk["sources"]]

    with_vectors = kb.get_all_records(include_vectors=True)
    vector = with_vectors.iloc[0]["content_vector"]
    assert isinstance(vector, np.ndarray) and vector.shape == (1536,)
    assert np.allclose(vector, np.asarray(_vec(1), dtype=np.float32), atol=1e-6)
    assert with_vectors.iloc[1]["content_vector"] is None


def test_knowledge_api_reads_the_pg_store(kb, monkeypatch):
    from fastapi.testclient import TestClient
    import app.api.knowledge as knowledge_api
    from app.main import app

    monkeypatch.setattr(knowledge_api, "_store", kb)
    a, _ = _save(kb, "健保卡停用，請點連結(今天)重新驗證",
                 [{"title": "165", "url": "https://165.npa.gov.tw/x"},
                  {"title": "PTT", "url": "https://www.ptt.cc/bbs/x"}])
    _save(kb, "喝鹽水治新冠", [{"title": "MyGoPen", "url": "https://www.mygopen.com/a"}],
          ai_result=_ai([{"title": "MyGoPen", "url": "https://www.mygopen.com/a"}], "MISINFO"))
    _save(kb, "未證實(草稿)", [{"title": "部落格", "url": "https://blog.example.com/p"}])

    client = TestClient(app)                                             # 不進 lifespan
    stats = client.get("/api/knowledge/stats").json()
    assert stats["total"] == 2 and stats["unverified_count"] == 1
    assert stats["counts"] == {"scam": 1, "misinfo": 1, "safe": 0, "unverifiable": 0}

    body = client.get("/api/knowledge", params={"limit": 5}).json()
    assert body["total"] == 2 and len(body["records"]) == 2
    found = client.get("/api/knowledge", params={"q": "(今天)"}).json()     # 字面比對
    assert [r["id"] for r in found["records"]] == [a["id"]]
    record = found["records"][0]
    assert [s["tier"] for s in record["sources"]] == [1]                  # Tier 3 不外露
    assert record["source_tier"] == 1 and record["hit_count"] == 1 and record["created_at"]
    assert client.get("/api/knowledge", params={"risk_type": "misinfo"}).json()["total"] == 1
    assert client.get("/api/knowledge", params={"q": "(草稿)"}).json()["total"] == 0


# ── 任務 ─────────────────────────────────────────────────────────
def test_task_lifecycle_defaults_and_json_columns(tasks):
    tid = tasks.create_task("analyze_text", "測試輸入")
    task = tasks.get_task(tid)
    assert set(task) == set(ts_mod._ALL_COLUMNS)
    assert task["status"] == "pending" and task["input_type"] == "text" and task["origin"] == "web"
    assert task["ai_unavailable"] is False and task["verified"] is False and task["label_source"] == "ai"
    for key in ("result_data", "error_message", "completed_at", "threads_mention_id", "threads_reply_id",
                "platform_post", "kb_id", "source_tier", "related_discussions"):
        assert task[key] is None, key
    assert isinstance(task["created_at"], str) and datetime.fromisoformat(task["created_at"])

    tasks.update_task(tid, status="completed", result_data="{}")
    done = tasks.get_task(tid)
    assert done["status"] == "completed" and done["result_data"] == "{}"
    assert done["updated_at"] >= task["updated_at"]
    assert tasks.get_task("no-such-id") is None
    tasks.update_task("no-such-id", status="failed")                     # 不存在：不做事、不報錯

    web_id = tasks.create_task("analyze_url", "https://example.com")
    post = {"platform": "threads", "post_id": "123", "permalink": "https://www.threads.net/@a/post/x",
            "username": "a"}
    threads_id = tasks.create_task(
        "threads_mention", "可疑貼文", origin="threads",
        threads_mention_id="m-1", platform_post=post, not_a_column="ignored",
    )
    tasks.update_task(
        threads_id, status="completed", threads_reply_id="r-1", ai_unavailable=True,
        label_source="ai", kb_id="kb-9", verified=True, source_tier=2,
        related_discussions=[{"url": "https://ptt.cc/x", "tier": 3}],
        completed_at=datetime.utcnow(), also_not_a_column=1,
    )
    t = tasks.get_task(threads_id)
    assert t["origin"] == "threads" and t["input_type"] == "text"
    assert t["threads_mention_id"] == "m-1" and t["threads_reply_id"] == "r-1"
    assert isinstance(t["platform_post"], str) and json.loads(t["platform_post"]) == post
    assert "not_a_column" not in t
    assert t["ai_unavailable"] is True and t["verified"] is True
    assert t["source_tier"] == 2 and type(t["source_tier"]) is int and t["kb_id"] == "kb-9"
    assert json.loads(t["related_discussions"])[0]["tier"] == 3
    assert isinstance(t["completed_at"], str)

    web = tasks.get_task(web_id)
    assert web["origin"] == "web" and web["input_type"] == "url"
    assert web["verified"] is False and web["source_tier"] is None
    assert tasks.get_task(tasks.create_task("analyze_text", "x", input_type="image"))["input_type"] == "image"
    assert tasks.get_task(tasks.create_task("analyze_image", "img.png"))["input_type"] == "image"


def test_task_prune_only_finished_oldest_first(tasks, monkeypatch):
    monkeypatch.setattr(ts_mod, "_MAX_TASKS", 3)

    def ids():
        with tasks._engine.connect() as conn:
            return set(conn.execute(text("SELECT id FROM tasks")).scalars())

    p1 = tasks.create_task("analyze_text", "pending-1")                  # 最舊，但 pending
    c1 = tasks.create_task("analyze_text", "completed-1")
    tasks.update_task(c1, status="completed")
    f1 = tasks.create_task("analyze_text", "failed-1")
    tasks.update_task(f1, status="failed")
    pr1 = tasks.create_task("analyze_text", "processing-1")
    tasks.update_task(pr1, status="processing")
    assert ids() == {p1, f1, pr1}                                        # 第 4 筆超過上限：刪最舊的已結束者 c1

    p2 = tasks.create_task("analyze_text", "pending-2")
    assert ids() == {p1, pr1, p2}                                        # f1 被刪
    p3 = tasks.create_task("analyze_text", "pending-3")
    assert ids() == {p1, pr1, p2, p3}                                    # 全是進行中：不硬砍


def test_result_and_task_endpoints_read_the_pg_task_store(tasks, monkeypatch):
    from fastapi.testclient import TestClient
    import app.api.analyze as analyze_api
    import app.api.result as result_api
    import app.workers.pandas_task_processor as proc
    from app.main import app

    monkeypatch.setattr(analyze_api, "task_store", tasks)
    monkeypatch.setattr(result_api, "task_store", tasks)
    tid = tasks.create_task("analyze_text", "假冒165詐騙", input_type="text")
    client = TestClient(app)
    pending = client.get(f"/api/result/{tid}").json()
    assert pending["status"] == "pending" and pending["result"] is None

    built = proc._build_result(
        _ai([{"title": "165", "url": "https://165.npa.gov.tw/x"}]), result_id=tid, label_source="ai",
    )
    proc._complete(tasks, tid, built)
    body = client.get(f"/api/result/{tid}").json()
    assert body["status"] == "completed" and body["input_preview"] == "假冒165詐騙"
    assert body["result"]["risk_type"] == "SCAM" and body["result"]["verification_status"] == "verified"
    assert body["created_at"].endswith("+08:00") and body["completed_at"].endswith("+08:00")
    assert client.get(f"/api/analyze/task/{tid}").json()["result_id"] == tid
    assert client.get(f"/api/analyze/task/{tid}/status").json()["status"] == "completed"
    assert client.get("/api/result/no-such-id").status_code == 404


# ── 三層快取主流程（處理器）接 Postgres ─────────────────────────────
def test_processor_three_layers_on_pg(kb, tasks, monkeypatch):
    import app.workers.pandas_task_processor as proc

    text_in = "緊急！點擊連結領取政府普發現金六千元，逾期作廢，加LINE客服 gov888 快速申請"
    paraphrase = "快點連結領政府普發的六千元現金，過期就沒了，加 LINE 客服 gov888 申請"
    vectors = {text_in: _vec(21), paraphrase: _mix(_vec(21), _vec(22), 0.82)}
    calls = {"ai": 0}

    class FakeAI:
        def analyze_content(self, content, url=None, context=None, use_web_search=None):
            calls["ai"] += 1
            return {**_ai([{"title": "165", "url": "https://165.npa.gov.tw/x"},
                           {"title": "PTT", "url": "https://www.ptt.cc/bbs/x"}]), "provider": "cgu"}

    class FakeVector:
        def vectorize_content(self, value):
            return vectors.get(value, [])

    class NoCrawler:
        async def process_input(self, data, input_type):
            raise AssertionError("text input must not crawl")

    async def grade(sources):
        tiered, related = proc._partition_sources(sources)
        return tiered, related, 0

    monkeypatch.setattr(proc, "TaskStore", lambda: tasks)
    monkeypatch.setattr(proc, "PandasStore", lambda: kb)
    monkeypatch.setattr(proc, "AIService", FakeAI)
    monkeypatch.setattr(proc, "VectorService", FakeVector)
    monkeypatch.setattr(proc, "CrawlerService", NoCrawler)
    monkeypatch.setattr(proc, "filter_valid_sources", lambda sources: sources)
    monkeypatch.setattr(proc, "grade_sources", grade)
    monkeypatch.setattr(settings, "SIMILARITY_THRESHOLD", 0.75)

    def run(content):
        tid = tasks.create_task("analyze_text", content, input_type="text")
        return tid, asyncio.run(proc.process_analysis_task_async(tid, content, "text"))

    tid1, first = run(text_in)                                           # L3：AI → 寫知識庫
    assert calls["ai"] == 1 and first["cached"] is False and first["cache_layer"] is None
    assert first["verification_status"] == "verified" and first["source_tier"] == 1
    assert [s["tier"] for s in first["sources"]] == [1]
    assert [s["tier"] for s in first["related_discussions"]] == [3]
    df = kb.get_all_records()
    assert len(df) == 1 and df.iloc[0]["raw_content"] == text_in and bool(df.iloc[0]["verified"])
    assert df.iloc[0]["last_result_id"] == tid1 and df.iloc[0]["id"] == first["kb_id"]
    assert "provider" not in df.iloc[0]["ai_analysis"]                   # 呼叫資訊不進知識庫

    tid2, second = run(text_in)                                          # L1：hash
    assert calls["ai"] == 1 and second["cached"] is True and second["cache_layer"] == "hash"
    assert second["kb_id"] == first["kb_id"] and [s["tier"] for s in second["sources"]] == [1]
    assert [s["tier"] for s in second["related_discussions"]] == [3]

    tid3, third = run(paraphrase)                                        # L2：向量
    assert calls["ai"] == 1 and third["cache_layer"] == "vector" and third["kb_id"] == first["kb_id"]

    stored = tasks.get_task(tid2)
    assert stored["status"] == "completed" and stored["kb_id"] == first["kb_id"]
    assert stored["verified"] is True and stored["source_tier"] == 1
    assert json.loads(stored["result_data"])["cache_layer"] == "hash"
    assert json.loads(stored["related_discussions"])[0]["tier"] == 3
    assert _scalar(kb_pg(kb), "SELECT hit_count FROM knowledge_base") == 3


# ── 管理者覆寫＋稽核 ─────────────────────────────────────────────
def test_admin_override_updates_task_kb_row_and_audit(kb, tasks, audit, monkeypatch):
    from fastapi.testclient import TestClient
    import app.api.admin as admin_api
    import app.api.result as result_api
    import app.workers.pandas_task_processor as proc
    from app.main import app

    token = "pg-test-admin-token"
    monkeypatch.setattr(settings, "ADMIN_TOKEN", token)
    monkeypatch.setattr(admin_api, "task_store", tasks)
    monkeypatch.setattr(admin_api, "kb_store", kb)
    monkeypatch.setattr(admin_api, "audit_store", audit)
    monkeypatch.setattr(result_api, "task_store", tasks)

    content, vec = "網傳領取振興券要先輸入信用卡號", _vec(5)
    ai = {"is_risk": False, "risk_type": "SAFE", "category": "Safe", "confidence_score": 0.9,
          "summary": "看起來是官方公告", "explanation": "e",
          "sources": [{"title": "部落格", "url": "https://blog.example.com/p"}]}
    row, _ = _save(kb, content, ai_result=ai, vector=vec)
    other, _ = _save(kb, "別的列", ai_result=AI_RESULT)
    assert row["verified"] is False and kb.find_similar_by_vector(vec, threshold=0.5) is None

    tid = tasks.create_task("analyze_text", content, input_type="text")
    proc._complete(tasks, tid, proc._build_result(ai, result_id=tid, label_source="ai", kb_id=row["id"]))

    client = TestClient(app)
    body = {"risk_type": "SCAM", "category": "Phishing", "confidence_score": 0.99,
            "reason": "人工複核", "admin_id": "tester"}
    assert client.post(f"/api/admin/tasks/{tid}/override", json=body).status_code == 401
    resp = client.post(f"/api/admin/tasks/{tid}/override", json=body, headers={"X-Admin-Token": token})
    assert resp.status_code == 200, resp.text
    result = resp.json()
    assert result["label_source"] == "admin" and result["risk_type"] == "SCAM" and result["is_risk"] is True
    assert result["verification_status"] == "rule" and result["frame_type"] == "red"

    task = tasks.get_task(tid)
    assert task["label_source"] == "admin" and task["verified"] is True
    assert json.loads(task["result_data"])["frame_type"] == "red"

    df = kb.get_all_records().set_index("id")
    changed, untouched = df.loc[row["id"]], df.loc[other["id"]]
    assert changed["label_source"] == "admin" and bool(changed["verified"]) is True
    assert changed["risk_type"] == "SCAM" and bool(changed["is_risk"]) is True
    assert changed["category"] == "Phishing" and float(changed["confidence_score"]) == 0.99
    assert changed["ai_analysis"]["risk_type"] == "SCAM" and changed["ai_analysis"]["is_risk"] is True
    assert changed["ai_analysis"]["summary"] == "看起來是官方公告"        # 其餘鍵保留
    assert untouched["label_source"] == "ai" and untouched["risk_type"] == "SCAM"
    hit = kb.find_similar_by_vector(vec, threshold=0.5)                   # 確定性標記 → 參與向量命中
    assert hit is not None and hit["id"] == row["id"]
    assert kb.apply_admin_override("no-such-row", {"risk_type": "SAFE"}) is False

    overrides = audit._load_overrides()
    assert len(overrides) == 1 and overrides.iloc[0]["task_id"] == tid
    assert overrides.iloc[0]["new_risk_type"] == "SCAM" and overrides.iloc[0]["admin_id"] == "tester"


def test_audit_store_writes(audit, tasks, monkeypatch):
    from fastapi.testclient import TestClient
    import app.api.feedback as feedback_api
    from app.main import app

    record = audit.append_override(task_id="t-1", admin_id="a", reason="r", new_risk_type="SCAM",
                                   new_confidence_score=0.5)
    assert record["task_id"] == "t-1" and isinstance(record["created_at"], str) and len(record["id"]) == 36
    feedback = audit.append_feedback(task_id="t-1", rating="agree", comment="謝謝", user_id=None)
    assert feedback["rating"] == "agree" and isinstance(feedback["created_at"], str)
    assert list(audit._load_overrides()["new_confidence_score"]) == [0.5]
    assert audit._load_feedback().iloc[0]["comment"] == "謝謝"

    monkeypatch.setattr(feedback_api, "task_store", tasks)
    monkeypatch.setattr(feedback_api, "audit_store", audit)
    tid = tasks.create_task("analyze_text", "回饋測試")
    client = TestClient(app)
    assert client.post(f"/api/feedback/tasks/{tid}", json={"rating": "disagree"}).json() == {"status": "ok"}
    assert client.post("/api/feedback/tasks/nope", json={"rating": "agree"}).status_code == 404
    assert list(audit._load_feedback()["rating"]) == ["agree", "disagree"]


# ── 遷移腳本：整條路徑在拋棄式 schema 內跑，第二次不動任何列 ─────────────
def _load_migrate_module():
    spec = importlib.util.spec_from_file_location("migrate_to_supabase", ROOT / "scripts" / "migrate_to_supabase.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)                                      # 非 __main__：不會執行 main()
    return module


def _build_local_data(data_dir: Path):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.database_sql import init_sql_db
    from app.models.fact_check_record import FactCheckRecord
    from app.services.audit_store import AuditStore
    from app.services.pandas_store import PandasStore
    from app.services.task_store import TaskStore

    store = PandasStore(data_dir=str(data_dir))
    _save(store, "有 1536 維向量的已證實列", ai_result=AI_RESULT, vector=_vec(1))
    _save(store, "舊的 768 維向量", ai_result=AI_RESULT, vector=_vec(2, dim=768))
    _save(store, "未證實、沒有向量", [{"title": "部落格", "url": "https://blog.example.com/p"}],
          related_discussions=[{"url": "https://www.ptt.cc/x", "tier": 3}])
    ts = TaskStore(data_dir=str(data_dir))
    done = ts.create_task("analyze_text", "已完成的任務")
    ts.update_task(done, status="completed", result_data='{"risk_type": "SCAM"}',
                   completed_at=datetime.utcnow(), verified=True, source_tier=1, kb_id="kb-1")
    ts.create_task("analyze_url", "https://example.com/pending")
    AuditStore(data_dir=str(data_dir)).append_feedback(task_id=done, rating="agree")

    sqlite_engine = create_engine(f"sqlite:///{(data_dir / 'factcheck.db').as_posix()}")
    try:
        init_sql_db(bind=sqlite_engine)
        session = sessionmaker(bind=sqlite_engine)()
        session.add_all([
            FactCheckRecord(source_url="https://www.mygopen.com/a", news_title="【錯誤】甲", risk_type="MISINFO",
                            is_trending=True, label_source="rule", verified=True, source_tier=1, ai_score=0.95),
            FactCheckRecord(source_url="https://tfc-taiwan.org.tw/b", news_title="乙", risk_type="PENDING",
                            is_trending=True),
        ])
        session.commit()
        session.close()
    finally:
        sqlite_engine.dispose()
    return done


def test_migration_script_is_idempotent(clean, tmp_path, monkeypatch, capsys):
    migrate = _load_migrate_module()
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    done_id = _build_local_data(data_dir)
    monkeypatch.chdir(ROOT)
    args = ["--data-dir", str(data_dir), "--schema", clean["schema"]]

    def counts():
        return {t: _scalar(clean, f"SELECT count(*) FROM {t}") for t in PG_TABLES}

    assert migrate.main(args) == 0                                        # dry-run：不寫入
    assert counts() == {t: 0 for t in PG_TABLES}
    dry = capsys.readouterr().out
    assert "DRY-RUN" in dry and "non-1536-dim stored as NULL=1" in dry and "dim768=1" in dry

    assert migrate.main(args + ["--apply"]) == 0
    first = capsys.readouterr().out
    expected = {"knowledge_base": 3, "tasks": 2, "admin_overrides": 0, "user_feedback": 1, "fact_check_records": 2}
    assert counts() == expected
    assert "rows=3 verified=2 with_vector=1 null_vector=2" in first
    snapshot = _scalar(clean, "SELECT md5(string_agg(t::text, '|' ORDER BY t.id)) FROM knowledge_base t")

    assert migrate.main(args + ["--apply"]) == 0                          # 第二次：零新增、零更新
    second = capsys.readouterr().out
    assert counts() == expected
    assert snapshot == _scalar(clean, "SELECT md5(string_agg(t::text, '|' ORDER BY t.id)) FROM knowledge_base t")
    for line in second.splitlines():
        cells = line.split()
        if cells and cells[0] in expected and len(cells) == 7:
            assert cells[2:4] == ["0", "0"] or cells[2:4] == ["-", "-"], line   # inserted / updated
    assert "WARNING" not in first + second and "FAILED" not in first + second

    # 本機改了一列 → 只有那一列被更新；--insert-only 則完全不動既有列
    from app.services.task_store import TaskStore
    TaskStore(data_dir=str(data_dir)).update_task(done_id, error_message="edited locally")
    assert migrate.main(args + ["--apply", "--insert-only"]) == 0
    capsys.readouterr()
    assert _scalar(clean, "SELECT error_message FROM tasks WHERE id = :i", i=done_id) is None
    assert migrate.main(args + ["--apply"]) == 0
    third = capsys.readouterr().out
    assert _scalar(clean, "SELECT error_message FROM tasks WHERE id = :i", i=done_id) == "edited locally"
    task_line = [ln.split() for ln in third.splitlines() if ln.split()[:1] == ["tasks"] and len(ln.split()) == 7][0]
    assert task_line[2:5] == ["0", "1", "1"]                              # inserted 0、updated 1、unchanged 1

    # 遷移進來的資料可被 store 正常讀取（型別轉換正確）
    from app.services.pg_store import PgKnowledgeStore, PgTaskStore
    migrated = PgKnowledgeStore(engine=clean["engine"])
    assert migrated.find_similar_by_vector(_vec(1), threshold=0.99)["raw_content"] == "有 1536 維向量的已證實列"
    assert migrated.find_by_hash(CacheService.generate_hash("舊的 768 維向量"))["verified"] is True
    task = PgTaskStore(engine=clean["engine"]).get_task(done_id)
    assert task["status"] == "completed" and task["verified"] is True and task["source_tier"] == 1
    assert _scalar(clean, "SELECT verified FROM fact_check_records WHERE risk_type = 'PENDING'") is None

    # 輸出只有 ASCII，且不含連線字串／密碼
    output = dry + first + second + third
    assert not _leaks_credentials(output)
    assert output.isascii()


def _leaks_credentials(output: str) -> bool:
    """只回傳布林：連線字串與密碼不留在測試函式的區域變數，也不會出現在斷言失敗訊息裡。"""
    raw = (settings.SUPABASE_DB_URL or "").strip()
    password = urlparse(raw).password or ""
    return any(s and s in output for s in (raw, password, unquote(password)))


# ── 每日 AI 次數上限的計數表（app/services/ai_budget.py）在 Postgres 上的行為 ─────────
def test_ai_budget_counts_atomically_on_postgres(pg, monkeypatch):
    import threading

    from app.services.ai_budget import TABLE, AiBudget

    monkeypatch.setattr(settings, "DAILY_AI_CALL_CAP", 3)
    with pg["engine"].begin() as conn:
        conn.exec_driver_sql(f'DROP TABLE IF EXISTS "{pg["schema"]}".{TABLE}')

    budget = AiBudget(engine=pg["engine"])
    assert budget.calls_today() == 0                       # 第一次使用時自己建表
    results = []
    lock = threading.Lock()

    def worker():
        ok = budget.try_consume()
        with lock:
            results.append(ok)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert results.count(True) == 3                        # 同時 8 個請求，剛好 3 個拿到額度
    assert budget.calls_today() == 3 and budget.cap_reached() is True
    assert AiBudget(engine=pg["engine"]).calls_today() == 3   # 新行程（主機重啟）讀得到同一個數字

    with pg["engine"].connect() as conn:
        in_schema, rls = conn.execute(text(
            "SELECT n.nspname, c.relrowsecurity FROM pg_class c "
            "JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE c.relname = :t AND n.nspname = :s"
        ), {"t": TABLE, "s": pg["schema"]}).one()
    assert in_schema == pg["schema"] and rls is True       # 建在拋棄式 schema、RLS 已啟用
