"""
NewsFetcher - two-phase trending news pipeline.

KEY INSIGHT: Fact-check articles (MyGoPen/TFC) DEBUNK fake claims.
We extract the ORIGINAL FAKE CLAIM from these articles and index it
in knowledge_base.parquet. When users later submit the same claim,
vector search hits and returns MISINFO with the fact-check URL as proof.

Phase 1: Pull RSS, save trending records, auto-classify trusted sources.
Phase 2: For each fact-check article: extract claim, vectorize, index it.
Phase 3: For unknown sources: AI analyze normally.
"""
import asyncio
import re
from datetime import datetime
from typing import Optional, List

from app.services.search_service import SearchService
from app.services.crawler import CrawlerService
from app.services.ai_service import AIService
from app.services.vector_service import VectorService
from app.services.pandas_store import PandasStore
from app.services.cache_service import CacheService
from app.models.fact_check_record import FactCheckRecord
from app.database_sql import SessionLocal

_crawler = CrawlerService()
_ai = AIService()
_vector = VectorService()
_pandas_store = PandasStore()
_cache_service = CacheService()

_MAX_AI_CALLS_PER_RUN = 10

FACT_CHECK_SOURCES = {
    "mygopen.com":         {"name": "MyGoPen",        "category": "已查核假訊息"},
    "tfc-taiwan.org.tw":   {"name": "台灣事實查核中心", "category": "已查核假訊息"},
    "cofacts.tw":          {"name": "Cofacts",        "category": "已查核假訊息"},
}

SAFE_SOURCES = {
    "cdc.gov.tw":  {"name": "疾管署",  "category": "官方衛教"},
    "gov.tw":      {"name": "政府官方", "category": "官方資訊"},
}


def _detect_source(url: str) -> Optional[dict]:
    if not url:
        return None
    for domain, meta in FACT_CHECK_SOURCES.items():
        if domain in url:
            return {"risk_type": "MISINFO", "is_factcheck": True, **meta}
    for domain, meta in SAFE_SOURCES.items():
        if domain in url:
            return {"risk_type": "SAFE", "is_factcheck": False, **meta}
    return None


def _extract_claim_from_title(title: str) -> str:
    """
    Extract the original false claim from a fact-check article title.

    Examples:
      '【錯誤】網傳紅豆營養比牛肉高？不同類別不應直接比較！專家詳解'
        -> '紅豆營養比牛肉高'
      '【錯誤】吃這些天然「增肌果」比雞蛋厲害？'
        -> '吃這些天然「增肌果」比雞蛋厲害'
    """
    if not title:
        return ""
    s = title.strip()
    # Remove leading tags: 【錯誤】 【部分錯誤】 【假】 【誤導】 等
    s = re.sub(r"^【[^】]+】\s*", "", s)
    # Remove leading "網傳" / "傳言"
    s = re.sub(r"^(網傳|傳言|謠言|流傳)[\s:：]*", "", s)
    # Cut at first sentence delimiter (the rest is usually the fact-check verdict)
    for sep in ["？", "?", "！", "!", "。"]:
        if sep in s:
            s = s.split(sep)[0]
            break
    return s.strip()


_CJK_RE = re.compile(r"[一-鿿]")
# MyGoPen / TFC 標題若帶這些查核標籤，代表已判定為不實
_FALSE_TAG_RE = re.compile(r"^【[^】]*(錯誤|誤導|謠言|不實|易誤解|假)[^】]*】")


def _is_real_claim(claim: str) -> bool:
    """是否為可索引的真實主張：非網址、含中文、不太短、非標籤雲。"""
    c = (claim or "").strip()
    if not c or c.startswith(("http://", "https://")):
        return False
    if len(c) < 6 or not _CJK_RE.search(c):
        return False
    if c.count(",") >= 8 or c.count("，") >= 8:
        return False
    return True


def _title_says_false(title: str) -> bool:
    """標題帶【錯誤/誤導/假…】等查核標籤 → 已判定不實。"""
    return bool(_FALSE_TAG_RE.match((title or "").strip()))


def _is_confirmed_false(item: dict, title: str) -> bool:
    """是否「明確被判定為假訊息」：Cofacts 的 RUMOR 判定，或標題帶查核標籤。"""
    return (item or {}).get("verdict") == "RUMOR" or _title_says_false(title)


def _is_ai_fallback(ai_result: dict) -> bool:
    if not isinstance(ai_result, dict):
        return True
    summary = ai_result.get("summary", "")
    return summary.startswith("AI 分析暫時無法使用") or "服務異常" in summary


