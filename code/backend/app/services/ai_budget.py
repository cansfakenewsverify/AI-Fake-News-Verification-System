"""
每日 AI 呼叫次數上限（FR-14、spec §5.7 `daily_cap_reached`）。

- 只算「使用者查證管線」真的要呼叫 AI 的次數（app/workers/pandas_task_processor.py 的 L3 與圖片分析）；
  快取命中不算。評測與批次腳本由負責人手動執行，不經過這裡。
- 計數存在 SQL 資料庫（與 app/database_sql.py 同一個 engine：本機 SQLite／雲端 Supabase Postgres），
  所以雲端主機休眠、重啟後不會歸零。一天以 Asia/Taipei 的 00:00 為界。
- try_consume() 是原子操作（UPDATE ... WHERE calls < cap），同時多個請求也不會超過上限。
- 資料庫出錯時退回行程內計數：仍然有上限（每個行程各自算），不會變成無上限。
- snapshot() 不做任何 IO，給 /health 用（健康檢查不能因為資料庫慢而逾時）。
- DAILY_AI_CALL_CAP <= 0 表示關閉（完全不碰資料庫）。
"""
import logging
import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.config import settings

logger = logging.getLogger(__name__)

TZ_TAIPEI = timezone(timedelta(hours=8))
TABLE = "ai_usage_daily"

_CREATE_SQL = (
    f"CREATE TABLE IF NOT EXISTS {TABLE} ("
    "day VARCHAR(10) PRIMARY KEY, "
    "calls INTEGER NOT NULL DEFAULT 0)"
)
_SEED_SQL = f"INSERT INTO {TABLE} (day, calls) VALUES (:day, 0) ON CONFLICT (day) DO NOTHING"
_CONSUME_SQL = f"UPDATE {TABLE} SET calls = calls + 1 WHERE day = :day AND calls < :cap"
_READ_SQL = f"SELECT calls FROM {TABLE} WHERE day = :day"


class AiBudget:
    def __init__(
        self,
        engine: Optional[Engine] = None,
        now: Optional[Callable[[], datetime]] = None,
    ):
        self._engine = engine
        self._now = now or (lambda: datetime.now(TZ_TAIPEI))
        self._ready = False
        self._lock = threading.Lock()
        self._memory: Dict[str, int] = {}
        self._last_seen: Optional[Tuple[str, int]] = None   # (day, calls)：最近一次讀到的資料庫計數

    # ── 時間 ────────────────────────────────────────────────
    def today(self) -> str:
        return self._now().astimezone(TZ_TAIPEI).strftime("%Y-%m-%d")

    def seconds_until_reset(self) -> int:
        """到隔日 00:00（+08:00）還有幾秒，給 Retry-After 用。"""
        now = self._now().astimezone(TZ_TAIPEI)
        midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        return max(1, int((midnight - now).total_seconds()))

    # ── 設定 ────────────────────────────────────────────────
    @property
    def cap(self) -> int:
        return int(settings.DAILY_AI_CALL_CAP or 0)

    @property
    def enabled(self) -> bool:
        return self.cap > 0

    # ── 資料庫 ──────────────────────────────────────────────
    def _db(self) -> Engine:
        if self._engine is None:
            from app.database_sql import engine   # 延後 import：關閉時完全不載入資料庫
            self._engine = engine
        if not self._ready:
            with self._lock:
                if not self._ready:
                    with self._engine.begin() as conn:
                        conn.execute(text(_CREATE_SQL))
                        if self._engine.dialect.name == "postgresql":
                            # 同 pg_store.ensure_pg_schema：Supabase 會把 public 的表經 Data API 開放給
                            # anon 金鑰；啟用 RLS 且不建 policy = 只有後端（資料表擁有者）讀寫得到
                            conn.execute(text(f"ALTER TABLE {TABLE} ENABLE ROW LEVEL SECURITY"))
                    self._ready = True
        return self._engine

    @staticmethod
    def _describe(exc: BaseException) -> str:
        # 連線字串含密碼：錯誤訊息一律經 describe_db_error 遮蔽後才進 log
        from app.database_sql import describe_db_error
        return describe_db_error(exc)

    def _remember(self, day: str, calls: int) -> None:
        with self._lock:
            self._last_seen = (day, calls)

    # ── 對外介面（除 snapshot 外皆為阻塞 IO：async 端點請包 asyncio.to_thread）──
    def calls_today(self) -> int:
        if not self.enabled:
            return 0
        day = self.today()
        try:
            with self._db().connect() as conn:
                row = conn.execute(text(_READ_SQL), {"day": day}).fetchone()
            stored = int(row[0]) if row else 0
            self._remember(day, stored)
        except Exception as e:
            logger.warning("ai_budget: read failed, using in-process count: %s", self._describe(e))
            stored = 0
        with self._lock:
            return max(stored, self._memory.get(day, 0))

    def cap_reached(self) -> bool:
        return self.enabled and self.calls_today() >= self.cap

    def try_consume(self) -> bool:
        """要呼叫 AI 前先扣一次額度；回 False 表示今天已達上限，不可呼叫。"""
        if not self.enabled:
            return True
        day, cap = self.today(), self.cap
        try:
            with self._db().begin() as conn:
                conn.execute(text(_SEED_SQL), {"day": day})
                consumed = conn.execute(text(_CONSUME_SQL), {"day": day, "cap": cap}).rowcount == 1
                row = conn.execute(text(_READ_SQL), {"day": day}).fetchone()
            self._remember(day, int(row[0]) if row else 0)
            return consumed
        except Exception as e:
            logger.warning("ai_budget: consume failed, using in-process count: %s", self._describe(e))
            return self._consume_in_memory(day, cap)

    def _consume_in_memory(self, day: str, cap: int) -> bool:
        with self._lock:
            used = self._memory.get(day, 0)
            if used >= cap:
                return False
            self._memory = {day: used + 1}   # 只留今天
            return True

    def snapshot(self) -> Optional[Dict[str, Any]]:
        """
        /health 的 daily_ai_calls：{used, cap}；關閉時回 None。不讀資料庫——
        used 是這個行程最近一次看到的數字（啟動時 lifespan 會先讀一次；還沒讀到時為 None）。
        """
        if not self.enabled:
            return None
        day = self.today()
        with self._lock:
            seen, memory = self._last_seen, self._memory.get(day, 0)
        if seen is None:
            used = memory or None
        else:
            # 換日後還沒有任何呼叫：今天就是 0
            used = max(seen[1] if seen[0] == day else 0, memory)
        return {"used": used, "cap": self.cap}


ai_budget = AiBudget()
