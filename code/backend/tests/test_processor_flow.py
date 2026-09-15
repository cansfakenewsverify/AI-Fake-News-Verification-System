"""任務處理器流程測試（全 mock、離線）：
守住「文字輸入的分析對象是使用者原文」這條 2026-07 修正，
以及 FR-01「文字輸入不爬、不送搜尋引擎」（B-03，FN-1 例外）。
"""
import asyncio

import app.workers.pandas_task_processor as proc
from app.services.pandas_store import PandasStore
from app.services.task_store import TaskStore

USER_TEXT = "緊急！點擊連結領取政府普發現金六千元，逾期作廢，加LINE客服 gov888 快速申請"

AI_OK = {
    "is_risk": True, "risk_type": "SCAM", "category": "Phishing",
    "confidence_score": 0.9, "summary": "假冒政府釣魚訊息",
    "explanation": "政府不會用私人LINE發放補助。", "sources": [],
}


class FakeCrawler:
    """文字輸入絕不能碰到爬蟲（FR-01）：一被呼叫就失敗。"""
    calls = 0

    async def process_input(self, data, input_type):
        FakeCrawler.calls += 1
        raise AssertionError("文字輸入不得呼叫 crawler.process_input")


class CountingCrawler:
    """只計數、回假成功結果（不拋例外），讓 calls==0 的斷言真正有意義：
    若流程誤呼叫爬蟲，會拿到一份「偷換過的網頁內容」並繼續跑完，只有計數能抓到。"""
    calls = 0

    async def process_input(self, data, input_type):
        CountingCrawler.calls += 1
        return {
            "success": True,
            "url": "https://example.com/crawled",
            "title": "爬到的網頁",
            "content": "這是爬蟲抓回來的網頁內容，不是使用者原文。",
        }


class FakeAI:
    def __init__(self):
        self.seen_content = None
        self.seen_url = "sentinel"

    def analyze_content(self, content, url=None, context=None, use_web_search=None):
        self.seen_content = content
        self.seen_url = url
        self.seen_context = context
        return dict(AI_OK)


class FakeVector:
    def vectorize_content(self, text):
        return []          # 向量層停用，逼流程走到 AI


def _patch(monkeypatch, tmp_path, fake_ai):
    FakeCrawler.calls = 0
    monkeypatch.setattr(proc, "TaskStore", lambda: TaskStore(data_dir=str(tmp_path)))
    monkeypatch.setattr(proc, "PandasStore", lambda: PandasStore(data_dir=str(tmp_path)))
    monkeypatch.setattr(proc, "CrawlerService", FakeCrawler)
    monkeypatch.setattr(proc, "AIService", lambda: fake_ai)
    monkeypatch.setattr(proc, "VectorService", FakeVector)


def _run(tmp_path):
    ts = TaskStore(data_dir=str(tmp_path))
    tid = ts.create_task("analyze_text", USER_TEXT)
    return asyncio.run(proc.process_analysis_task_async(tid, USER_TEXT, "text"))


def test_text_input_analyzes_user_text_not_crawled_page(tmp_path, monkeypatch):
    fake_ai = FakeAI()
    _patch(monkeypatch, tmp_path, fake_ai)
    result = _run(tmp_path)

    # 分析對象必須是使用者原文
    assert fake_ai.seen_content == USER_TEXT
    assert fake_ai.seen_url is None
    # v1.2：similar_news 固定回空（向量近鄰降 P1）
    assert result["similar_news"] == []
    # 結果與快取寫入
    assert result["risk_type"] == "SCAM" and result["cached"] is False
    store = PandasStore(data_dir=str(tmp_path))
    df = store.get_all_records()
    assert len(df) == 1
    assert df.iloc[0]["raw_content"] == USER_TEXT        # 存原文，向量比對才一致


def test_text_input_never_calls_crawler(tmp_path, monkeypatch):
    fake_ai = FakeAI()
    _patch(monkeypatch, tmp_path, fake_ai)
    CountingCrawler.calls = 0
    monkeypatch.setattr(proc, "CrawlerService", CountingCrawler)
    result = _run(tmp_path)

    assert CountingCrawler.calls == 0
    assert fake_ai.seen_content == USER_TEXT
    assert result["risk_type"] == "SCAM"
