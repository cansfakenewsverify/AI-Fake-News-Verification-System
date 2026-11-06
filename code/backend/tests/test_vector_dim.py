"""向量維度改由設定決定、換模型的遷移與重算（票 B-52：Mercury 的 bge-m3，1024 維）。離線、零 API 呼叫、不連資料庫。"""
import importlib.util
import re
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from app.config import settings
from app.services import ai_service
from app.services import factcheck_corpus as fc
from app.services import pg_store

ROOT = Path(__file__).resolve().parent.parent
MB = 1024 * 1024


def _load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def dim1024(monkeypatch):
    monkeypatch.setattr(settings, "VECTOR_DIMENSION", 1024)


def _unit(seed, dim):
    v = np.random.default_rng(seed).normal(size=dim)
    return list(v / np.linalg.norm(v))


# ── pg_store 讀設定 ─────────────────────────────────────────────
def test_vector_literal_follows_the_configured_dimension(dim1024):
    assert pg_store.vector_dim() == 1024
    assert pg_store.vector_literal(_unit(1, 1024)) is not None
    assert pg_store.vector_literal(_unit(1, 1536)) is None        # 舊模型的向量存 NULL、不參與比對


def test_table_definition_uses_the_configured_dimension(dim1024):
    ddl = pg_store._DDL_STATEMENTS[0].replace("{vector_dim}", str(pg_store.vector_dim()))
    assert "content_vector      vector(1024)" in ddl


class _Result:
    rowcount = 1

    def mappings(self):
        return self

    def first(self):
        return None

    def all(self):
        return []


class _Conn:
    def __init__(self):
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, statement, params=None):
        self.calls.append((str(statement), params))
        return _Result()


class _Engine:
    def __init__(self):
        self.conn = _Conn()

    def connect(self):
        return self.conn


def _store_with_column(dim):
    engine = _Engine()
    store = pg_store.PgKnowledgeStore(engine=engine)
    store._autocommit_engine = engine          # 跳過真的連線與建表
    pg_store._COLUMN_DIM[engine] = dim
    return store, engine.conn


def test_column_of_another_dimension_skips_vector_queries_instead_of_failing(dim1024):
    """設定已是 1024、資料庫欄位還是 1536（遷移前就上線）：不送進資料庫報錯，語意比對當作沒命中。"""
    store, conn = _store_with_column(1536)
    vec = _unit(3, 1024)
    assert store.find_similar_by_vector(vec, threshold=0.5) is None
    assert store.nearest_verified(vec, k=5) == []
    assert store.set_vectors({"a": vec}) == 0
    assert conn.calls == []
    record = store.save_record(data_type="TEXT", raw_content="測試", content_hash="h", content_vector=vec,
                               ai_result={"is_risk": True, "risk_type": "SCAM", "sources": []})
    (sql, params), = conn.calls
    assert sql.startswith("INSERT INTO knowledge_base") and params["content_vector"] is None
    assert record["content_vector"] is None


def test_matching_column_sends_the_query(dim1024):
    store, conn = _store_with_column(1024)
    store.find_similar_by_vector(_unit(3, 1024), threshold=0.5)
    assert len(conn.calls) == 1 and "content_vector <=>" in conn.calls[0][0]


# ── generate_embedding 截斷長文 ─────────────────────────────────
def test_generate_embedding_sends_at_most_the_corpus_limit(monkeypatch):
    sent = []

    class Resp:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {"data": [{"embedding": [0.1, 0.2]}]}

    def post(url, headers=None, json=None, timeout=None):
        sent.append(json)
        return Resp()

    monkeypatch.setattr(settings, "EMBED_RELAY_URL", "https://example.invalid/v1")
    monkeypatch.setattr(settings, "EMBED_API_KEY", "dummy-key")
    monkeypatch.setattr(settings, "EMBED_MODEL", "bge-m3")
    monkeypatch.setattr(ai_service, "_embed_retry_at", 0.0)
    monkeypatch.setattr(ai_service, "_EMBED_STATUS", {"ok": None, "checked_at": None, "error": None})
    monkeypatch.setattr(ai_service.requests, "post", post)
    assert ai_service.AIService().generate_embedding("長" * 5000) == [0.1, 0.2]
    assert sent[0]["model"] == "bge-m3" and len(sent[0]["input"]) == fc.EMBED_MAX_CHARS


