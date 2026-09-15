"""B-17：/api/analyze 改版（result_id、URL 驗證、task_type、錯誤格式）。離線、零 AI 點數。"""
import pytest
from fastapi.testclient import TestClient

import app.api.analyze as analyze_api
import app.workers.pandas_task_processor as proc
from app.main import app
from app.services.task_store import TaskStore

V2_FIELDS = (
    "result_id", "ai_unavailable", "similar_news", "category_label", "label_source",
    "analyzed_at", "verified", "verification_status", "source_tier", "related_discussions",
)


@pytest.fixture
def store(tmp_path, monkeypatch):
    ts = TaskStore(data_dir=str(tmp_path))
    monkeypatch.setattr(analyze_api, "task_store", ts)
    monkeypatch.setattr(analyze_api.settings, "DEMO_MODE", False)
    return ts


@pytest.fixture
def client():
    # 不進 lifespan：不啟動排程、不碰 SQLite
    return TestClient(app)


@pytest.fixture
def enqueued(monkeypatch):
    calls = []
    monkeypatch.setattr(
        analyze_api, "enqueue_analysis_task",
        lambda task_id, data, input_type: calls.append((task_id, data, input_type)),
    )
    return calls


def _assert_validation_error(resp):
    assert resp.status_code == 422
    body = resp.json()
    assert body["code"] == "validation_error"
    assert isinstance(body["detail"], list) and body["detail"]
    assert isinstance(body["message"], str) and body["message"]
    return body


@pytest.mark.parametrize("content", ["", "   "])
def test_text_empty_422_validation_error(client, store, enqueued, content):
    body = _assert_validation_error(client.post("/api/analyze/text", json={"content": content}))
    assert body["message"] == "請先貼上要查證的內容。"
    assert enqueued == []


def test_text_missing_body_422(client, store, enqueued):
    _assert_validation_error(client.post("/api/analyze/text", json={}))


def test_text_over_20000_422(client, store, enqueued):
    body = _assert_validation_error(
        client.post("/api/analyze/text", json={"content": "字" * 20001})
    )
    assert body["message"] == "內容超過 20,000 字，請刪減後再試。"
    assert enqueued == []
    # 剛好 20,000 字仍接受
    ok = client.post("/api/analyze/text", json={"content": "字" * 20000})
    assert ok.status_code == 200


