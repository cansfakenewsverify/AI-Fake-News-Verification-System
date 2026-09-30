"""查核結論同步（FR-23，app/services/factcheck_sync.py）與管理端點 /api/admin/factcheck-sync。

全部離線、零 AI：三個來源的抓取與 embedding 換成假資料，知識庫寫在 tmp_path 的 PandasStore。
收錄規則本身（標籤、主張、Cofacts 判定）另有 test_marking_rules／test_tfc_reports 守著，這裡只驗同步流程：
只寫入可入庫的判定、重跑不重複、被中斷後從剩下的繼續、同一時間只跑一輪、失敗時回報並釋放鎖。
"""
import hashlib

import numpy as np
import pytest
from fastapi.testclient import TestClient

import app.services.ai_service as ai_service
import app.services.factcheck_corpus as fc
import app.services.factcheck_sync as sync
from app.config import settings
from app.main import app
from app.services.cache_service import CacheService
from app.services.pandas_store import PandasStore

TOKEN = "0123456789abcdef0123456789abcdef"

MYGOPEN_TITLES = [
    ("【錯誤】網傳喝檸檬水能殺死癌細胞？醫師：沒有科學根據", "2026-09-20"),
    ("【詐騙】網傳健保卡即日起停用要點連結更新？假冒健保署的釣魚簡訊", "2026-09-28"),
    ("【真】網傳郵局推出新的數位帳戶服務？確有其事", "2026-09-27"),   # SAFE：只供分析，不寫入
]
TFC_ROWS = [
    {"source": "TFC", "kind": "rumor_text", "use": "kb", "label": "MISINFO", "verdict_raw": "false",
     "text": "緊急通知！明天起全台自來水停水三天，請大家趕快儲水並轉傳給親友", "url": "https://tfc-taiwan.org.tw/fact-check-reports/1",
     "title": "網傳「全台停水三天」", "published": "2026-09-25", "requests": None, "scam_topic": False, "extra": ""},
    {"source": "TFC", "kind": "title_claim", "use": "analysis", "label": "SAFE", "verdict_raw": "correct",
     "text": "衛福部宣布十月起擴大流感疫苗公費接種對象", "url": "https://tfc-taiwan.org.tw/fact-check-reports/2",
     "title": "網傳「擴大公費接種」", "published": "2026-09-26", "requests": None, "scam_topic": False, "extra": ""},
]
GATEWAY_MODELS = sorted({settings.CGU_MODEL, settings.CGU_FALLBACK_MODEL, settings.EMBED_MODEL})
COFACTS_RUMOR = "恭喜您獲得週年慶抽獎一等獎，請點以下連結填寫個人資料領取 iPhone 17 一支"


def _node(node_id, text, replies):
    return {"id": node_id, "text": text, "createdAt": "2026-09-22T10:00:00Z", "replyRequestCount": 5,
            "articleCategories": [],
            "articleReplies": [{"positiveFeedbackCount": pos, "negativeFeedbackCount": 0,
                                "reply": {"type": kind, "text": "這是假的抽獎訊息"}} for kind, pos in replies]}


COFACTS_NODES = [
    _node("rumor1", COFACTS_RUMOR, [("RUMOR", 3)]),
    _node("conflict1", "有人說喝熱水可以預防所有的病毒感染，請大家多喝熱水保平安", [("RUMOR", 2), ("NOT_RUMOR", 1)]),
]


def _entry(title, published):
    return {"title": {"$t": title}, "published": {"$t": published + "T08:00:00+08:00"},
            "link": [{"rel": "alternate", "href": "https://www.mygopen.com/2026/09/" + hashlib.md5(title.encode()).hexdigest()[:8]}],
            "summary": {"$t": "查核內容摘要"}}


def _vector(text):
    rng = np.random.default_rng(int(hashlib.sha256(text.encode("utf-8")).hexdigest()[:8], 16))
    v = rng.standard_normal(1536).astype(np.float32)
    return v / np.linalg.norm(v)


