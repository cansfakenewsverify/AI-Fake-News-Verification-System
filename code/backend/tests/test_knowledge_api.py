"""B-21：/api/knowledge 分頁、verified 過濾、四格統計、來源只留 Tier 1／2（FR-07、FR-17；測試 FN-8）。

全部離線、零 AI：知識庫是 tmp_path 的 PandasStore（monkeypatch knowledge._store），
並擋下所有 requests 呼叫（Cofacts 分級必須走離線模式）。
"""
import socket

import pandas as pd
import pytest
import requests
from fastapi.testclient import TestClient

import app.api.knowledge as knowledge_api
from app.main import app
from app.services.cache_service import CacheService
from app.services.pandas_store import PandasStore

_LOOPBACK = ("127.0.0.1", "::1", "localhost")


@pytest.fixture
def network_calls(monkeypatch):
    calls = []

    def fake_request(self, method, url, *args, **kwargs):
        calls.append((method, url))
        raise AssertionError(f"knowledge API must not make HTTP calls: {method} {url}")

    real_connect = socket.socket.connect

    def guarded_connect(self, address):
        host = address[0] if isinstance(address, tuple) else address
        if host not in _LOOPBACK:
            calls.append(("socket", address))
            raise AssertionError(f"knowledge API must not open sockets: {address}")
        return real_connect(self, address)

    monkeypatch.setattr(requests.Session, "request", fake_request)
    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    return calls


@pytest.fixture
def store(tmp_path, monkeypatch, network_calls):
    s = PandasStore(data_dir=str(tmp_path))
    monkeypatch.setattr(knowledge_api, "_store", s)
    yield s
    assert network_calls == []


@pytest.fixture
def client():
    return TestClient(app)  # 不進 lifespan：不動真實 SQLite／data


def _add(store, text, *, risk_type="SCAM", sources=(), verified=True, label_source="ai",
         summary="摘要", confidence=0.9, **kwargs):
    ai = {
        "is_risk": risk_type in ("SCAM", "MISINFO"), "risk_type": risk_type, "category": "Test",
        "confidence_score": confidence, "summary": summary, "explanation": "e",
        "sources": list(sources),
    }
    return store.save_record(
        data_type=kwargs.pop("data_type", "TEXT"), raw_content=text,
        content_hash=CacheService.generate_hash(text), ai_result=ai,
        label_source=label_source, verified=verified, **kwargs,
    )


def _list(client, **params):
    resp = client.get("/api/knowledge", params=params)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _ids(body):
    return [r["id"] for r in body["records"]]


# ── FN-8：q 含 regex 特殊字元不得 500，且為字面比對 ──────────────────────
def test_q_with_regex_chars_200(client, store):
    a = _add(store, "限時優惠(今天)[最後]*一天")["id"]
    b = _add(store, "健保卡停用，請點連結重新驗證", summary="假冒健保署 a.b LINE 訊息")["id"]
    _add(store, "未證實(草稿)[x]*", verified=False)

    cases = {
        "(": {a}, "[": {a}, "*": {a}, ")": {a}, "[最後]*": {a}, "(今天)": {a},
        ".": {b}, "健保": {b}, "line": {b},   # summary 也比對、不分大小寫
        ".*": set(), "\\": set(), "(草稿)": set(),  # regex 會全中；未證實列不命中
    }
    for q, expected in cases.items():
        body = _list(client, q=q)
        assert set(_ids(body)) == expected, q
        assert body["total"] == len(expected), q

    # 驗收 curl 的形狀：q=( 且 offset 超過總數 → 200、空頁、total 不變
    body = _list(client, q="(", limit=30, offset=30)
    assert body == {"total": 1, "records": []}


