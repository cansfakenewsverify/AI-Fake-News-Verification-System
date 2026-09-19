"""每日 AI 呼叫次數上限的計數器（FR-14）。離線、零 AI 點數；SQLite 暫存檔。"""
import threading
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, text

import app.services.ai_budget as ai_budget_module
from app.services.ai_budget import TZ_TAIPEI, AiBudget


class Clock:
    def __init__(self, now):
        self.now = now

    def __call__(self):
        return self.now


class ExplodingEngine:
    """任何存取都失敗的 engine；used 記錄有沒有被碰過。"""
    def __init__(self):
        self.used = 0

    def begin(self):
        self.used += 1
        raise RuntimeError("database is down")

    connect = begin


@pytest.fixture
def engine(tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path / 'budget.db'}", connect_args={"check_same_thread": False})
    yield eng
    eng.dispose()


@pytest.fixture
def clock():
    return Clock(datetime(2026, 9, 19, 10, 0, 0, tzinfo=TZ_TAIPEI))


def _cap(monkeypatch, value):
    monkeypatch.setattr(ai_budget_module.settings, "DAILY_AI_CALL_CAP", value)


def test_consumes_up_to_cap_then_refuses(engine, clock, monkeypatch):
    _cap(monkeypatch, 2)
    budget = AiBudget(engine=engine, now=clock)
    assert budget.cap_reached() is False
    assert [budget.try_consume() for _ in range(3)] == [True, True, False]
    assert budget.calls_today() == 2
    assert budget.cap_reached() is True


def test_count_survives_a_new_instance(engine, clock, monkeypatch):
    _cap(monkeypatch, 2)
    assert AiBudget(engine=engine, now=clock).try_consume() is True
    restarted = AiBudget(engine=engine, now=clock)      # 模擬雲端主機重啟
    assert restarted.calls_today() == 1
    assert [restarted.try_consume(), restarted.try_consume()] == [True, False]


def test_new_day_in_taipei_resets_the_count(engine, clock, monkeypatch):
    _cap(monkeypatch, 1)
    budget = AiBudget(engine=engine, now=clock)
    assert [budget.try_consume(), budget.try_consume()] == [True, False]
    clock.now = datetime(2026, 9, 20, 0, 0, 1, tzinfo=TZ_TAIPEI)
    assert budget.cap_reached() is False
    assert budget.try_consume() is True
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT day, calls FROM ai_usage_daily ORDER BY day")).fetchall()
    assert [tuple(r) for r in rows] == [("2026-09-19", 1), ("2026-09-20", 1)]


def test_day_boundary_uses_taipei_time_not_utc(engine, monkeypatch):
    _cap(monkeypatch, 5)
    # 雲端主機的時鐘是 UTC：UTC 9/19 16:30 = 台北 9/20 00:30
    utc_clock = Clock(datetime(2026, 9, 19, 16, 30, 0, tzinfo=timezone.utc))
    budget = AiBudget(engine=engine, now=utc_clock)
    assert budget.today() == "2026-09-20"
    assert budget.seconds_until_reset() == 23 * 3600 + 30 * 60


def test_seconds_until_reset(engine, monkeypatch):
    _cap(monkeypatch, 5)
    late = AiBudget(engine=engine, now=Clock(datetime(2026, 9, 19, 23, 59, 30, tzinfo=TZ_TAIPEI)))
    assert late.seconds_until_reset() == 30
    noon = AiBudget(engine=engine, now=Clock(datetime(2026, 9, 19, 12, 0, 0, tzinfo=TZ_TAIPEI)))
    assert noon.seconds_until_reset() == 12 * 3600


@pytest.mark.parametrize("cap", [0, -1])
def test_disabled_never_touches_the_database(clock, monkeypatch, cap):
    _cap(monkeypatch, cap)
    exploding = ExplodingEngine()
    budget = AiBudget(engine=exploding, now=clock)
    assert all(budget.try_consume() for _ in range(50))
    assert budget.cap_reached() is False and budget.calls_today() == 0
    assert exploding.used == 0


def test_database_failure_still_enforces_cap_in_process(clock, monkeypatch):
    _cap(monkeypatch, 2)
    budget = AiBudget(engine=ExplodingEngine(), now=clock)
    assert [budget.try_consume() for _ in range(3)] == [True, True, False]
    assert budget.cap_reached() is True


def test_snapshot_reports_last_seen_count_without_io(engine, clock, monkeypatch):
    _cap(monkeypatch, 3)
    budget = AiBudget(engine=engine, now=clock)
    assert budget.snapshot() == {"used": None, "cap": 3}      # 還沒讀過資料庫
    budget.try_consume()
    budget.try_consume()
    exploding = ExplodingEngine()
    budget._engine = exploding                                 # 之後任何資料庫存取都會失敗
    assert budget.snapshot() == {"used": 2, "cap": 3}
    clock.now = datetime(2026, 9, 20, 8, 0, 0, tzinfo=TZ_TAIPEI)
    assert budget.snapshot() == {"used": 0, "cap": 3}         # 換日、尚無呼叫
    assert exploding.used == 0


def test_snapshot_is_none_when_disabled(clock, monkeypatch):
    _cap(monkeypatch, 0)
    assert AiBudget(engine=ExplodingEngine(), now=clock).snapshot() is None


def test_concurrent_consumers_never_exceed_cap(engine, clock, monkeypatch):
    _cap(monkeypatch, 5)
    budget = AiBudget(engine=engine, now=clock)
    budget.calls_today()                                  # 先建表，避免 20 條執行緒搶著建
    results = []
    lock = threading.Lock()

    def worker():
        ok = budget.try_consume()
        with lock:
            results.append(ok)

    threads = [threading.Thread(target=worker) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert results.count(True) == 5
    assert budget.calls_today() == 5