def test_text_returns_result_id_and_origin_web(client, store, enqueued):
    resp = client.post("/api/analyze/text", json={"content": "網傳吃香蕉配優格會中毒"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["result_id"] == body["task_id"]
    task = store.get_task(body["task_id"])
    assert task["task_type"] == "analyze_text"
    assert task["input_type"] == "text" and task["origin"] == "web"
    assert enqueued == [(body["task_id"], "網傳吃香蕉配優格會中毒", "text")]


@pytest.mark.parametrize(
    "content",
    ["not a url", "www.example.com", "ftp://example.com/a", "http://", "https:///path",
     "javascript:alert(1)"],
)
def test_url_invalid_422_invalid_url(client, store, enqueued, content):
    resp = client.post("/api/analyze/url", json={"content": content})
    assert resp.status_code == 422
    body = resp.json()
    assert body["code"] == "invalid_url"
    assert isinstance(body["detail"], str) and body["detail"]
    assert enqueued == []


def test_url_task_type_analyze_url(client, store, enqueued, monkeypatch):
    monkeypatch.setattr(analyze_api.safe_url, "check_url", lambda url: None)
    resp = client.post("/api/analyze/url", json={"content": "  https://www.mygopen.com/2026/09/x.html "})
    assert resp.status_code == 200
    body = resp.json()
    assert body["result_id"] == body["task_id"]
    task = store.get_task(body["task_id"])
    assert task["task_type"] == "analyze_url"
    assert task["input_type"] == "url" and task["origin"] == "web"
    # 不再委派 /text：以 url 型別送進處理器（KB data_type="URL"）
    assert enqueued == [(body["task_id"], "https://www.mygopen.com/2026/09/x.html", "url")]


def _fake_processor_result(task_id):
    return proc._build_result(
        {
            "is_risk": True, "risk_type": "SCAM", "category": "Phishing",
            "confidence_score": 0.93, "summary": "假冒健保署的釣魚連結",
            "explanation": "官方不會以簡訊要求點連結驗證。",
            "sources": [{"title": "165 反詐騙", "url": "https://165.npa.gov.tw/x"}],
        },
        result_id=task_id,
    )


def test_sync_response_has_v2_fields(client, store, monkeypatch):
    seen = {}

    async def fake_process(task_id, input_data, input_type):
        seen.update(task_id=task_id, input_type=input_type)
        return _fake_processor_result(task_id)

    monkeypatch.setattr(proc, "process_analysis_task_async", fake_process)
    resp = client.post("/api/analyze/sync", json={"content": "健保卡即日起停用，請點連結重新驗證"})
    assert resp.status_code == 200
    body = resp.json()
    for key in V2_FIELDS:
        assert key in body, key
        if key != "source_tier":   # source_tier 無來源時可為 null，其餘 §5.4 型別非 null
            assert body[key] is not None, key
    assert isinstance(body["result_id"], str) and body["result_id"]
    assert isinstance(body["label_source"], str) and body["label_source"] == "ai"
    assert isinstance(body["verified"], bool)
    assert "timeline" not in body
    assert body["result_id"] == seen["task_id"]
    assert body["similar_news"] == []
    assert body["ai_unavailable"] is False
    assert body["verification_status"] == "verified" and body["verified"] is True
    assert body["source_tier"] == 1
    assert body["category_label"]
    assert body["analyzed_at"].endswith("+08:00")
    assert all(s["tier"] in (1, 2) for s in body["sources"])
    task = store.get_task(seen["task_id"])
    assert task["origin"] == "web" and task["input_type"] == "text"
    assert seen["input_type"] == "text"


def test_sync_url_input_task_type(client, store, monkeypatch):
    seen = {}

    async def fake_process(task_id, input_data, input_type):
        seen.update(task_id=task_id, input_type=input_type)
        return _fake_processor_result(task_id)

    monkeypatch.setattr(proc, "process_analysis_task_async", fake_process)
    # 離線：SSRF 檢查的 DNS 解析不真的連網
    monkeypatch.setattr(analyze_api.safe_url, "check_url", lambda url: None)
    resp = client.post("/api/analyze/sync", json={"content": "https://example.com/news"})
    assert resp.status_code == 200
    task = store.get_task(seen["task_id"])
    assert task["task_type"] == "analyze_url" and task["input_type"] == "url"


def test_sync_500_hides_exception_text(client, store, monkeypatch):
    async def boom(task_id, input_data, input_type):
        raise RuntimeError("secret upstream detail sk-XXXX")

    monkeypatch.setattr(proc, "process_analysis_task_async", boom)
    resp = client.post("/api/analyze/sync", json={"content": "測試文字"})
    assert resp.status_code == 500
    body = resp.json()
    assert body["code"] == "analysis_failed"
    assert "secret" not in resp.text and "sk-XXXX" not in resp.text


def test_task_status_not_found_code(client, store):
    resp = client.get("/api/analyze/task/not-exist/status")
    assert resp.status_code == 404
    assert resp.json()["code"] == "task_not_found"


def test_analysis_result_model_v2_fields_required_non_null():
    """§5.4：v2 欄位必填且非 null；verification_status 只允許三值。"""
    from pydantic import ValidationError

    base = analyze_api.AnalysisResult.model_json_schema()
    required = set(base.get("required", []))
    for key in V2_FIELDS:
        assert key in required, key
    good = _fake_processor_result("t-1")
    analyze_api.AnalysisResult(**good)
    for key in ("result_id", "category_label", "label_source", "analyzed_at",
                "verification_status", "verified"):
        bad = dict(good)
        bad[key] = None
        with pytest.raises(ValidationError):
            analyze_api.AnalysisResult(**bad)
        bad.pop(key)
        with pytest.raises(ValidationError):
            analyze_api.AnalysisResult(**bad)
    with pytest.raises(ValidationError):
        analyze_api.AnalysisResult(**{**good, "verification_status": "bogus"})


def test_legacy_task_payload_backfills_v2_fields(client, store):
    """v2 前寫入的舊任務缺欄位：/task/{id} 不 500，補保守預設（unverified）。"""
    import json as _json

    tid = store.create_task("analyze_text", "舊任務", input_type="text", origin="web")
    legacy = {"is_risk": False, "risk_type": "SAFE", "category": "Safe",
              "confidence_score": 0.9, "summary": "s", "explanation": "e", "sources": []}
    store.update_task(tid, status="completed", result_data=_json.dumps(legacy))
    resp = client.get(f"/api/analyze/task/{tid}")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["result_id"] == tid
    assert body["verification_status"] == "unverified" and body["verified"] is False
    assert body["label_source"] == "ai" and body["category_label"]
    assert isinstance(body["analyzed_at"], str)


def test_sync_demo_mode_satisfies_model(client, monkeypatch):
    monkeypatch.setattr(analyze_api.settings, "DEMO_MODE", True)
    resp = client.post("/api/analyze/sync", json={"content": "demo 測試"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    for key in V2_FIELDS:
        if key != "source_tier":
            assert body[key] is not None, key
