"""API 冒煙測試：不呼叫 AI 的端點（health / knowledge / threads status）。"""
from fastapi.testclient import TestClient

from app.main import app


def test_health_and_root():
    with TestClient(app) as client:
        assert client.get("/health").json() == {"status": "healthy"}
        assert "version" in client.get("/").json()


def test_knowledge_stats_and_list():
    with TestClient(app) as client:
        stats = client.get("/api/knowledge/stats").json()
        assert "total" in stats and "by_risk" in stats

        data = client.get("/api/knowledge", params={"limit": 5}).json()
        assert "records" in data
        for rec in data["records"]:
            assert "risk_type" in rec
            assert "&nbsp;" not in rec["raw_content"]   # RSS entities 已清乾淨


def test_threads_status_disabled_by_default():
    with TestClient(app) as client:
        st = client.get("/api/threads/status").json()
        assert st["configured"] in (True, False)
        # 手動觸發在未設 token 時要擋下
        if not st["configured"]:
            poll = client.post("/api/threads/poll").json()
            assert poll["started"] is False
