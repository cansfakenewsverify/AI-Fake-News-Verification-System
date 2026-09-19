"""全測試共用設定。"""
import pytest

from app.config import settings


@pytest.fixture(autouse=True)
def _launch_guards_off(monkeypatch):
    """
    上線護欄（每 IP 限速、每日 AI 次數上限）在測試中預設關閉：
    - 限速器是行程內的全域狀態，TestClient 的來源 IP 都一樣，不關的話測試會互相影響；
    - 每日上限的計數存在 SQL 資料庫，不關的話處理器測試會寫到真的 data/factcheck.db。
    要測護欄本身的測試，自己再用 monkeypatch 把數值設回來（見 test_launch_guards.py）。
    """
    monkeypatch.setattr(settings, "RATE_LIMIT_PER_MINUTE", 0)
    monkeypatch.setattr(settings, "RATE_LIMIT_PER_HOUR", 0)
    monkeypatch.setattr(settings, "DAILY_AI_CALL_CAP", 0)
