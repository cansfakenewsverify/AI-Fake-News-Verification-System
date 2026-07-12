"""任務處理器流程測試（全 mock、離線）：
守住「文字輸入的分析對象是使用者原文，不是爬到的網頁」這條 2026-07 修正。
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
    """回傳一個「爬到的查核文章」，內容刻意與使用者訊息不同。"""
    async def process_input(self, data, input_type):
        assert input_type == "keyword"
        return {
            "success": True,
            "url": "https://factcheck.example.com/a1",
            "title": "查核報導標題",
            "content": "這是查核網站文章的全文，不是使用者的訊息。" * 5,
            "date": "2026-07-01",
            "source": "查核站",
            "similar_news": [{"title": "相關報導", "url": "https://news.example.com/b"}],
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


def test_text_input_analyzes_user_text_not_crawled_page(tmp_path, monkeypatch):
    fake_ai = FakeAI()
    monkeypatch.setattr(proc, "TaskStore", lambda: TaskStore(data_dir=str(tmp_path)))
    monkeypatch.setattr(proc, "PandasStore", lambda: PandasStore(data_dir=str(tmp_path)))
    monkeypatch.setattr(proc, "CrawlerService", FakeCrawler)
    monkeypatch.setattr(proc, "AIService", lambda: fake_ai)
    monkeypatch.setattr(proc, "VectorService", FakeVector)

    ts = TaskStore(data_dir=str(tmp_path))
    tid = ts.create_task("analyze_text", USER_TEXT)
    result = asyncio.run(proc.process_analysis_task_async(tid, USER_TEXT, "text"))

    # 分析對象必須是使用者原文（勿退回：舊版會被爬到的網頁全文取代）
    assert fake_ai.seen_content == USER_TEXT
    assert fake_ai.seen_url is None                      # 文字輸入不該掛搜尋結果的網址
    # 爬到的網頁降級為 similar_news 參考脈絡
    urls = [n.get("url") for n in result["similar_news"]]
    assert "https://factcheck.example.com/a1" in urls
    assert "https://news.example.com/b" in urls
    # 結果與快取寫入
    assert result["risk_type"] == "SCAM" and result["cached"] is False
    store = PandasStore(data_dir=str(tmp_path))
    df = store.get_all_records()
    assert len(df) == 1
    assert df.iloc[0]["raw_content"] == USER_TEXT        # 存原文，向量比對才一致
