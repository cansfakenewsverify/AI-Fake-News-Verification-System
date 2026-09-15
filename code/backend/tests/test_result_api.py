"""B-16：GET /api/result/{id}、舊結果端點 202、分享文案。離線、零 AI 點數。"""
import json

import pytest
from fastapi.testclient import TestClient

import app.api.analyze as analyze_api
import app.api.result as result_api
import app.workers.pandas_task_processor as proc
from app.main import app
from app.services.task_store import TaskStore
from app.utils import share as share_mod

TOP_KEYS = {
    "id", "status", "input_type", "input_preview", "source_url", "origin", "platform_post",
    "created_at", "completed_at", "ai_unavailable", "result", "error", "share",
}
RESULT_KEYS = {
    "frame_type", "frame_label", "is_risk", "risk_type", "category", "category_label",
    "confidence_score", "confidence_level", "confidence_note", "summary", "explanation",
    "sources", "related_discussions", "verified", "verification_status", "source_tier",
    "similar_news", "cached", "cache_layer", "label_source", "kb_id",
}
BASE_URL = "https://fact.example.app"
TIER1_URL = "https://www.mygopen.com/2026/09/sim.html"
TIER3_URL = "https://www.facebook.com/groups/x/posts/1"


@pytest.fixture
def store(tmp_path, monkeypatch):
    ts = TaskStore(data_dir=str(tmp_path))
    monkeypatch.setattr(analyze_api, "task_store", ts)
    monkeypatch.setattr(result_api, "task_store", ts)
    monkeypatch.setattr(analyze_api.settings, "DEMO_MODE", False)
    monkeypatch.setattr(share_mod.settings, "PUBLIC_BASE_URL", BASE_URL + "/")
    return ts


@pytest.fixture
def client():
    return TestClient(app)


def _complete(ts, task_id, ai_analysis, **kw):
    result = proc._build_result(ai_analysis, result_id=task_id, **kw)
    proc._complete(ts, task_id, result)
    return result


SCAM = {
    "is_risk": True, "risk_type": "SCAM", "category": "Phishing", "confidence_score": 0.93,
    "summary": "假冒健保署的釣魚連結。", "explanation": "官方不會以簡訊要求點連結驗證。",
    "sources": [{"title": "臉書社團轉傳", "url": TIER3_URL},
                {"title": "MyGoPen：健保卡停用是假的", "url": TIER1_URL}],
}


def test_pending_schema(client, store):
    tid = store.create_task("analyze_text", "健保卡即日起停用" * 30, input_type="text")
    resp = client.get(f"/api/result/{tid}")
    assert resp.status_code == 200
    assert resp.headers["cache-control"] == "max-age=5"
    body = resp.json()
    assert set(body) == TOP_KEYS
    assert body["id"] == tid and body["status"] == "pending"
    assert body["input_type"] == "text" and body["origin"] == "web"
    assert len(body["input_preview"]) == 200
    assert body["result"] is None and body["share"] is None and body["error"] is None
    assert body["platform_post"] is None and body["source_url"] is None
    assert body["created_at"].endswith("+08:00") and body["completed_at"] is None

    store.update_task(tid, status="processing")
    body = client.get(f"/api/result/{tid}").json()
    assert body["status"] == "processing" and body["result"] is None and body["share"] is None


def test_completed_schema(client, store):
    tid = store.create_task("analyze_text", "健保卡即日起停用，請點連結重新驗證", input_type="text")
    _complete(store, tid, SCAM)
    resp = client.get(f"/api/result/{tid}")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body) == TOP_KEYS
    assert body["status"] == "completed" and body["error"] is None
    assert body["completed_at"].endswith("+08:00")
    assert body["ai_unavailable"] is False
    res = body["result"]
    assert RESULT_KEYS <= set(res)
    assert res["frame_type"] == "red" and res["frame_label"] == "詐騙警告"
    assert res["verification_status"] == "verified" and res["source_tier"] == 1
    assert all(s["tier"] in (1, 2) for s in res["sources"])
    assert [s["url"] for s in res["related_discussions"]] == [TIER3_URL]
    assert body["share"] == {
        "text": "\U0001F534 AI 判定這則訊息是詐騙：假冒健保署的釣魚連結。查核來源：mygopen.com",
        "url": f"{BASE_URL}/r/{tid}",
    }


def test_url_and_image_preview(client, store):
    url = "https://example.com/" + "a" * 300
    tid = store.create_task("analyze_url", url, input_type="url")
    body = client.get(f"/api/result/{tid}").json()
    assert body["input_preview"] == url and body["source_url"] == url
    tid = store.create_task("analyze_image", "data/uploads/x.png", input_type="image")
    body = client.get(f"/api/result/{tid}").json()
    assert body["input_preview"] == "[圖片]" and body["input_type"] == "image"


