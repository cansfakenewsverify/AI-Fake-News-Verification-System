"""
FR-18 cleanup fixtures (D-03, shared with D-04): builds a legacy-shaped
knowledge_base.parquet and a trending SQLite file inside tmp_path.
Offline; never touches code/backend/data.
"""
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

DIM = 4
VEC = [0.1, 0.2, 0.3, 0.4]

# article ids used by the Cofacts mock
COFACTS_REPLIED = "art-replied"
COFACTS_UNANSWERED = "art-unanswered"
COFACTS_FLAKY = "art-flaky"

# Legacy KB columns (the committed seed has none of label_source/source_tier/verified/related_discussions)
LEGACY_KB_COLUMNS = [
    "id", "data_type", "source_url", "raw_content", "data_hash", "content_vector",
    "is_risk", "risk_type", "category", "confidence_score", "summary", "explanation",
    "sources", "ai_analysis", "created_at", "last_accessed_at", "hit_count",
]


def kb_row(row_id: str, raw_content: str, source_url: Optional[str] = None,
           sources: Optional[List[Dict]] = None, vector=VEC, **extra) -> Dict:
    now = datetime(2026, 9, 1, 12, 0)
    srcs = list(sources or [])
    row = {
        "id": row_id,
        "data_type": "TEXT",
        "source_url": source_url,
        "raw_content": raw_content,
        "data_hash": f"hash-{row_id}",
        "content_vector": list(vector) if vector is not None else None,
        "is_risk": True,
        "risk_type": "MISINFO",
        "category": "已查核假訊息",
        "confidence_score": 0.9,
        "summary": f"摘要 {row_id}",
        "explanation": "說明",
        "sources": srcs,
        "ai_analysis": {"risk_type": "MISINFO", "summary": f"摘要 {row_id}", "sources": srcs},
        "created_at": now,
        "last_accessed_at": now,
        "hit_count": 1,
    }
    row.update(extra)
    return row


def default_kb_rows() -> List[Dict]:
    return [
        # rule 1: empty sources + Tier 1 source_url -> backfilled
        kb_row("kb-backfill", "網傳喝熱水可以殺死病毒是假的",
               source_url="https://www.mygopen.com/2026/05/hot-water.html", sources=[]),
        # rule 1: Tier 1 item kept, Tier 3 item moved to related_discussions
        kb_row("kb-mixed", "網傳某超商發放免費禮券需要輸入帳號",
               sources=[
                   {"title": "TFC 查核", "url": "https://tfc-taiwan.org.tw/articles/1"},
                   {"title": "某部落格", "url": "https://blog.example.com/p/2"},
               ]),
        # ai row with only a Tier 3 source -> verified false
        kb_row("kb-tier3-ai", "網傳某地區明天將全面停水一整天",
               sources=[{"title": "一般新聞", "url": "https://news.example.com/a"}]),
        # rule-labelled row with only a Tier 3 source -> must stay verified
        kb_row("kb-rule", "網傳政府將發放每人一萬元補助金",
               sources=[{"title": "一般新聞", "url": "https://news.example.com/b"}],
               label_source="rule"),
        # Cofacts article with a RUMOR reply -> Tier 1
        kb_row("kb-cofacts-yes", "網傳吃香蕉可以預防新冠肺炎感染",
               source_url=f"https://cofacts.tw/article/{COFACTS_REPLIED}",
               sources=[{"title": "Cofacts", "url": f"https://cofacts.tw/article/{COFACTS_REPLIED}"}]),
        # rule 2: Cofacts article without reply -> verified false + no vector
        kb_row("kb-cofacts-no", "網傳某銀行帳戶即將凍結請點連結",
               source_url=f"https://cofacts.tw/article/{COFACTS_UNANSWERED}",
               sources=[{"title": "Cofacts", "url": f"https://cofacts.tw/article/{COFACTS_UNANSWERED}"}]),
        # rule 2: not a real claim (LINE chat fragment)
        kb_row("kb-chat", "ok 好", sources=[]),
        # rule 1 + rule 2 together: Tier 1 source_url (backfilled) but raw_content is a bare
        # URL (not a claim) -> verified stays false; must not re-flag rule 1 on a second pass
        kb_row("kb-tier1-nonclaim", "https://tfc-taiwan.org.tw/top10",
               source_url="https://tfc-taiwan.org.tw/top10", sources=[]),
    ]


def make_kb_parquet(data_dir: Path, rows: Optional[List[Dict]] = None) -> Path:
    data_dir = Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    rows = default_kb_rows() if rows is None else rows
    df = pd.DataFrame(rows)
    for col in LEGACY_KB_COLUMNS:
        if col not in df.columns:
            df[col] = None
    path = data_dir / "knowledge_base.parquet"
    df.to_parquet(path, index=False)
    return path


_TRENDING_SCHEMA = """
CREATE TABLE fact_check_records (
    id VARCHAR(36) NOT NULL PRIMARY KEY,
    source_url VARCHAR(500) UNIQUE,
    news_title VARCHAR(300),
    content TEXT,
    ai_score FLOAT,
    ai_summary TEXT,
    risk_type VARCHAR(20),
    category VARCHAR(50),
    is_trending BOOLEAN,
    created_at DATETIME,
    updated_at DATETIME,
    platform VARCHAR(20),
    post_id VARCHAR(64),
    label_source VARCHAR(10),
    result_id VARCHAR(36),
    verified BOOLEAN,
    source_tier INTEGER
)
"""


