"""
Threads 機器人的狀態存在 Supabase（2026-10-01 起，機器人改在雲端執行）。

啟用條件見 threads_state.use_db：settings.use_supabase、THREADS_MODE 生效為 live，而且呼叫端沒有指定 data_dir
（測試與模擬模式一律用本機檔案）。雲端與負責人電腦同時以 live 執行時共用這份狀態與輪詢鎖，不會重複回覆。

資料表（建立在 pg_store.ensure_pg_schema，全部 idempotent、啟用 RLS 且不建 policy）：
- threads_kv(key, value jsonb, updated_at)
    'state'     等同 data/threads_state.json（已回覆 id、since 游標、backoff、pending_publish、failed…）
    'token'     等同 data/threads_token.json（access_token、obtained_at、expires_at、authorized_at、user_id）
    'poll_lock' 跨機器輪詢鎖 {token, host, pid}；updated_at 超過 stale_seconds 視為殘留、可接手
- threads_replies(seq, id, mention_id, reply_id, record jsonb, replied_at)：等同 data/threads_replies.jsonl；
  id 用 mention_id（同一則提及只記一次，搬遷腳本可重跑）

token 只在這張表與 Render 的資料庫連線裡，不進 log、不回傳給任何 API。
"""
from __future__ import annotations

import json
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

from sqlalchemy import text

from app.services.pg_store import _PgStoreBase

TOKEN_CACHE_SECONDS = 60     # /api/threads/status 每次都會建客戶端：token 讀取快取 60 秒，put('token') 時清掉


class ThreadsPgStore(_PgStoreBase):
    def __init__(self, engine=None) -> None:
        super().__init__(engine)
        self._token_cache: Optional[tuple] = None
        self._cache_lock = threading.Lock()

    # ── key-value ────────────────────────────────────────────────
    def get(self, key: str) -> Optional[Any]:
        if key == "token":
            with self._cache_lock:
                cached = self._token_cache
            if cached is not None and time.monotonic() - cached[0] < TOKEN_CACHE_SECONDS:
                return cached[1]
        with self._connect() as conn:
            row = conn.execute(text("SELECT value FROM threads_kv WHERE key = :k"), {"k": key}).first()
        value = row[0] if row is not None else None
        if isinstance(value, str):      # 驅動沒有把 jsonb 解成物件時
            value = json.loads(value)
        if key == "token":
            with self._cache_lock:
                self._token_cache = (time.monotonic(), value)
        return value

    def put(self, key: str, value: Any) -> None:
        with self._connect() as conn:
            conn.execute(
                text(
                    "INSERT INTO threads_kv (key, value, updated_at) VALUES (:k, CAST(:v AS jsonb), now()) "
                    "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()"
                ),
                {"k": key, "v": json.dumps(value, ensure_ascii=False)},
            )
        if key == "token":
            with self._cache_lock:
                self._token_cache = None

    # ── 回覆紀錄 ─────────────────────────────────────────────────
    def append_reply(self, row: Dict[str, Any]) -> bool:
        """寫一筆回覆紀錄；同一個 mention_id 已有紀錄時略過（回傳 False）。"""
        record_id = str(row.get("mention_id") or "") or f"no-mention-{uuid.uuid4().hex}"
        replied_at = row.get("replied_at")
        with self._connect() as conn:
            result = conn.execute(
                text(
                    "INSERT INTO threads_replies (id, mention_id, reply_id, record, replied_at) "
                    "VALUES (:id, :mention_id, :reply_id, CAST(:record AS jsonb), :replied_at) "
                    "ON CONFLICT (id) DO NOTHING"
                ),
                {
                    "id": record_id,
                    "mention_id": row.get("mention_id"),
                    "reply_id": row.get("reply_id"),
                    "record": json.dumps(row, ensure_ascii=False),
                    "replied_at": _as_utc_naive(replied_at),
                },
            )
        return bool(result.rowcount)

    def replies(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """最新在前；limit=None 為全部。"""
        sql = "SELECT record FROM threads_replies ORDER BY seq DESC"
        params: Dict[str, Any] = {}
        if limit is not None:
            sql += " LIMIT :n"
            params["n"] = int(limit)
        with self._connect() as conn:
            rows = conn.execute(text(sql), params).scalars().all()
        return [json.loads(r) if isinstance(r, str) else r for r in rows]

    def reply_ids(self) -> Set[str]:
        with self._connect() as conn:
            rows = conn.execute(text("SELECT reply_id FROM threads_replies WHERE reply_id IS NOT NULL")).scalars().all()
        return {str(r) for r in rows}

    # ── 跨機器輪詢鎖 ──────────────────────────────────────────────
    def acquire_lock(self, token: str, stale_seconds: float) -> bool:
        """沒有人持有、或持有者超過 stale_seconds 沒放（行程被砍）→ 取得並回 True。單一 SQL，原子。"""
        with self._connect() as conn:
            row = conn.execute(
                text(
                    "INSERT INTO threads_kv (key, value, updated_at) VALUES ('poll_lock', CAST(:v AS jsonb), now()) "
                    "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = now() "
                    "WHERE threads_kv.value IS NULL OR threads_kv.value = 'null'::jsonb "
                    "   OR threads_kv.updated_at < now() - make_interval(secs => :stale) "
                    "RETURNING key"
                ),
                {"v": json.dumps({"token": token}), "stale": float(stale_seconds)},
            ).first()
        return row is not None

    def release_lock(self, token: str) -> bool:
        """只放自己的鎖（token 相符）。"""
        with self._connect() as conn:
            result = conn.execute(
                text(
                    "UPDATE threads_kv SET value = 'null'::jsonb, updated_at = now() "
                    "WHERE key = 'poll_lock' AND value ->> 'token' = :t"
                ),
                {"t": token},
            )
        return bool(result.rowcount)

    def lock_held(self, stale_seconds: float) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                text(
                    "SELECT 1 FROM threads_kv WHERE key = 'poll_lock' AND value IS NOT NULL "
                    "AND value <> 'null'::jsonb AND updated_at >= now() - make_interval(secs => :stale)"
                ),
                {"stale": float(stale_seconds)},
            ).first()
        return row is not None


def _as_utc_naive(value: Any) -> Optional[datetime]:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


_STORE: Optional[ThreadsPgStore] = None
_STORE_LOCK = threading.Lock()


def get_threads_pg() -> ThreadsPgStore:
    global _STORE
    with _STORE_LOCK:
        if _STORE is None:
            _STORE = ThreadsPgStore()
        return _STORE


def set_threads_pg(store: Optional[ThreadsPgStore]) -> None:
    """測試用：換成拋棄式 schema 上的 store，或清掉（None）。"""
    global _STORE
    with _STORE_LOCK:
        _STORE = store