@pytest.fixture
def sources(monkeypatch):
    """假來源：記下每次抓取的參數；embedding 以文字決定向量，tokens = 每段 10。"""
    calls = {"mygopen": [], "tfc": [], "cofacts": [], "embed": []}
    missing = set()

    def mygopen_entries(cache=fc.no_cache, max_pages=None):
        calls["mygopen"].append(max_pages)
        return [_entry(t, d) for t, d in MYGOPEN_TITLES]

    def tfc_rows(cache=fc.no_cache, report_pages=None, rumor_pages=None, skipped=None):
        calls["tfc"].append((report_pages, rumor_pages))
        return [dict(r) for r in TFC_ROWS]

    def cofacts_nodes(reply_type, min_requests, limit, cache=fc.no_cache, order="requests"):
        calls["cofacts"].append((reply_type, min_requests, limit, order))
        return COFACTS_NODES if reply_type == "RUMOR" else []

    def embed_batch(texts):
        calls["embed"].append(len(texts))
        return [None if t in missing else _vector(t) for t in texts], 10 * len(texts)

    monkeypatch.setattr(fc, "mygopen_entries", mygopen_entries)
    monkeypatch.setattr(fc, "tfc_rows", tfc_rows)
    monkeypatch.setattr(fc, "cofacts_nodes", cofacts_nodes)
    monkeypatch.setattr(fc, "embed_batch", embed_batch)
    monkeypatch.setattr(ai_service, "gateway_models", lambda timeout=15.0: GATEWAY_MODELS)
    return calls, missing


SEED_TEXT = "既有的查核機構資料：網傳喝醋可以軟化血管"


@pytest.fixture
def empty_store(tmp_path, monkeypatch):
    kb = PandasStore(data_dir=str(tmp_path))
    monkeypatch.setattr(sync, "get_knowledge_store", lambda: kb)
    return kb


@pytest.fixture
def store(empty_store):
    """已經同步過一次的知識庫（有一筆 origin=factcheck_batch 列），recent 不會自動改跑 full。"""
    empty_store.save_record(
        data_type="TEXT", raw_content=SEED_TEXT, content_hash=CacheService.generate_hash(SEED_TEXT),
        content_vector=None, source_url="https://www.mygopen.com/2025/01/seed.html",
        ai_result={"is_risk": True, "risk_type": "MISINFO", "category": "Test", "confidence_score": 0.95,
                   "summary": "摘要", "explanation": "解釋",
                   "sources": [{"title": "MyGoPen", "url": "https://www.mygopen.com/2025/01/seed.html", "tier": 1}]},
        label_source="rule", origin=fc.ORIGIN)
    return empty_store


@pytest.fixture(autouse=True)
def _fresh_status():
    sync._reset("recent")
    sync.STATUS.update(state="idle", mode=None, started_at=None)
    yield
    if sync._lock.locked():
        sync._lock.release()


def _rows(kb):
    """本次同步寫入的列（不含 store fixture 預先放的那一筆）。"""
    df = kb.get_all_records()
    return df[(df["origin"] == fc.ORIGIN) & (df["raw_content"] != SEED_TEXT)] if not df.empty else df


def test_recent_sync_writes_only_fact_checked_false_or_scam_claims(sources, store):
    calls, _ = sources

    result = sync.run_sync("recent", store)

    assert result["state"] == "done" and result["error"] is None
    # MyGoPen 錯誤＋詐騙、TFC 錯誤、Cofacts 獲認可的 RUMOR；SAFE 與判定矛盾的不寫
    assert result["written"] == 4 and result["candidates"] == 4 and result["already_present"] == 0
    assert result["written_by_source"] == {"MyGoPen": 2, "TFC": 1, "Cofacts": 1}
    assert result["tokens"] == 40
    rows = _rows(store)
    assert len(rows) == 4
    assert set(rows["risk_type"]) == {"MISINFO", "SCAM"}
    assert rows["verified"].all() and set(rows["label_source"]) == {"rule"}
    assert "衛福部宣布十月起擴大流感疫苗公費接種對象" not in set(rows["raw_content"])
    # recent：各來源只抓最新一批，Cofacts 依最近回覆排序
    assert calls["mygopen"] == [sync.RECENT["mygopen_pages"]]
    assert calls["tfc"] == [(sync.RECENT["tfc_report_pages"], sync.RECENT["tfc_rumor_pages"])]
    assert calls["cofacts"] == [("RUMOR", sync.COFACTS_MIN_REQUESTS, sync.RECENT["cofacts_limit"], "replied")]