def test_embed_batch_accepts_responses_without_index(monkeypatch):
    class Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"data": [{"embedding": [1.0, 0.0]}, {"embedding": [0.0, 1.0]}], "usage": {"total_tokens": 4}}

    monkeypatch.setattr(settings, "EMBED_RELAY_URL", "https://example.invalid/v1")
    monkeypatch.setattr(settings, "EMBED_API_KEY", "dummy-key")
    monkeypatch.setattr(fc.requests, "post", lambda *a, **k: Resp())
    vectors, tokens = fc.embed_batch(["甲", "乙"])
    assert [v.tolist() for v in vectors] == [[1.0, 0.0], [0.0, 1.0]] and tokens == 4


# ── 遷移腳本 migrate_vector_dim.py ──────────────────────────────
mig = _load("migrate_vector_dim")


class _Row:
    def __init__(self, row):
        self.row = row

    def fetchone(self):
        return self.row


class _MigConn:
    """假的 psycopg 連線：記下 SQL，依欄位狀態回答查詢，ALTER 會真的改狀態。"""

    def __init__(self, columns, indexes=(), db_bytes=225 * MB, heap_bytes=40 * MB, fail_alter=False):
        self.columns = dict(columns)
        self.indexes = set(indexes)
        self.db_bytes, self.heap_bytes = db_bytes, heap_bytes
        self.fail_alter = fail_alter
        self.sql = []
        self.in_tx = False

    def transaction(self):
        conn = self

        class _Tx:
            def __enter__(self):
                conn.in_tx = True
                conn.snapshot = (dict(conn.columns), set(conn.indexes))

            def __exit__(self, exc_type, *rest):
                conn.in_tx = False
                if exc_type is not None:               # 交易失敗：全部不生效
                    conn.columns, conn.indexes = conn.snapshot
                return False

        return _Tx()

    def execute(self, sql, params=()):
        self.sql.append(sql)
        if "format_type" in sql:
            dim = self.columns.get(params[1])
            return _Row(None if dim is None else (f"vector({dim})",))
        if "pg_database_size" in sql:
            return _Row((self.db_bytes,))
        if "pg_total_relation_size" in sql:
            return _Row((200 * MB,))
        if "pg_relation_size" in sql:
            return _Row((self.heap_bytes,))
        if "FROM pg_class" in sql:
            return _Row((1 if params[0] in self.indexes else 0,))
        if sql.startswith("SELECT count(*)"):
            return _Row((18891,))
        if sql.startswith("SELECT count("):
            column = re.search(r"count\((\w+)\)", sql).group(1)
            return _Row((18000 if self.columns.get(column) == 1536 else 0,))
        if sql.startswith("ALTER"):
            assert self.in_tx, "ALTER must run inside the transaction"
            if self.fail_alter:
                raise RuntimeError("lock timeout")
            if "RENAME COLUMN content_vector TO content_vector_te3s" in sql:
                self.columns["content_vector_te3s"] = self.columns.pop("content_vector")
            elif "ADD COLUMN content_vector" in sql:
                self.columns["content_vector"] = int(re.search(r"vector\((\d+)\)", sql).group(1))
            elif "DROP COLUMN content_vector" in sql:
                self.columns.pop("content_vector")
            elif "RENAME COLUMN content_vector_te3s TO content_vector" in sql:
                self.columns["content_vector"] = self.columns.pop("content_vector_te3s")
            elif sql.startswith("ALTER INDEX"):
                old, new = re.search(r"ALTER INDEX (\S+) RENAME TO (\S+)", sql).groups()
                self.indexes.discard(old)
                self.indexes.add(new)
        return _Row(None)

    def alters(self):
        return [s for s in self.sql if s.startswith("ALTER")]


def test_migration_dry_run_changes_nothing(capsys):
    conn = _MigConn({"content_vector": 1536})
    assert mig.main(["--dim", "1024"], connect=lambda: conn) == 0
    assert conn.alters() == [] and conn.columns == {"content_vector": 1536}
    assert "只看不改" in capsys.readouterr().out