def default_trending_rows() -> List[Dict]:
    base = datetime(2026, 9, 1, 8, 0)
    return [
        {"id": "tr-rule", "source_url": "https://www.mygopen.com/2026/09/a.html",
         "news_title": "【錯誤】網傳某訊息", "risk_type": "MISINFO", "category": "已查核假訊息",
         "label_source": "rule", "created_at": base},
        {"id": "tr-google", "source_url": "https://news.google.com/rss/articles/abc",
         "news_title": "某新聞", "risk_type": "UNVERIFIABLE", "category": None,
         "label_source": "ai", "created_at": base + timedelta(hours=1)},
    ]


def trending_rows_d04() -> List[Dict]:
    """D-04 scenarios: Google News resolve + dedupe, unresolved delete, rule/ai/Cofacts backfill."""
    base = datetime(2026, 9, 1, 8, 0)
    return [
        # rule label with a Tier 3 url -> verified true (label, not tier, decides)
        {"id": "tr-rule", "source_url": "https://news.example.com/rule-1",
         "news_title": "網傳某訊息", "risk_type": "MISINFO", "category": "已查核假訊息",
         "label_source": "rule", "verified": 0, "created_at": base},
        # existing TFC row (earliest) that a resolved Google News row duplicates
        {"id": "tr-tfc-early", "source_url": "https://tfc-taiwan.org.tw/articles/999",
         "news_title": "網傳喝檸檬水治癌 查核：錯誤", "risk_type": "MISINFO", "category": None,
         "label_source": "ai", "created_at": base + timedelta(minutes=5)},
        # Google News -> resolves to the same TFC domain + same title (with publisher suffix) -> deduped
        {"id": "tr-google-dup", "source_url": "https://news.google.com/rss/articles/dup",
         "news_title": "網傳喝檸檬水治癌 查核：錯誤 - 台灣事實查核中心", "risk_type": "MISINFO",
         "category": None, "label_source": "ai", "created_at": base + timedelta(hours=2)},
        # Google News -> resolves to a new public url -> overwritten + kept
        {"id": "tr-google-ok", "source_url": "https://news.google.com/rss/articles/ok",
         "news_title": "某地停電原因說明", "risk_type": "SAFE", "category": None,
         "label_source": "ai", "created_at": base + timedelta(hours=3)},
        # Google News that cannot be resolved -> deleted
        {"id": "tr-google-bad", "source_url": "https://news.google.com/rss/articles/bad",
         "news_title": "無法解析的新聞", "risk_type": "UNVERIFIABLE", "category": None,
         "label_source": "ai", "created_at": base + timedelta(hours=4)},
        # Google News that stays on Google -> deleted
        {"id": "tr-google-stay", "source_url": "https://news.google.com/rss/articles/stay",
         "news_title": "仍在 Google 的新聞", "risk_type": "SAFE", "category": None,
         "label_source": "ai", "created_at": base + timedelta(hours=5)},
        # rule-labelled Google News row that stays on Google -> deleted, and the report
        # must count it as a deleted rule row (not hide it behind "被降級：0 筆")
        {"id": "tr-google-rule", "source_url": "https://news.google.com/rss/articles/rule-stay",
         "news_title": "【錯誤】網傳某地淹水照片", "risk_type": "MISINFO", "category": "已查核假訊息",
         "label_source": "rule", "created_at": base + timedelta(hours=5, minutes=30)},
        # ai + Tier 1 url -> verified true
        {"id": "tr-ai-mygopen", "source_url": "https://www.mygopen.com/2026/09/b.html",
         "news_title": "網傳某超商送禮券", "risk_type": "SCAM", "category": None,
         "label_source": "ai", "created_at": base + timedelta(hours=6)},
        # ai + Cofacts with / without reply
        {"id": "tr-cofacts-yes", "source_url": f"https://cofacts.tw/article/{COFACTS_REPLIED}",
         "news_title": "網傳吃香蕉防新冠", "risk_type": "MISINFO", "category": None,
         "label_source": "ai", "created_at": base + timedelta(hours=7)},
        {"id": "tr-cofacts-no", "source_url": f"https://cofacts.tw/article/{COFACTS_UNANSWERED}",
         "news_title": "網傳帳戶凍結", "risk_type": "SCAM", "category": None,
         "label_source": "ai", "verified": 1, "created_at": base + timedelta(hours=8)},
        # PENDING row without a label -> false
        {"id": "tr-pending", "source_url": "https://www.mygopen.com/2026/09/c.html",
         "news_title": "待查證標題", "risk_type": "PENDING", "category": None,
         "label_source": None, "created_at": base + timedelta(hours=9)},
    ]


def make_trending_db(data_dir: Path, rows: Optional[List[Dict]] = None) -> Path:
    data_dir = Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    path = data_dir / "factcheck.db"
    con = sqlite3.connect(path)
    try:
        con.execute(_TRENDING_SCHEMA)
        for r in (default_trending_rows() if rows is None else rows):
            ts = r.get("created_at")
            ts = ts.isoformat(sep=" ") if isinstance(ts, datetime) else ts
            con.execute(
                "INSERT INTO fact_check_records (id, source_url, news_title, risk_type, category, "
                "is_trending, created_at, updated_at, label_source, verified, source_tier) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (r["id"], r.get("source_url"), r.get("news_title"), r.get("risk_type"),
                 r.get("category"), 1, ts, ts,
                 r.get("label_source"), r.get("verified"), r.get("source_tier")),
            )
        con.commit()
    finally:
        con.close()
    return path