# ── FN-8：offset 分頁不重複不遺漏、排序穩定（created_at desc、id asc）─────────
def test_offset_pagination_no_dup_no_gap(client, store):
    rows = [_add(store, f"分頁測試第{i}筆")["id"] for i in range(7)]
    hidden = [_add(store, f"未證實第{i}筆", verified=False)["id"] for i in range(2)]

    df = store.get_all_records()
    t1, t2, t3 = (pd.Timestamp("2026-09-01 08:00:00"), pd.Timestamp("2026-09-02 08:00:00"),
                  pd.Timestamp("2026-09-03 08:00:00"))
    # 同一時間的列：id 刻意與寫入順序相反，只依 created_at 排序（或不穩定排序）就會錯
    plan = {
        rows[0]: ("kb-3", t1), rows[1]: ("kb-2", t1), rows[2]: ("kb-1", t1),
        rows[3]: ("kb-6", t2), rows[4]: ("kb-5", t2), rows[5]: ("kb-4", t2),
        rows[6]: ("kb-7", t3), hidden[0]: ("kb-8", t3), hidden[1]: ("kb-9", t3),
    }
    df["created_at"] = df["id"].map(lambda i: plan[i][1])
    df["id"] = df["id"].map(lambda i: plan[i][0])
    store._save_knowledge_base(df)
    expected = ["kb-7", "kb-4", "kb-5", "kb-6", "kb-1", "kb-2", "kb-3"]

    seen = []
    for offset in (0, 3, 6, 9):
        body = _list(client, limit=3, offset=offset)
        assert body["total"] == 7
        assert len(body["records"]) == {0: 3, 3: 3, 6: 1, 9: 0}[offset]
        seen += _ids(body)
    assert seen == expected
    assert len(set(seen)) == len(seen) == 7
    assert _ids(_list(client, limit=200)) == expected
    # 重複請求結果一致
    assert _ids(_list(client, limit=3, offset=3)) == expected[3:6]

    # total 是篩選後、分頁前的筆數
    body = _list(client, q="分頁測試", limit=2, offset=4)
    assert body["total"] == 7 and _ids(body) == expected[4:6]


def test_limit_default_30_and_param_validation(client, store):
    for i in range(31):
        _add(store, f"預設筆數第{i}筆")
    body = _list(client)
    assert body["total"] == 31 and len(body["records"]) == 30
    assert len(_list(client, offset=30)["records"]) == 1

    for params in ({"limit": 0}, {"limit": 201}, {"offset": -1}):
        resp = client.get("/api/knowledge", params=params)
        assert resp.status_code == 422, params
        assert resp.json()["code"] == "validation_error"
    assert len(_list(client, limit=200)["records"]) == 31


# ── FR-07 驗收 3：四格加總 = total，只計 verified=true ─────────────────────
def test_stats_four_cells_sum_to_total(client, store):
    verified = ["SCAM", "SCAM", "scam", "MISINFO", "SAFE", "SAFE", "UNKNOWN", "UNVERIFIABLE", None]
    for i, rt in enumerate(verified):
        _add(store, f"統計列{i}", risk_type=rt)
    for i, rt in enumerate(["SCAM", "SCAM", "SAFE"]):
        _add(store, f"未證實統計列{i}", risk_type=rt, verified=False)

    resp = client.get("/api/knowledge/stats")
    assert resp.status_code == 200
    stats = resp.json()
    assert set(stats) == {"total", "by_risk", "counts", "unverified_count"}
    assert stats["total"] == 9
    assert stats["counts"] == {"scam": 3, "misinfo": 1, "safe": 2, "unverifiable": 3}
    assert sum(stats["counts"].values()) == stats["total"]
    assert stats["unverified_count"] == 3
    assert stats["by_risk"]["SCAM"] == 2 and stats["by_risk"]["UNKNOWN"] == 2
    assert sum(stats["by_risk"].values()) == stats["total"]
    assert _list(client)["total"] == stats["total"]


def test_stats_empty_store(client, store):
    assert client.get("/api/knowledge/stats").json() == {
        "total": 0, "by_risk": {},
        "counts": {"scam": 0, "misinfo": 0, "safe": 0, "unverifiable": 0},
        "unverified_count": 0,
    }
    assert _list(client) == {"total": 0, "records": []}


# ── FN-8／FR-17：verified=false 列不出現在列表、不計入 total ───────────────
def test_unverified_rows_invisible_in_list_and_total(client, store):
    v1 = _add(store, "已證實的詐騙訊息", risk_type="SCAM")["id"]
    v2 = _add(store, "已證實的假訊息", risk_type="MISINFO", label_source="rule", verified=None)["id"]
    # 明確 verified=False，與寫入門檻自然得 false（只有 Tier 3 來源）兩種
    u1 = _add(store, "只存在於未證實列的句子", risk_type="SAFE", verified=False)
    u2 = _add(store, "只有部落格來源的判定", risk_type="UNVERIFIABLE", verified=None,
              sources=[{"title": "部落格", "url": "https://blog.example.com/p"}])
    assert u1["verified"] is False and u2["verified"] is False

    body = _list(client, limit=200)
    assert set(_ids(body)) == {v1, v2}
    assert body["total"] == 2
    assert _list(client, q="只存在於未證實列") == {"total": 0, "records": []}
    assert _list(client, q="部落格來源") == {"total": 0, "records": []}
    assert _list(client, risk_type="UNVERIFIABLE") == {"total": 0, "records": []}
    assert _list(client, risk_type="safe") == {"total": 0, "records": []}
    assert _ids(_list(client, risk_type="misinfo")) == [v2]

    stats = client.get("/api/knowledge/stats").json()
    assert stats["total"] == 2 and stats["unverified_count"] == 2
    assert stats["counts"] == {"scam": 1, "misinfo": 1, "safe": 0, "unverifiable": 0}


