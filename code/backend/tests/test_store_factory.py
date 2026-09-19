"""store_factory 與雲端資料層的選擇邏輯（離線、不需要資料庫、零 AI）。

重點：STORAGE_BACKEND=supabase 時「建構」不得連線（連線延後到第一次查詢），
所以 import 應用程式、建立 store 都不需要 Postgres；CI 沒有資料庫也能跑。
"""
import socket

import pytest

from app import database_sql
from app.config import Settings, settings
from app.services import store_factory
from app.services.audit_store import AuditStore
from app.services.pandas_store import PandasStore
from app.services.task_store import TaskStore

FAKE_PASSWORD = "s3cr3t-pw-never-log"
# 127.0.0.1:9 = discard port，就算真的去連也不會連到任何資料庫
FAKE_URL = f"postgresql://postgres.fakeproject:{FAKE_PASSWORD}@127.0.0.1:9/postgres"


@pytest.fixture(autouse=True)
def _fresh_factory():
    store_factory.reset_store_factory()
    yield
    store_factory.reset_store_factory()
    database_sql.reset_pg_engine()


@pytest.fixture
def no_sockets(monkeypatch):
    """任何連線嘗試都算失敗：用來證明建構階段完全不碰網路。"""
    attempts = []

    def guarded_connect(self, address):
        attempts.append(address)
        raise AssertionError(f"must not connect while constructing stores: {address}")

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    return attempts


@pytest.fixture
def supabase_settings(monkeypatch):
    monkeypatch.setattr(settings, "STORAGE_BACKEND", "supabase")
    monkeypatch.setattr(settings, "SUPABASE_DB_URL", FAKE_URL)


# ── 預設：本機檔案 ───────────────────────────────────────────────
def test_default_backend_is_local(monkeypatch):
    monkeypatch.setattr(settings, "STORAGE_BACKEND", "local")
    assert settings.use_supabase is False
    assert store_factory.storage_backend() == "local"
    assert isinstance(store_factory.get_knowledge_store(), PandasStore)
    assert isinstance(store_factory.get_task_store(), TaskStore)
    assert isinstance(store_factory.get_audit_store(), AuditStore)


def test_settings_class_defaults_are_local():
    fields = Settings.model_fields
    assert fields["STORAGE_BACKEND"].default == "local"
    assert fields["SUPABASE_DB_URL"].default == ""


def test_factory_returns_process_wide_singletons(monkeypatch):
    monkeypatch.setattr(settings, "STORAGE_BACKEND", "local")
    assert store_factory.get_task_store() is store_factory.get_task_store()
    assert store_factory.get_knowledge_store() is store_factory.get_knowledge_store()
    assert store_factory.get_audit_store() is store_factory.get_audit_store()

    first = store_factory.get_task_store()
    store_factory.reset_store_factory()
    assert store_factory.get_task_store() is not first


@pytest.mark.parametrize("backend,url,expected", [
    ("local", "", False),
    ("local", FAKE_URL, False),          # 有網址但沒切後端：仍是本機
    ("supabase", "", False),             # 切了後端但沒網址：退回本機（不讓服務起不來）
    ("supabase", "   ", False),
    ("supabase", FAKE_URL, True),
    (" Supabase ", FAKE_URL, True),      # 大小寫與空白容忍
    ("postgres", FAKE_URL, False),       # 未知值一律本機
])
def test_use_supabase_needs_backend_and_url(monkeypatch, backend, url, expected):
    monkeypatch.setattr(settings, "STORAGE_BACKEND", backend)
    monkeypatch.setattr(settings, "SUPABASE_DB_URL", url)
    assert settings.use_supabase is expected
    assert store_factory.storage_backend() == ("supabase" if expected else "local")


def test_supabase_without_url_falls_back_to_local(monkeypatch):
    monkeypatch.setattr(settings, "STORAGE_BACKEND", "supabase")
    monkeypatch.setattr(settings, "SUPABASE_DB_URL", "")
    assert isinstance(store_factory.get_knowledge_store(), PandasStore)
    assert isinstance(store_factory.get_task_store(), TaskStore)
    assert isinstance(store_factory.get_audit_store(), AuditStore)


# ── supabase：選到 Postgres 版，且建構不連線 ───────────────────────
def test_supabase_selects_pg_stores_without_connecting(supabase_settings, no_sockets):
    from app.services.pg_store import PgAuditStore, PgKnowledgeStore, PgTaskStore

    kb = store_factory.get_knowledge_store()
    tasks = store_factory.get_task_store()
    audit = store_factory.get_audit_store()
    assert isinstance(kb, PgKnowledgeStore)
    assert isinstance(tasks, PgTaskStore)
    assert isinstance(audit, PgAuditStore)
    assert store_factory.get_task_store() is tasks          # 單例
    assert no_sockets == []                                # 完全沒有連線嘗試


def test_backend_switch_does_not_return_stale_singleton(monkeypatch):
    from app.services.pg_store import PgTaskStore

    monkeypatch.setattr(settings, "STORAGE_BACKEND", "local")
    local_store = store_factory.get_task_store()
    monkeypatch.setattr(settings, "STORAGE_BACKEND", "supabase")
    monkeypatch.setattr(settings, "SUPABASE_DB_URL", FAKE_URL)
    assert isinstance(store_factory.get_task_store(), PgTaskStore)
    monkeypatch.setattr(settings, "STORAGE_BACKEND", "local")
    assert store_factory.get_task_store() is local_store