def test_migration_keeps_the_old_vectors_and_adds_an_empty_column():
    conn = _MigConn({"content_vector": 1536}, indexes={mig.INDEX_NAME})
    assert mig.main(["--dim", "1024", "--apply"], connect=lambda: conn) == 0
    assert conn.columns == {"content_vector_te3s": 1536, "content_vector": 1024}
    assert conn.indexes == {mig.OLD_INDEX_NAME}                 # 舊索引跟著舊欄位，名稱改掉
    assert any("lock_timeout" in s for s in conn.sql)
    assert mig.OLD_COLUMN == pg_store.OLD_VECTOR_COLUMN

    before = len(conn.alters())
    assert mig.main(["--dim", "1024", "--apply"], connect=lambda: conn) == 0   # 重跑：已經換過，不再動
    assert len(conn.alters()) == before


def test_migration_rollback_restores_the_old_column():
    conn = _MigConn({"content_vector_te3s": 1536, "content_vector": 1024}, indexes={mig.OLD_INDEX_NAME})
    assert mig.main(["--rollback"], connect=lambda: conn) == 0        # 只看
    assert conn.alters() == []
    assert mig.main(["--rollback", "--apply"], connect=lambda: conn) == 0
    assert conn.columns == {"content_vector": 1536} and conn.indexes == {mig.INDEX_NAME}


def test_migration_refuses_when_the_database_would_overflow():
    conn = _MigConn({"content_vector": 1536}, db_bytes=480 * MB)
    assert mig.main(["--dim", "1024", "--apply"], connect=lambda: conn) == 1
    assert conn.alters() == []


def test_failed_migration_leaves_the_table_as_it_was(capsys):
    conn = _MigConn({"content_vector": 1536}, fail_alter=True)
    assert mig.main(["--dim", "1024", "--apply"], connect=lambda: conn) == 1
    assert conn.columns == {"content_vector": 1536}
    assert "沒有改成" in capsys.readouterr().out


def test_vector_size_estimate_is_about_four_kilobytes_for_bge_m3():
    assert 4100 < mig.vector_bytes(1024) < 4400
    assert 6100 < mig.vector_bytes(1536) < 6400


# ── 校準腳本 embedding_calibration.py ─────────────────────────
cal = _load("embedding_calibration")


def test_calibration_bands_and_suggestion():
    rng = np.random.default_rng(0)
    base = cal.unit(rng.normal(size=(6, 32)))
    K = base                                                    # 知識庫 6 則互不相關的謠言
    orig = base[:3]
    para = cal.unit(base[:3] + rng.normal(size=(3, 32)) * 0.03)          # 改寫句：靠近原文
    questions = cal.unit(rng.normal(size=(4, 32)))
    labels = np.array(["SAFE", "SAFE", "SCAM", "MISINFO"])
    m = cal.measure(K, orig, para, ["甲", "乙", "丙"], questions, labels)
    assert m["para"].min() > 0.8 and len(m["cross"]) == 3 and len(m["safe_nn"]) == 2
    tip = cal.suggest(m)
    assert tip["noise_max"] < tip["suggest"] < tip["para_median"]
    assert abs(tip["suggest"] - (tip["noise_max"] + tip["para_median"]) / 2) <= 0.005 + 1e-9
    tops = cal.top_cross_pairs(orig, ["#1", "#2", "#3"], n=2)
    assert len(tops) == 2 and tops[0][0] >= tops[1][0] and {tops[0][1], tops[0][2]} <= {"#1", "#2", "#3"}
    assert (m["safe_nn"] >= tip["suggest"]).sum() == 0 and (m["cross"] >= tip["suggest"]).sum() == 0
    rows = cal.threshold_rows(m)
    assert [r["t"] for r in rows][:2] == [0.50, 0.51] and rows[0]["para_hit"] == 3


def test_quantile_map_moves_a_value_to_the_same_position():
    old = np.linspace(0.3, 0.8, 101)
    new = np.linspace(0.5, 1.0, 101)
    assert abs(cal.quantile_map(old, new, 0.65) - 0.85) < 0.01
    assert cal.quantile_map(np.array([]), new, 0.65) is None


# ── 重算腳本 reembed_vectors.py 與本機快取 ─────────────────────
re_mod = _load("reembed_vectors")
import embed_cache  # noqa: E402  （reembed_vectors 已把 scripts 加進 sys.path）