# ── FR-16：回應 sources 只含 Tier 1／2，每項帶 tier_label ────────────────
def test_sources_only_tier12(client, store):
    sources = [
        {"title": "MyGoPen：健保卡停用是假的", "url": "https://www.mygopen.com/2026/09/a.html"},
        {"title": "查核：網傳喝鹽水治新冠是假的", "url": "https://www.ettoday.net/news/1"},
        {"title": "一般新聞", "url": "https://www.ettoday.net/news/2"},
        {"title": "臉書轉傳", "url": "https://www.facebook.com/groups/x/posts/1"},
        {"title": "Google News 轉址", "url": "https://news.google.com/rss/articles/abc"},
        {"title": "假冒政府網域", "url": "https://gov.tw.evil.com/notice"},
        # 列上帶了錯誤／過期的 tier：非 Cofacts 一律以離線規則重新分級
        {"title": "部落格", "url": "https://blog.example.com/p", "tier": 1},
        # Cofacts：離線查不到回覆 → 只沿用線上分級或清洗腳本寫入的結論（tier 1 / verdict）
        {"title": "Cofacts 有回覆", "url": "https://cofacts.tw/article/has-reply", "tier": 1},
        {"title": "Cofacts verdict", "url": "https://cofacts.g0v.tw/article/v1", "verdict": "RUMOR"},
        {"title": "Cofacts 未分級", "url": "https://cofacts.tw/article/no-tier"},
        {"title": "", "url": ""},
    ]
    rec = _add(store, "來源分級測試", sources=sources)
    _add(store, "只有 Tier 3 但以規則標記", label_source="rule", verified=None,
         sources=[{"title": "臉書", "url": "https://www.facebook.com/x"}])

    body = _list(client, limit=200)
    by_id = {r["id"]: r for r in body["records"]}
    graded = by_id[rec["id"]]["sources"]
    assert [s["url"] for s in graded] == [
        "https://www.mygopen.com/2026/09/a.html",
        "https://www.ettoday.net/news/1",
        "https://cofacts.tw/article/has-reply",
        "https://cofacts.g0v.tw/article/v1",
    ]
    assert [s["tier"] for s in graded] == [1, 2, 1, 1]
    assert [s["tier_label"] for s in graded] == ["查核機構", "媒體查核報導", "查核機構", "查核機構"]
    assert all(None not in s.values() for s in graded)
    assert by_id[rec["id"]]["source_tier"] == 1

    for r in body["records"]:
        assert all(s["tier"] in (1, 2) for s in r["sources"])
        urls = " ".join(s["url"] for s in r["sources"])
        for bad in ("facebook.com", "news.google.com", "evil.com", "blog.example.com", "no-tier"):
            assert bad not in urls
    rule_row = next(r for r in body["records"] if r["label_source"] == "rule")
    assert rule_row["sources"] == [] and rule_row["source_tier"] is None


# ── FR-07 驗收 4、spec §9 隱私：新欄位與 raw_content 前 500 字 ─────────────
def test_record_fields_and_raw_content_truncated(client, store):
    long_text = "謠" * 800
    rec = _add(store, long_text, label_source="gold", verified=None, data_type="URL",
               last_result_id="11111111-2222-3333-4444-555555555555",
               source_url="https://www.mygopen.com/2026/09/b.html", confidence=None,
               summary="Tier 2 only", sources=[{"title": "查核：網傳某某是假的", "url": "https://udn.com/n/1"}])
    plain = _add(store, "沒有結果頁的列", label_source="admin", verified=None)

    body = _list(client, limit=200)
    by_id = {r["id"]: r for r in body["records"]}
    r = by_id[rec["id"]]
    for key in ("id", "data_type", "label_source", "last_result_id", "source_tier",
                "raw_content", "risk_type", "summary", "sources", "hit_count", "created_at"):
        assert key in r
    assert r["raw_content"] == "謠" * 500
    assert r["data_type"] == "URL" and r["label_source"] == "gold"
    assert r["last_result_id"] == "11111111-2222-3333-4444-555555555555"
    assert r["source_tier"] == 2 and [s["tier"] for s in r["sources"]] == [2]
    assert r["confidence_score"] == 0.0   # 缺信心值不讓整頁 500（JSON 無 NaN）
    p = by_id[plain["id"]]
    assert p["last_result_id"] is None and p["label_source"] == "admin"
    assert p["source_tier"] is None and p["sources"] == []
    # 搜尋仍比對完整原文（回應只截前 500 字）
    assert _list(client, q="謠" * 600)["total"] == 1