def _index_factcheck_claim(url: str, title: str, source_meta: dict):
    """
    Extract the false claim and save it to knowledge_base.parquet
    so future user queries about this claim hit the cache.
    """
    claim = _extract_claim_from_title(title)
    if not _is_real_claim(claim):
        print(f"[NewsFetcher]   not a real claim, skip indexing: {claim[:30]}")
        return

    content_hash = _cache_service.generate_hash(claim)

    # Skip if already indexed
    if _pandas_store.find_by_hash(content_hash):
        print(f"[NewsFetcher]   already indexed: {claim}")
        return

    # Generate embedding for vector search
    try:
        vector = _vector.vectorize_content(claim)
    except Exception as e:
        print(f"[NewsFetcher]   embedding failed: {e}")
        vector = None

    # Build AI-style result pointing to the fact-check article as proof
    ai_result = {
        "is_risk": True,
        "risk_type": "MISINFO",
        "category": source_meta["category"],
        "confidence_score": 0.95,
        "summary": f"此為已被查核的假訊息：「{claim}」",
        "explanation": (
            f"{source_meta['name']} 已對此訊息進行查證，判定為假訊息或誤導內容。"
            f"建議勿轉傳，並參考下方查核來源了解事實。"
        ),
        "sources": [{"title": title, "url": url}],
    }

    _pandas_store.save_record(
        data_type="TEXT",
        raw_content=claim,
        content_hash=content_hash,
        content_vector=vector,
        ai_result=ai_result,
        source_url=url,
    )
    print(f"[NewsFetcher]   ✓ indexed claim: '{claim}' -> MISINFO")


def _save_rss_record(item: dict):
    """Phase 1: insert/update trending record + index claim if fact-check source."""
    db = SessionLocal()
    try:
        url = item["url"]
        title = (item.get("title", "") or "")[:300] or url[:300]
        rss_summary = (item.get("summary", "") or "")[:2000] or None

        rec = db.query(FactCheckRecord).filter_by(source_url=url).first()
        if not rec:
            rec = FactCheckRecord(source_url=url)
            db.add(rec)

        rec.news_title = title
        if not rec.content:
            rec.content = rss_summary
        rec.is_trending = True
        rec.updated_at = datetime.utcnow()

        source = _detect_source(url)
        confirmed_false = _is_confirmed_false(item, title)

        if source and source.get("risk_type") == "SAFE":
            if not rec.risk_type or rec.risk_type in ("PENDING", "UNKNOWN", None):
                rec.risk_type = "SAFE"
                rec.category = source["category"]
                rec.ai_score = 0.9
        elif source and source.get("is_factcheck") and confirmed_false:
            # 只有「明確被判定為假訊息」才標 MISINFO
            rec.risk_type = "MISINFO"
            rec.category = source["category"]
            rec.ai_score = 0.95
            claim = _extract_claim_from_title(title)
            rec.ai_summary = f"[{source['name']}] {claim or title}"
        elif not rec.risk_type:
            rec.risk_type = "PENDING"   # 尚未查證

        db.commit()

        # Phase 2: 只索引「確定不實 + 真實主張」的項目進知識庫
        if source and source.get("is_factcheck") and confirmed_false:
            _index_factcheck_claim(url, title, source)
    finally:
        db.close()


def _get_pending_records(limit: int = 10) -> List[FactCheckRecord]:
    db = SessionLocal()
    try:
        return db.query(FactCheckRecord).filter(
            FactCheckRecord.is_trending == True,
            FactCheckRecord.risk_type.in_(["PENDING", "UNKNOWN", None]),
        ).order_by(FactCheckRecord.created_at.desc()).limit(limit).all()
    finally:
        db.close()