def test_embed_text_matches_how_each_row_was_written():
    web = {"raw_content": "網傳吃香蕉配優格會中毒，是真的嗎？", "data_type": "TEXT", "origin": "web", "label_source": "ai"}
    batch = {"raw_content": "網傳吃香蕉配優格會中毒，是真的嗎？", "data_type": "TEXT", "origin": "factcheck_batch",
             "label_source": "rule"}
    url = {"raw_content": "網傳某某新聞全文", "data_type": "URL", "origin": "web", "label_source": "ai"}
    assert re_mod.embed_text(web) == "吃香蕉配優格會中毒"            # 網站文字查證列：和查詢時一樣去掉開頭詞與結尾問句
    assert re_mod.embed_text(batch) == batch["raw_content"]          # 查核資料：原文
    assert re_mod.embed_text(url) == url["raw_content"]
    assert re_mod.embed_text({"raw_content": "   "}) == ""


def _fake_embed(dim, calls):
    def embed(texts):
        calls.append(list(texts))
        return [np.full(dim, (i + 1) / 10, dtype=np.float32) for i, _ in enumerate(texts)], 0
    return embed


def test_cache_only_embeds_new_texts_and_survives_a_restart(tmp_path):
    calls = []
    path = tmp_path / "bge-m3.parquet"
    cache = embed_cache.EmbedCache("bge-m3", path=path, embed=_fake_embed(1024, calls), batch=2, dim=1024)
    assert cache.ensure(["甲", "乙", "丙", "甲", " "]) == 3
    assert calls == [["甲", "乙"], ["丙"]]                           # 去重、空白不送、每批 2 筆
    assert cache.known("乙").shape == (1024,)

    again = embed_cache.EmbedCache("bge-m3", path=path, embed=_fake_embed(1024, calls), batch=2, dim=1024)
    assert again.ensure(["甲", "乙", "丁"]) == 1 and calls[-1] == ["丁"]
    stored = pd.read_parquet(path)
    assert set(stored.columns) == {"key", "vector"}                   # 只存雜湊與向量，不存文字
    assert "甲" not in "".join(stored["key"])


def test_cache_drops_vectors_of_the_wrong_dimension(tmp_path):
    cache = embed_cache.EmbedCache("bge-m3", path=tmp_path / "c.parquet", embed=_fake_embed(1536, []), dim=1024)
    assert cache.ensure(["甲"]) == 0 and cache.known("甲") is None


def test_cache_key_uses_the_text_actually_sent(tmp_path):
    cache = embed_cache.EmbedCache("bge-m3", path=tmp_path / "c.parquet", embed=_fake_embed(4, []), dim=4)
    assert cache.key("長" * 3000) == cache.key("長" * fc.EMBED_MAX_CHARS)


def test_local_reembed_switches_the_seed_to_the_new_dimension(tmp_path, monkeypatch, dim1024):
    kb = tmp_path / "knowledge_base.parquet"
    pd.DataFrame({
        "id": ["a", "b", "none"],
        "raw_content": ["甲謠言", "乙謠言", "沒有向量"],
        "data_type": ["TEXT", "TEXT", "TEXT"],
        "origin": ["factcheck_batch", "web", "web"],
        "label_source": ["rule", "ai", "ai"],
        "content_vector": [np.ones(1536), np.ones(1536), None],
        "verified": [True, True, True],
    }).to_parquet(kb)
    calls = []
    monkeypatch.setattr(re_mod, "KB_PATH", kb)
    monkeypatch.setattr(embed_cache, "CACHE_DIR", tmp_path / "embed_cache")
    monkeypatch.setattr(fc, "embed_batch", _fake_embed(1024, calls))

    assert re_mod.main(["--target", "local"]) == 0 and calls == []          # 只看：不呼叫
    assert re_mod.main(["--target", "local", "--embed"]) == 0              # 只算、存快取
    assert len(calls) == 1 and pd.read_parquet(kb)["content_vector"].map(re_mod.vector_dim).tolist() == [1536, 1536, 0]
    assert re_mod.main(["--target", "local", "--apply"]) == 0              # 快取已有：不再呼叫，直接寫
    assert len(calls) == 1
    after = pd.read_parquet(kb).set_index("id")
    assert len(after.loc["a", "content_vector"]) == 1024 and len(after.loc["b", "content_vector"]) == 1024
    assert after.loc["none", "content_vector"] is None
    assert re_mod.rows_to_fix(pd.read_parquet(kb), 1024).empty