def test_failed_schema_no_raw_exception(client, store):
    tid = store.create_task("analyze_text", "測試", input_type="text")
    store.update_task(tid, status="failed", error_message="secret upstream sk-XXXX")
    resp = client.get(f"/api/result/{tid}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "failed"
    assert body["result"] is None and body["share"] is None
    assert body["error"]["code"] == "analysis_failed"
    assert body["error"]["message"]
    assert "secret" not in resp.text and "sk-XXXX" not in resp.text

    # 舊端點同樣不洩漏
    old = client.get(f"/api/analyze/task/{tid}")
    assert old.status_code == 500 and old.json()["code"] == "analysis_failed"
    assert "sk-XXXX" not in old.text


def test_not_found_404_code(client, store):
    resp = client.get("/api/result/not-exist")
    assert resp.status_code == 404
    assert resp.json() == {"detail": "找不到這筆查證", "code": "result_not_found"}


def test_ai_unavailable_grey_share_null(client, store):
    tid = store.create_task("analyze_text", "測試", input_type="text")
    _complete(store, tid, {
        "is_risk": False, "risk_type": "SAFE", "confidence_score": 0,
        "summary": "AI 分析暫時無法使用（額度用盡）", "explanation": "x", "sources": [],
    })
    body = client.get(f"/api/result/{tid}").json()
    assert body["status"] == "completed"
    assert body["ai_unavailable"] is True
    assert body["result"]["frame_type"] == "grey"
    assert body["result"]["frame_label"] == "AI 暫時無法使用"
    assert body["share"] is None


def test_share_text_unverified_red_has_no_source_tail(client, store):
    tid = store.create_task("analyze_text", "某則謠言", input_type="text")
    _complete(store, tid, {
        "is_risk": True, "risk_type": "MISINFO", "category": "Content_Farm",
        "confidence_score": 0.9, "summary": "內容農場改寫的舊聞", "explanation": "x",
        "sources": [{"title": "臉書", "url": TIER3_URL}],
    })
    body = client.get(f"/api/result/{tid}").json()
    assert body["result"]["verification_status"] == "unverified"
    text = body["share"]["text"]
    assert text == "\U0001F534 AI 判定這則訊息是假訊息：內容農場改寫的舊聞"
    assert "查核來源" not in text and "facebook" not in text


def test_task_endpoint_pending_202(client, store):
    tid = store.create_task("analyze_text", "測試", input_type="text")
    resp = client.get(f"/api/analyze/task/{tid}")
    assert resp.status_code == 202
    assert resp.json() == {"task_id": tid, "status": "pending"}
    store.update_task(tid, status="processing")
    resp = client.get(f"/api/analyze/task/{tid}")
    assert resp.status_code == 202 and resp.json()["status"] == "processing"

    _complete(store, tid, SCAM)
    old = client.get(f"/api/analyze/task/{tid}")
    assert old.status_code == 200
    new = client.get(f"/api/result/{tid}").json()["result"]
    old_body = old.json()
    assert set(new) <= set(old_body)
    for key in RESULT_KEYS | {"result_id"}:
        assert old_body[key] == new[key], key

    missing = client.get("/api/analyze/task/not-exist")
    assert missing.status_code == 404 and missing.json()["code"] == "task_not_found"


def test_threads_sim_origin_platform_post(client, store, monkeypatch):
    post = {"platform": "threads", "post_id": "1793001", "permalink":
            "https://www.threads.com/@user/post/C1", "username": "user"}
    tid = store.create_task(
        "analyze_text", "網傳吃香蕉配優格會中毒", input_type="text",
        origin="threads_sim", platform_post=json.dumps(post, ensure_ascii=False),
    )
    resp = client.get(f"/api/result/{tid}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["origin"] == "threads_sim"
    assert body["platform_post"] == post

    # FN-3：web 來源經 /sync 與 /text 各建一筆，/api/result 皆 200
    async def fake_process(task_id, input_data, input_type):
        return _complete(store, task_id, SCAM)

    monkeypatch.setattr(proc, "process_analysis_task_async", fake_process)
    monkeypatch.setattr(analyze_api, "enqueue_analysis_task", lambda *a: None)

    sync_id = client.post("/api/analyze/sync", json={"content": "健保卡停用簡訊"}).json()["result_id"]
    text_id = client.post("/api/analyze/text", json={"content": "健保卡停用簡訊"}).json()["result_id"]
    for rid, status in ((sync_id, "completed"), (text_id, "pending")):
        r = client.get(f"/api/result/{rid}")
        assert r.status_code == 200
        b = r.json()
        assert b["origin"] == "web" and b["platform_post"] is None and b["status"] == status


def _tiered(url, tier):
    return {"title": "t", "url": url, "tier": tier,
            "tier_label": {1: "查核機構", 2: "媒體查核報導", 3: "相關討論（未查證）"}[tier]}


LONG = "字" * 150


@pytest.mark.parametrize(
    "result, key",
    [
        ({"frame_type": "red", "frame_label": "詐騙警告", "risk_type": "SCAM", "is_risk": True,
          "verification_status": "verified"}, "share_text_red_scam"),
        ({"frame_type": "red", "frame_label": "假訊息", "risk_type": "MISINFO", "is_risk": True,
          "verification_status": "verified"}, "share_text_red_misinfo"),
        ({"frame_type": "yellow", "frame_label": "尚待確認", "risk_type": "UNKNOWN",
          "verification_status": "unverified"}, "share_text_yellow"),
        ({"frame_type": "yellow", "frame_label": "無法查證", "risk_type": "UNVERIFIABLE",
          "verification_status": "unverified"}, "share_text_yellow"),
        ({"frame_type": "yellow", "frame_label": "尚無查核機構證實", "risk_type": "SAFE",
          "verification_status": "unverified"}, "share_text_yellow_unverified"),
        ({"frame_type": "green", "frame_label": "查無異常", "risk_type": "SAFE",
          "verification_status": "verified"}, "share_text_green"),
    ],
    ids=["red_scam", "red_misinfo", "yellow_pending", "yellow_unverifiable",
         "yellow_unverified", "green"],
)
@pytest.mark.parametrize("summary", ["簡短摘要", LONG])
def test_share_text_by_frame(store, result, key, summary):
    # Tier 3 網域排第一；另有一個缺 tier 的 Tier 3（離線判定）
    result = dict(result, summary=summary, sources=[
        _tiered(TIER3_URL, 3),
        {"title": "", "url": "https://news.google.com/rss/articles/abc"},
        _tiered("https://tfc-taiwan.org.tw/articles/1", 1),
    ])
    assert share_mod.share_key(result) == key
    share = share_mod.build_share(result, "rid-1")
    text = share["text"]
    assert share["url"] == f"{BASE_URL}/r/rid-1"
    assert len(text) <= 200
    assert "facebook.com" not in text and "news.google.com" not in text

    expected_summary = summary if len(summary) <= 80 else "字" * 79 + "…"
    template = share_mod.SHARE_TEMPLATES[key].replace("{summary}", expected_summary)
    if "{source_domain}" in template:
        template = template.replace("{source_domain}", "tfc-taiwan.org.tw")
    assert text == template


def test_share_tier3_only_red_drops_tail(store):
    result = {"frame_type": "red", "frame_label": "詐騙警告", "risk_type": "SCAM",
              "verification_status": "verified", "summary": "x", "sources": [_tiered(TIER3_URL, 3)]}
    assert share_mod.build_share(result, "r")["text"] == "\U0001F534 AI 判定這則訊息是詐騙：x"


def test_empty_public_base_url_falls_back_to_request_base(client, store, monkeypatch):
    monkeypatch.setattr(share_mod.settings, "PUBLIC_BASE_URL", "")
    tid = store.create_task("analyze_text", "健保卡停用簡訊", input_type="text")
    _complete(store, tid, SCAM)

    # TestClient 的 base URL 為 http://testserver → 絕對網址，不回相對路徑
    share = client.get(f"/api/result/{tid}").json()["share"]
    assert share["url"] == f"http://testserver/r/{tid}"

    # 反向代理：以 X-Forwarded-Proto/Host 組網址
    share = client.get(f"/api/result/{tid}", headers={
        "X-Forwarded-Host": "fact.proxy.app", "X-Forwarded-Proto": "https",
    }).json()["share"]
    assert share["url"] == f"https://fact.proxy.app/r/{tid}"


def test_empty_public_base_url_without_request_share_none(store, monkeypatch, caplog):
    monkeypatch.setattr(share_mod.settings, "PUBLIC_BASE_URL", "")
    result = {"frame_type": "green", "frame_label": "查無異常", "risk_type": "SAFE",
              "verification_status": "verified", "summary": "x", "sources": []}
    # 無 PUBLIC_BASE_URL 也無請求網址 → share=null（絕不回相對 /r/{id}）
    assert share_mod.share_url("r") is None
    assert share_mod.build_share(result, "r") is None
    assert share_mod.build_share(result, "r", "http://h:8000/")["url"] == "http://h:8000/r/r"

    with caplog.at_level("WARNING", logger=share_mod.logger.name):
        assert share_mod.warn_if_public_base_url_missing() is True
    assert "PUBLIC_BASE_URL" in caplog.text

    monkeypatch.setattr(share_mod.settings, "PUBLIC_BASE_URL", BASE_URL)
    assert share_mod.warn_if_public_base_url_missing() is False


def test_share_grey_is_none(store):
    assert share_mod.build_share({"frame_type": "grey", "ai_unavailable": True}, "r") is None
