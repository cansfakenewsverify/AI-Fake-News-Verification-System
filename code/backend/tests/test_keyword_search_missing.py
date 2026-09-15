"""googlesearch 套件缺席時的回歸測試（全離線、零點數）。

B-04 移除依賴後、B-03 移除關鍵字路徑前的過渡期：全新安裝若沒有
googlesearch-python，文字查證不得因「爬取失敗」變成 HTTP 500，
必須照常以使用者原文走到 AI 分析。
"""
import asyncio
import sys

import app.workers.pandas_task_processor as proc
from app.services.crawler import CrawlerService
from app.services.pandas_store import PandasStore
from app.services.task_store import TaskStore

USER_TEXT = "網傳換新式SIM卡要先把舊卡寄回電信公司，否則門號會被停用，是真的嗎"

AI_OK = {
    "is_risk": True, "risk_type": "MISINFO", "category": "Rumor",
    "confidence_score": 0.8, "summary": "不實的換卡謠言",
    "explanation": "電信公司不會要求寄回舊卡。", "sources": [],
}


class FakeAI:
    def __init__(self):
        self.seen_content = None

    def analyze_content(self, content, url=None, context=None, use_web_search=None):
        self.seen_content = content
        return dict(AI_OK)


class FakeVector:
    def vectorize_content(self, text):
        return []  # 向量層停用，逼流程走到爬蟲與 AI


def _block_network(monkeypatch):
    def _no_net(*a, **k):
        raise AssertionError("測試不得發出網路請求")
    monkeypatch.setattr("requests.get", _no_net)
    monkeypatch.setattr("requests.post", _no_net)


def test_keyword_crawl_soft_fails_without_googlesearch(monkeypatch):
    _block_network(monkeypatch)
    monkeypatch.setitem(sys.modules, "googlesearch", None)  # import 會丟 ImportError
    res = asyncio.run(CrawlerService.process_input(USER_TEXT, "keyword"))
    assert res["success"] is True
    assert res["content"] == USER_TEXT
    assert res["similar_news"] == []


def test_text_input_reaches_ai_without_googlesearch(tmp_path, monkeypatch):
    _block_network(monkeypatch)
    monkeypatch.setitem(sys.modules, "googlesearch", None)
    fake_ai = FakeAI()
    monkeypatch.setattr(proc, "TaskStore", lambda: TaskStore(data_dir=str(tmp_path)))
    monkeypatch.setattr(proc, "PandasStore", lambda: PandasStore(data_dir=str(tmp_path)))
    monkeypatch.setattr(proc, "AIService", lambda: fake_ai)
    monkeypatch.setattr(proc, "VectorService", FakeVector)
    # CrawlerService 用真的，驗證它在缺套件時不會讓流程丟「爬取失敗」

    ts = TaskStore(data_dir=str(tmp_path))
    tid = ts.create_task("analyze_text", USER_TEXT)
    result = asyncio.run(proc.process_analysis_task_async(tid, USER_TEXT, "text"))

    assert fake_ai.seen_content == USER_TEXT
    assert result["risk_type"] == "MISINFO"
