"""
資料層工廠：依 settings.use_supabase 回傳本機檔案版或 Supabase Postgres 版的 store。

- 預設（STORAGE_BACKEND=local）：PandasStore／TaskStore／AuditStore，行為與直接建構完全相同。
- STORAGE_BACKEND=supabase 且有 SUPABASE_DB_URL：app/services/pg_store.py 的三個 Pg*Store。
  建構時不連線（第一次查詢才連），所以 import 應用程式不需要資料庫。
- 每種 store 在同一行程內是單例；後端設定在測試中切換時以 (種類, 後端) 區分，不會拿錯。

API 模組維持原本的模組層級名稱（analyze.task_store、knowledge._store、admin.kb_store…），
測試照舊用 monkeypatch 換掉它們。
"""
import threading
from typing import Any, Callable, Dict, Tuple

from app.config import settings
from app.services.audit_store import AuditStore
from app.services.pandas_store import PandasStore
from app.services.task_store import TaskStore

_LOCK = threading.RLock()
_INSTANCES: Dict[Tuple[str, str], Any] = {}


def storage_backend() -> str:
    """實際生效的後端名稱：'supabase' 或 'local'。"""
    return "supabase" if settings.use_supabase else "local"


def _pg_store(class_name: str) -> Any:
    # 延後 import：預設的本機模式完全不載入 Postgres 版程式碼
    from app.services import pg_store
    return getattr(pg_store, class_name)()


_BUILDERS: Dict[Tuple[str, str], Callable[[], Any]] = {
    ("knowledge", "local"): PandasStore,
    ("task", "local"): TaskStore,
    ("audit", "local"): AuditStore,
    ("knowledge", "supabase"): lambda: _pg_store("PgKnowledgeStore"),
    ("task", "supabase"): lambda: _pg_store("PgTaskStore"),
    ("audit", "supabase"): lambda: _pg_store("PgAuditStore"),
}


def _get(kind: str) -> Any:
    key = (kind, storage_backend())
    with _LOCK:
        if key not in _INSTANCES:
            _INSTANCES[key] = _BUILDERS[key]()
        return _INSTANCES[key]


def get_knowledge_store() -> Any:
    """三層快取知識庫：PandasStore 或 PgKnowledgeStore。"""
    return _get("knowledge")


def get_task_store() -> Any:
    """非同步任務／結果頁：TaskStore 或 PgTaskStore。"""
    return _get("task")


def get_audit_store() -> Any:
    """管理者覆寫與使用者回饋：AuditStore 或 PgAuditStore。"""
    return _get("audit")


def reset_store_factory() -> None:
    """清掉單例（測試用）。已經被模組層級名稱持有的舊實例不受影響。"""
    with _LOCK:
        _INSTANCES.clear()
