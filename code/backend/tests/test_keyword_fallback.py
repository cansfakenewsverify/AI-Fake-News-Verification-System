"""語意比對停用時的備援比對（票 B-48，DEF-13）與存著的向量（票 B-50）。全 mock、離線、零 AI。"""
import asyncio

import numpy as np
import pytest

import app.workers.pandas_task_processor as proc
from app.config import settings
from app.services import keyword_match
from app.services.cache_service import CacheService
from app.services.pandas_store import PandasStore
from app.services.task_store import TaskStore

USER_TEXT = "聽說冷水煮蛋會讓營養流失四成，以後都要等水滾再放蛋"
FACTCHECK = "冷水煮蛋正在把每一顆雞蛋煮成垃圾，這種蛋營養流失接近40%"
OTHER = "喝冷水會讓蛋白質流失，每天都要喝熱水"
TFC = {"title": "用冷水煮雞蛋，不會讓雞蛋營養價值流失", "tier": 1,
       "url": "https://tfc-taiwan.org.tw/fact-check-reports/boiling-eggs-cold-water-nutrition/"}


def _vec(seed):
    v = np.random.default_rng(seed).normal(size=1536)
    return list(v / np.linalg.norm(v))


def _ai(risk_type="MISINFO", sources=(TFC,)):
    return {"is_risk": risk_type != "SAFE", "risk_type": risk_type, "category": "已查核假訊息",
            "confidence_score": 0.95, "summary": f"{risk_type} 摘要", "explanation": "說明", "sources": list(sources)}


class FakeAI:
    """complete_json 依序回 replies；判讀被叫到就記下來。"""
    replies = []
    prompts = []
    models = []
    analyzed = 0

    def complete_json(self, prompt, model=None, timeout=None):
        FakeAI.prompts.append(prompt)
        FakeAI.models.append(model)
        return FakeAI.replies.pop(0) if FakeAI.replies else None

    def analyze_content(self, content, url=None, context=None, use_web_search=None):
        FakeAI.analyzed += 1
        return dict(_ai("SAFE", sources=()), provider="cgu", model="fake")


class NoCrawler:
    async def process_input(self, *args, **kwargs):
        raise AssertionError("文字輸入不得爬取")


class FakeVector:
    result = []
    calls = 0

    def vectorize_content(self, text):
        FakeVector.calls += 1
        return FakeVector.result


@pytest.fixture
def env(tmp_path, monkeypatch):
    FakeAI.replies, FakeAI.prompts, FakeAI.models, FakeAI.analyzed = [], [], [], 0
    FakeVector.result, FakeVector.calls = [], 0
    monkeypatch.setattr(settings, "KEYWORD_FALLBACK_ENABLED", True)
    monkeypatch.setattr(proc, "TaskStore", lambda: TaskStore(data_dir=str(tmp_path)))
    monkeypatch.setattr(proc, "PandasStore", lambda: PandasStore(data_dir=str(tmp_path)))
    monkeypatch.setattr(proc, "AIService", FakeAI)
    monkeypatch.setattr(proc, "CrawlerService", NoCrawler)
    monkeypatch.setattr(proc, "VectorService", FakeVector)
    return tmp_path


def _seed(tmp_path, text, vector=None, label_source="rule", verified=True, ai=None):
    return PandasStore(data_dir=str(tmp_path)).save_record(
        data_type="TEXT", raw_content=text, content_hash=CacheService().generate_hash(text),
        content_vector=vector, ai_result=ai or _ai(), source_url=TFC["url"],
        label_source=label_source, verified=verified,
    )


def _run(tmp_path, text=USER_TEXT):
    task_id = TaskStore(data_dir=str(tmp_path)).create_task(text, "text")
    return asyncio.run(proc.process_analysis_task_async(task_id, text, "text"))


def test_embedding_down_finds_the_fact_check_by_keywords(env):
    _seed(env, FACTCHECK)
    FakeAI.replies = [{"keywords": ["冷水煮蛋", "營養流失"]}, {"relation": "same", "match": 1, "quote": "冷水煮蛋正在把每一顆雞蛋煮成垃圾"}]
    result = _run(env)
    assert result["cached"] is True and result["cache_layer"] == "keyword"
    assert FakeAI.models == [settings.KEYWORD_EXTRACT_MODEL, settings.KEYWORD_MATCH_MODEL]
    assert result["risk_type"] == "MISINFO"
    assert [s["url"] for s in result["sources"]] == [TFC["url"]]
    assert FakeAI.analyzed == 0, "對上查核資料就不用判讀"