def test_rerun_skips_rows_already_written(sources, store):
    calls, _ = sources
    sync.run_sync("recent", store)
    embedded = sum(calls["embed"])

    again = sync.run_sync("recent", store)

    assert again["state"] == "done" and again["written"] == 0
    assert again["already_present"] == again["candidates"] == 4
    assert sum(calls["embed"]) == embedded   # 已寫入的文字不再付 embedding
    assert len(_rows(store)) == 4


def test_newest_fact_check_gets_latest_created_at(sources, store):
    sync.run_sync("recent", store)
    rows = _rows(store).sort_values("created_at")
    # 依發布日由舊到新寫入：知識庫頁「新到舊」先列出最新的查核結論（MyGoPen 詐騙 09-28 最新）
    assert rows.iloc[-1]["risk_type"] == "SCAM"
    assert rows["created_at"].is_monotonic_increasing and rows["created_at"].is_unique


def test_hash_present_only_as_unverified_row_is_still_written(sources, store):
    h = CacheService.generate_hash(COFACTS_RUMOR)
    store.save_record(data_type="TEXT", raw_content=COFACTS_RUMOR, content_hash=h, content_vector=None,
                      ai_result={"is_risk": True, "risk_type": "SCAM", "category": "Test", "confidence_score": 0.8,
                                 "summary": "尚無查核機構證實", "explanation": "", "sources": []})
    assert store.existing_hashes([h], origin=fc.ORIGIN) == set()

    result = sync.run_sync("recent", store)

    assert result["written"] == 4
    same = store.get_all_records()
    same = same[same["data_hash"] == h]
    # 舊的未證實列留著；新的查核結論列讓 FR-20 回補把重複查詢改回查核結論
    assert sorted(same["verified"].tolist()) == [False, True]


def test_rows_without_vector_are_left_for_the_next_run(sources, store):
    _, missing = sources
    missing.add(COFACTS_RUMOR)

    first = sync.run_sync("recent", store)
    assert first["written"] == 3 and first["written_by_source"] == {"MyGoPen": 2, "TFC": 1}

    missing.clear()
    second = sync.run_sync("recent", store)
    assert second["written"] == 1 and second["written_by_source"] == {"Cofacts": 1}


def test_first_recent_sync_backfills_everything(sources, empty_store):
    calls, _ = sources

    result = sync.run_sync("recent", empty_store)

    assert result["state"] == "done" and result["written"] == 4
    assert result["mode"] == "full" and result["upgraded_from"] == "recent"
    assert calls["mygopen"] == [None] and calls["tfc"] == [(None, None)]
    # 回填過後的 recent 就只抓最新一批
    assert sync.run_sync("recent", empty_store)["upgraded_from"] is None
    assert calls["mygopen"] == [None, sync.RECENT["mygopen_pages"]]


def test_full_sync_scans_every_page(sources, store):
    calls, _ = sources
    assert sync.run_sync("full", store)["state"] == "done"
    assert calls["mygopen"] == [None]
    assert calls["tfc"] == [(None, None)]
    assert calls["cofacts"] == [("RUMOR", sync.COFACTS_MIN_REQUESTS, sync.FULL["cofacts_limit"], "requests")]


def test_failure_is_reported_and_releases_the_lock(sources, store, monkeypatch):
    def broken(texts):
        raise RuntimeError("embedding is not configured")

    monkeypatch.setattr(fc, "embed_batch", broken)
    result = sync.run_sync("recent", store)

    assert result["state"] == "failed"
    assert "embedding is not configured" in result["error"]
    assert not sync.is_running()
    assert _rows(store).empty