def test_pg_stores_expose_the_local_public_interface():
    """Postgres 版必須有本機版的每一個公開方法（呼叫端不分後端）。"""
    from app.services.pg_store import PgAuditStore, PgKnowledgeStore, PgTaskStore

    def public(cls):
        return {n for n in vars(cls) if not n.startswith("_") and callable(getattr(cls, n))}

    assert public(PandasStore) <= public(PgKnowledgeStore)
    assert public(TaskStore) <= public(PgTaskStore)
    assert public(AuditStore) <= public(PgAuditStore)


# ── engine：延後連線、改寫 scheme、不洩漏密碼 ───────────────────────
def test_build_pg_engine_is_lazy_and_uses_psycopg(no_sockets):
    engine = database_sql.build_pg_engine(FAKE_URL)
    try:
        assert engine.dialect.name == "postgresql"
        assert engine.url.drivername == "postgresql+psycopg"
        assert engine.pool.size() == 3
        assert engine.pool._max_overflow == 2
        assert engine.pool._recycle == 300
        assert engine.pool._pre_ping is True
        assert FAKE_PASSWORD not in repr(engine)
        assert FAKE_PASSWORD not in str(engine.url)
        assert no_sockets == []
    finally:
        engine.dispose()


def test_get_pg_engine_is_lazy_under_local_backend(monkeypatch, no_sockets):
    """migrate_to_supabase.py 的情境：後端是 local，仍能拿到（尚未連線的）Postgres engine。"""
    monkeypatch.setattr(settings, "SUPABASE_DB_URL", FAKE_URL)
    assert database_sql.engine.dialect.name == "sqlite"     # 模組 engine 不受影響
    engine = database_sql.get_pg_engine()
    assert engine.dialect.name == "postgresql"
    assert database_sql.get_pg_engine() is engine
    assert no_sockets == []


@pytest.mark.parametrize("schema,expected", [
    ("public", 'SET search_path TO "public", "extensions"'),
    ("test_ab12cd34", 'SET search_path TO "test_ab12cd34", "extensions", "public"'),
])
def test_search_path_always_includes_extensions(schema, expected):
    assert database_sql._search_path_sql(schema) == expected


@pytest.mark.parametrize("schema", ["", "Public", "a-b", 'x"; DROP SCHEMA public; --', "1abc", "a b"])
def test_build_pg_engine_rejects_unsafe_schema_names(schema):
    with pytest.raises(ValueError):
        database_sql.build_pg_engine(FAKE_URL, schema=schema)


def test_build_pg_engine_errors_never_echo_the_url(monkeypatch):
    with pytest.raises(RuntimeError) as empty:
        database_sql.build_pg_engine("")
    assert "SUPABASE_DB_URL" in str(empty.value)

    for bad in (f"not a url {FAKE_PASSWORD}", f"mysql://u:{FAKE_PASSWORD}@127.0.0.1/db"):
        with pytest.raises(RuntimeError) as err:
            database_sql.build_pg_engine(bad)
        assert FAKE_PASSWORD not in str(err.value)
        assert err.value.__cause__ is None and err.value.__suppress_context__


def test_describe_db_error_masks_credentials():
    exc = RuntimeError(f'connection to "{FAKE_URL}" failed: password {FAKE_PASSWORD} rejected\nline two')
    message = database_sql.describe_db_error(exc, FAKE_URL)
    assert FAKE_PASSWORD not in message
    assert FAKE_URL not in message
    assert message.startswith("RuntimeError: ")
    assert "line two" not in message            # 只留第一行

    encoded = "postgresql://u:p%40ss%2Fword@127.0.0.1:9/postgres"
    message = database_sql.describe_db_error(RuntimeError("auth failed for p@ss/word (p%40ss%2Fword)"), encoded)
    assert "p@ss/word" not in message and "p%40ss%2Fword" not in message


# ── 處理器與 Threads 機器人：本機模式沿用既有的測試接縫 ───────────────
def test_processor_keeps_module_level_store_seams():
    import app.workers.pandas_task_processor as proc

    assert proc.TaskStore is TaskStore
    assert proc.PandasStore is PandasStore


def test_threads_bot_context_uses_local_task_store_by_default(tmp_path, monkeypatch):
    from app.workers import threads_bot

    monkeypatch.setattr(settings, "STORAGE_BACKEND", "local")

    class Client:
        def reply_to(self, mention_id, text):
            return "r"

    ctx = threads_bot.PollContext(Client(), {}, "sim", data_dir=tmp_path)
    assert isinstance(ctx.task_store, TaskStore)
    assert ctx.task_store.data_dir == tmp_path


def test_threads_bot_context_uses_cloud_task_store(supabase_settings, no_sockets, tmp_path):
    from app.services.pg_store import PgTaskStore
    from app.workers import threads_bot

    class Client:
        def reply_to(self, mention_id, text):
            return "r"

    assert isinstance(threads_bot.PollContext(Client(), {}, "sim").task_store, PgTaskStore)
    # 明確指定 data_dir（sim 測試／腳本）仍用該目錄的本機檔案
    explicit = threads_bot.PollContext(Client(), {}, "sim", data_dir=tmp_path).task_store
    assert isinstance(explicit, TaskStore)
    assert no_sockets == []