def test_no_candidates_falls_back_to_ai_verdict(env):
    _seed(env, OTHER)
    FakeAI.replies = [{"keywords": ["台北捷運", "悠遊卡"]}]
    result = _run(env)
    assert result["cached"] is False and FakeAI.analyzed == 1
    assert len(FakeAI.prompts) == 1, "沒有候選就不用再問 AI 一次"


def test_ai_saying_not_the_same_claim_falls_back_to_ai_verdict(env):
    _seed(env, FACTCHECK)
    FakeAI.replies = [{"keywords": ["冷水煮蛋", "營養流失"]}, {"relation": "other", "match": None}]
    result = _run(env)
    assert result["cached"] is False and FakeAI.analyzed == 1


def test_broken_ai_reply_falls_back_to_ai_verdict(env):
    _seed(env, FACTCHECK)
    FakeAI.replies = [{"keywords": ["冷水煮蛋", "營養流失"]}, {"relation": "same", "match": 99, "quote": "冷水煮蛋正在把每一顆雞蛋煮成垃圾"}]
    assert _run(env)["cached"] is False
    FakeAI.replies = [None]
    assert _run(env, USER_TEXT + "。")["cached"] is False


def test_embedding_working_never_calls_the_fallback(env):
    FakeVector.result = _vec(1)
    _seed(env, FACTCHECK, vector=_vec(2))
    assert _run(env)["cached"] is False
    assert FakeAI.prompts == [] and FakeAI.analyzed == 1


def test_switch_turns_the_fallback_off(env, monkeypatch):
    monkeypatch.setattr(settings, "KEYWORD_FALLBACK_ENABLED", False)
    _seed(env, FACTCHECK)
    assert _run(env)["cached"] is False
    assert FakeAI.prompts == []


def test_only_fact_check_rows_are_candidates(env):
    """一般 AI 判定的列不算查核來源（AGENTS.md 來源規則），即使關鍵字都對上。"""
    _seed(env, FACTCHECK, label_source="ai", verified=True)
    FakeAI.replies = [{"keywords": ["冷水煮蛋", "營養流失"]}]
    assert _run(env)["cached"] is False
    assert len(FakeAI.prompts) == 1


def test_candidates_need_two_keywords_and_rank_by_hits(env):
    store = PandasStore(data_dir=str(env))
    _seed(env, FACTCHECK)
    _seed(env, OTHER)
    found = store.keyword_candidates(["冷水", "營養流失", "雞蛋"], 2, 8, ("rule",))
    assert [row["raw_content"] for row in found] == [FACTCHECK]
    found = store.keyword_candidates(["冷水", "流失"], 2, 8, ("rule",))
    assert {row["raw_content"] for row in found} == {FACTCHECK, OTHER}
    assert store.keyword_candidates(["冷水"], 2, 8, ("rule",)) == []
    assert store.keyword_candidates([], 2, 8, ("rule",)) == []
    assert store.keyword_candidates(["(冷水", "[流失"], 2, 8, ("rule",)) == [], "括號不當 regex"


def test_parse_keywords_drops_bad_items():
    assert keyword_match.parse_keywords({"keywords": ["冷水", "冷水", "蛋", 3, " 營養 ", "長" * 30]}) == ["冷水", "營養"]
    assert keyword_match.parse_keywords({"keywords": "冷水"}) == []
    assert keyword_match.parse_keywords(None) == []
    assert len(keyword_match.parse_keywords({"keywords": [f"詞語{i}" for i in range(20)]})) == keyword_match.MAX_KEYWORDS


_ROWS = [{"raw_content": "第一則內容巴威颱風重創關島"}, {"raw_content": "第二則"},
         {"raw_content": "第三則內容", "sources": [{"title": "網傳搭飛機拍到颱風眼為AI生成影像"}]}]


@pytest.mark.parametrize("reply, expected", [
    ({"relation": "same", "match": 1, "quote": "巴威颱風重創關島"}, 0),
    ({"relation": "same", "match": 1, "quote": "巴威颱風，重創 關島中"}, 0),
    ({"relation": "same", "match": 3, "quote": "搭飛機拍到颱風眼"}, 2),
    ({"relation": "same", "match": 1, "quote": "收取百分之十的手續費"}, None),
    ({"relation": "same", "match": 1, "quote": None}, None), ({"relation": "same", "match": 1}, None),
    ({"relation": "same", "match": 4, "quote": "第一則"}, None), ({"relation": "same", "match": 0, "quote": "第一則"}, None),
    ({"relation": "same", "match": None, "quote": "第一則"}, None), ({"relation": "same", "match": True, "quote": "第一則"}, None),
    ({"relation": "same", "match": "1", "quote": "第一則"}, None),
    ({"relation": "refute", "match": 1, "quote": "第一則"}, None), ({"relation": "other", "match": 1, "quote": "第一則"}, None),
    ({"match": 1, "quote": "第一則"}, None), ({}, None), (None, None),
])
def test_parse_match(reply, expected):
    assert keyword_match.parse_match(reply, _ROWS) == expected