def test_only_one_sync_runs_at_a_time(sources, store):
    assert sync._lock.acquire(blocking=False)
    try:
        assert sync.try_start("recent") is False
        assert sync.run_sync("recent", store)["state"] == "idle"   # 沒有開始，只回傳目前狀態
    finally:
        sync._lock.release()


def test_unknown_mode_is_rejected():
    with pytest.raises(ValueError):
        sync.run_sync("everything")
    with pytest.raises(ValueError):
        sync.try_start("everything")


# ── 管理端點 ─────────────────────────────────────────────────────

@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(settings, "ADMIN_TOKEN", TOKEN)
    return TestClient(app)


def test_endpoints_require_admin_token(client, monkeypatch):
    assert client.post("/api/admin/factcheck-sync").status_code == 401
    assert client.get("/api/admin/factcheck-sync").status_code == 401
    monkeypatch.setattr(settings, "ADMIN_TOKEN", "")
    assert client.post("/api/admin/factcheck-sync", headers={"X-Admin-Token": TOKEN}).status_code == 403


def test_post_starts_sync_in_background_and_get_reports_progress(client, sources, store):
    headers = {"X-Admin-Token": TOKEN}

    resp = client.post("/api/admin/factcheck-sync?mode=recent", headers=headers)

    assert resp.status_code == 202 and resp.json() == {"started": True, "mode": "recent"}
    # TestClient 在回應後把背景工作跑完
    status = client.get("/api/admin/factcheck-sync", headers=headers).json()
    assert status["state"] == "done" and status["mode"] == "recent" and status["written"] == 4
    assert len(_rows(store)) == 4


def test_post_while_running_returns_409(client, sources, store):
    assert sync._lock.acquire(blocking=False)
    try:
        resp = client.post("/api/admin/factcheck-sync?mode=full", headers={"X-Admin-Token": TOKEN})
    finally:
        sync._lock.release()
    assert resp.status_code == 409
    assert resp.json()["code"] == "sync_in_progress"
    assert _rows(store).empty


def test_post_rejects_unknown_mode(client):
    resp = client.post("/api/admin/factcheck-sync?mode=everything", headers={"X-Admin-Token": TOKEN})
    assert resp.status_code == 422


def test_one_failing_source_does_not_block_the_others(sources, store, monkeypatch):
    def down(*args, **kwargs):
        raise ConnectionError("cofacts is down")

    monkeypatch.setattr(fc, "cofacts_nodes", down)
    result = sync.run_sync("recent", store)

    assert result["state"] == "done"
    assert result["written_by_source"] == {"MyGoPen": 2, "TFC": 1}
    assert "cofacts is down" in result["source_errors"]["Cofacts"]


def test_all_sources_failing_fails_the_run(sources, store, monkeypatch):
    def down(*args, **kwargs):
        raise ConnectionError("offline")

    for name in ("mygopen_entries", "tfc_rows", "cofacts_nodes"):
        monkeypatch.setattr(fc, name, down)
    result = sync.run_sync("recent", store)

    assert result["state"] == "failed" and "all sources failed" in result["error"]
    assert not sync.is_running()


def test_model_check_reports_models_missing_from_the_gateway(sources, store, monkeypatch):
    monkeypatch.setattr(ai_service, "gateway_models", lambda timeout=15.0: [settings.EMBED_MODEL, "some-new-model"])

    result = sync.run_sync("recent", store)

    # 同步照做（只用 embedding），但狀態裡記下哪些設定的模型已經不在閘道上
    assert result["state"] == "done" and result["written"] == 4
    assert result["model_check"] == {"checked": True,
                                     "missing": [settings.CGU_MODEL, settings.CGU_FALLBACK_MODEL]}


def test_model_check_is_skipped_when_the_list_cannot_be_read(sources, store, monkeypatch):
    monkeypatch.setattr(ai_service, "gateway_models", lambda timeout=15.0: None)
    assert sync.run_sync("recent", store)["model_check"] == {"checked": False, "missing": []}
    monkeypatch.setattr(ai_service, "gateway_models", lambda timeout=15.0: GATEWAY_MODELS)
    assert sync.run_sync("recent", store)["model_check"] == {"checked": True, "missing": []}