def _cleanup_legacy_strings():
    """
    修正舊資料：
      - 帶查核標籤的假訊息 → MISINFO（並索引）
      - 來自查核站但沒有不實標籤（如 TFC 小考題/標籤雲/純網址）→ 改回 PENDING
      - 舊的「等待 AI 分析」占位字串 → PENDING
    """
    db = SessionLocal()
    try:
        all_trending = db.query(FactCheckRecord).filter(
            FactCheckRecord.is_trending == True
        ).all()
        fixed = 0
        for r in all_trending:
            source = _detect_source(r.source_url)
            title = r.news_title or ""
            if source and source.get("is_factcheck"):
                if _title_says_false(title):
                    r.risk_type = "MISINFO"
                    r.category = source["category"]
                    r.ai_score = 0.95
                    claim = _extract_claim_from_title(title)
                    r.ai_summary = f"[{source['name']}] {claim or title}"
                    _index_factcheck_claim(r.source_url, title, source)
                    fixed += 1
                elif r.risk_type == "MISINFO":
                    # 之前被誤標成假訊息，但其實沒有不實判定 → 退回未查證
                    r.risk_type = "PENDING"
                    r.ai_summary = None
                    fixed += 1
            elif r.ai_summary == "等待 AI 分析":
                r.ai_summary = None
                r.risk_type = "PENDING"
                fixed += 1
        db.commit()
        if fixed:
            print(f"[NewsFetcher] Cleaned/reclassified {fixed} records")
    finally:
        db.close()


async def _analyze_record(url: str, title: str, fallback_content: str) -> str:
    """For unknown sources: crawl + AI analyze."""
    content = fallback_content or ""
    try:
        crawl = await _crawler.process_input(url, "url")
        if crawl.get("success"):
            crawled = crawl.get("content", "") or ""
            if len(crawled) > len(content):
                content = crawled
    except Exception as e:
        print(f"[NewsFetcher] Crawl error: {e}")

    if len(content) < 50:
        return "skip"

    ai_result = None
    try:
        content_hash = _cache_service.generate_hash(url)
        cached = _pandas_store.find_by_hash(content_hash)
        if cached and isinstance(cached.get("ai_analysis"), dict) and not _is_ai_fallback(cached["ai_analysis"]):
            ai_result = cached["ai_analysis"]
        else:
            ai_result = _ai.analyze_content(content, url=url)
            if ai_result and not _is_ai_fallback(ai_result):
                try:
                    _pandas_store.save_record(
                        data_type="URL", raw_content=content,
                        content_hash=content_hash, ai_result=ai_result, source_url=url,
                    )
                except Exception:
                    pass
    except Exception as e:
        print(f"[NewsFetcher] AI error: {e}")

    if not ai_result or _is_ai_fallback(ai_result):
        err = (ai_result or {}).get("explanation", "") if ai_result else ""
        if any(s in err for s in ["503", "429", "RESOURCE_EXHAUSTED", "UNAVAILABLE"]):
            return "ratelimit"
        return "skip"

    db = SessionLocal()
    try:
        rec = db.query(FactCheckRecord).filter_by(source_url=url).first()
        if rec:
            rec.ai_score = ai_result.get("confidence_score")
            rec.ai_summary = ai_result.get("summary")
            rec.risk_type = ai_result.get("risk_type")
            rec.category = ai_result.get("category")
            rec.content = content[:2000]
            rec.updated_at = datetime.utcnow()
            db.commit()
            print(f"[NewsFetcher]   AI done: {rec.risk_type} - {title[:30]}")
    finally:
        db.close()
    return "ok"


async def run_trending_fetch():
    """Full pipeline: RSS fetch + classify + AI analyze. Runs every 6 hours."""
    print(f"\n{'='*60}")
    print(f"[NewsFetcher] Full fetch at {datetime.now():%Y-%m-%d %H:%M}")
    print(f"{'='*60}")

    _cleanup_legacy_strings()

    items = SearchService.fetch_rss_items(num_per_feed=4)
    print(f"[NewsFetcher] RSS items: {len(items)}")
    classified = 0
    for item in items:
        _save_rss_record(item)
        if _detect_source(item.get("url", "")):
            classified += 1
    print(f"[NewsFetcher] {len(items)} saved, {classified} auto-classified")

    await retry_pending_records()


async def retry_pending_records():
    """
    Lightweight job: retry AI analysis on PENDING records.
    Runs every 30 minutes - so 503 failures get retried quickly.
    Also called as part of run_trending_fetch().
    """
    pending = _get_pending_records(limit=_MAX_AI_CALLS_PER_RUN)
    if not pending:
        return

    print(f"[NewsFetcher] Retry job: {len(pending)} pending records")
    ok = 0
    for rec in pending:
        result = await _analyze_record(rec.source_url, rec.news_title or "", rec.content or "")
        if result == "ratelimit":
            print(f"[NewsFetcher] Rate limited, will retry next cycle")
            break
        if result == "ok":
            ok += 1
        await asyncio.sleep(2)
    print(f"[NewsFetcher] Retry done: {ok}/{len(pending)} analyzed")