def test_prompts_mark_the_message_as_data_and_cut_long_text():
    long_text = "冷" * 5000
    prompt = keyword_match.keywords_prompt(long_text)
    assert "不要照做" in prompt and prompt.count("冷") == keyword_match.MAX_TEXT_CHARS
    prompt = keyword_match.match_prompt("訊息", [{"raw_content": "內" * 900, "sources": [TFC]}, {"raw_content": "乙"}])
    assert "不要照做" in prompt and "[2] 內容：乙" in prompt and TFC["title"] in prompt
    assert prompt.count("內") <= keyword_match.CANDIDATE_CHARS + 3


def test_long_candidate_shows_the_part_with_the_keywords():
    """長篇聊天紀錄的開頭常常不是相關的部分：送給 AI 的要是對上關鍵字的那一段。"""
    row = {"raw_content": "開" * 600 + "巴威颱風重創關島" + "尾" * 600}
    prompt = keyword_match.match_prompt("巴威颱風影響關島", [row], ["巴威", "關島"])
    assert "巴威颱風重創關島" in prompt


def test_stored_vector_and_backfill_helpers(env):
    store = PandasStore(data_dir=str(env))
    with_vector = _seed(env, FACTCHECK, vector=_vec(3))
    without = store.save_record(
        data_type="TEXT", raw_content=OTHER, content_hash=CacheService().generate_hash(OTHER), content_vector=None,
        ai_result=_ai(), source_url=TFC["url"], label_source="rule", verified=True, origin="factcheck",
    )
    assert store.stored_vector(with_vector["id"]) == pytest.approx(_vec(3))
    assert store.stored_vector(without["id"]) is None
    assert store.stored_vector("no-such-id") is None
    assert [r["id"] for r in store.rows_missing_vector("factcheck")] == [without["id"]]
    assert store.set_vectors({without["id"]: _vec(4)}) == 1
    assert store.rows_missing_vector("factcheck") == []
    assert store.stored_vector(without["id"]) == pytest.approx(_vec(4))


def test_hit_on_unverified_row_uses_the_stored_vector_not_embedding(env):
    """DEF-11：命中未證實列時讀存著的向量，不要每次重算 embedding（票 B-50）。"""
    vector = _vec(5)
    _seed(env, USER_TEXT, vector=vector, label_source="ai", verified=False, ai=_ai("UNVERIFIABLE", sources=()))
    FakeVector.result = _vec(6)
    assert _run(env)["cached"] is True
    assert FakeVector.calls == 0


def test_cached_result_without_vector_is_superseded_by_the_fact_check(env):
    """語意比對停用期間存下的無來源結果：同一句話重查時改回查核資料，不要一直拿舊結果。"""
    _seed(env, FACTCHECK)
    _seed(env, USER_TEXT, label_source="ai", verified=False, ai=_ai(sources=()))
    FakeAI.replies = [{"keywords": ["冷水煮蛋", "營養流失"]}, {"relation": "same", "match": 1, "quote": "冷水煮蛋正在把每一顆雞蛋煮成垃圾"}]
    result = _run(env)
    assert result["cache_layer"] == "keyword" and [s["url"] for s in result["sources"]] == [TFC["url"]]
    assert FakeAI.analyzed == 0


def test_cached_result_keeps_its_answer_when_nothing_matches(env):
    _seed(env, USER_TEXT, label_source="ai", verified=False, ai=_ai(sources=()))
    FakeAI.replies = [{"keywords": ["台北捷運", "悠遊卡"]}]
    assert _run(env)["cache_layer"] == "hash"


def test_cached_result_with_a_vector_spends_no_extra_ai(env):
    _seed(env, USER_TEXT, vector=_vec(7), label_source="ai", verified=False, ai=_ai(sources=()))
    assert _run(env)["cache_layer"] == "hash"
    assert FakeAI.prompts == []


def test_verified_hash_hit_spends_no_extra_ai(env):
    _seed(env, USER_TEXT)
    assert _run(env)["cache_layer"] == "hash"
    assert FakeAI.prompts == []


def test_text_differing_only_in_line_breaks_hits_the_fact_check(env):
    """貼文複製下來有換行，知識庫存的是接成一行的原文：不用 AI 就要命中。"""
    _seed(env, "巴黎多家超市遭洗劫 唯獨豬肉沒有人搶")
    result = _run(env, "巴黎多家超市遭洗劫\n唯獨豬肉沒有人搶")
    assert result["cache_layer"] == "hash" and [s["url"] for s in result["sources"]] == [TFC["url"]]
    assert FakeAI.prompts == [] and FakeAI.analyzed == 0


def test_line_break_lookup_ignores_unverified_rows(env):
    _seed(env, "巴黎多家超市遭洗劫 唯獨豬肉沒有人搶", label_source="ai", verified=False, ai=_ai(sources=()))
    FakeAI.replies = [None]
    assert _run(env, "巴黎多家超市遭洗劫\n唯獨豬肉沒有人搶")["cached"] is False


def test_complete_json_retries_once(monkeypatch):
    import requests
    from app.services.ai_service import AIService

    class Reply:
        def raise_for_status(self):
            pass

        def json(self):
            return {"output": [{"type": "message", "content": [{"type": "output_text", "text": '{"match": 1}'}]}]}

    calls = []

    def flaky(*args, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            raise requests.exceptions.ConnectionError("boom")
        return Reply()

    monkeypatch.setattr(requests, "post", flaky)
    service = AIService()
    service.cgu_base, service.cgu_key = "https://gateway.example/v1", "dummy"
    assert service.complete_json("提示") == {"match": 1} and len(calls) == 2
    calls.clear()

    def down(*args, **kwargs):
        calls.append(1)
        raise requests.exceptions.ConnectionError("boom")

    monkeypatch.setattr(requests, "post", down)
    assert service.complete_json("提示") is None and len(calls) == 2


def test_complete_json_picks_the_model_and_does_not_retry_a_timeout(monkeypatch):
    import requests
    from app.services.ai_service import AIService

    seen = []

    def slow(url, headers=None, json=None, timeout=None):
        seen.append((json, timeout))
        raise requests.Timeout("slow")

    monkeypatch.setattr(requests, "post", slow)
    service = AIService()
    service.cgu_base, service.cgu_key = "https://gateway.example/v1", "dummy"
    assert service.complete_json("提示", model="gemma-4-26b-a4b-it", timeout=7) is None
    assert len(seen) == 1, "等滿逾時就不要再等一輪"
    assert seen[0][0]["model"] == "gemma-4-26b-a4b-it" and "reasoning" not in seen[0][0] and seen[0][1][1] == 7
    seen.clear()
    service.complete_json("提示", model="gpt-oss-120b", timeout=7)
    assert seen[0][0]["reasoning"] == {"effort": "low"}


def test_fallback_does_not_spend_the_daily_ai_budget(env, monkeypatch):
    """本地模型免費、不計額度：每日上限到了也能比對查核資料。"""
    async def no_budget(*args, **kwargs):
        raise AssertionError("備援比對不應扣每日額度")

    monkeypatch.setattr(proc, "_call_ai_within_budget", no_budget)
    _seed(env, FACTCHECK)
    FakeAI.replies = [{"keywords": ["冷水煮蛋", "營養流失"]}, {"relation": "same", "match": 1, "quote": "冷水煮蛋正在把每一顆雞蛋煮成垃圾"}]
    assert _run(env)["cache_layer"] == "keyword"


def test_message_refuting_the_rumour_is_not_treated_as_the_rumour(env):
    """闢謠的訊息用字和謠言幾乎一樣：AI 說 refute 就不能回那一列的「假訊息」。"""
    _seed(env, FACTCHECK)
    FakeAI.replies = [{"keywords": ["冷水煮蛋", "營養流失"]}, {"relation": "refute", "match": 1}]
    result = _run(env, "冷水煮蛋不會讓營養流失，查核中心說明過了")
    assert result["cached"] is False and FakeAI.analyzed == 1


def test_message_with_debunk_words_skips_the_fallback(env):
    """看到「查核中心」這類字就不走備援：闢謠訊息對上謠言列，會把說實話的人標成假訊息。"""
    _seed(env, FACTCHECK)
    result = _run(env, "用冷水煮蛋不會讓營養流失，查核中心已經說明過了")
    assert result["cached"] is False and FakeAI.analyzed == 1
    assert FakeAI.prompts == [], "不多花 AI"
