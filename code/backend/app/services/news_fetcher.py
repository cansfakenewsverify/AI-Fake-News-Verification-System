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
import sys
from datetime import datetime
from typing import Optional, List

from app.services.search_service import SearchService
from app.services.crawler import CrawlerService
from app.services.ai_service import AIService
from app.services.vector_service import VectorService
from app.services.store_factory import get_knowledge_store
from app.services.cache_service import CacheService
from app.utils.verdict import is_fallback
from app.utils.source_tier import tier_of, grade_sources
from app.utils.url_validator import filter_valid_sources
from app.models.fact_check_record import FactCheckRecord
from app.database_sql import SessionLocal

_crawler = CrawlerService()
_ai = AIService()
_vector = VectorService()
# 本機 PandasStore 或 Supabase 的 PgKnowledgeStore；測試以 monkeypatch 換掉 _pandas_store
_pandas_store = get_knowledge_store()
_cache_service = CacheService()


def _print(msg: str) -> None:
    """cp950 安全輸出：RSS 標題/主張是外部文字，可能含 ▶ 等非 Big5 字元，
    直接 print 會 UnicodeEncodeError 把整輪抓取炸掉（2026-07 實際發生）。"""
    try:
        print(msg)
    except UnicodeEncodeError:
        enc = getattr(sys.stdout, "encoding", None) or "utf-8"
        print(msg.encode(enc, errors="replace").decode(enc, errors="replace"))

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

# 主流媒體「轉載查核結果」的標題判定（ETtoday/華視/三立…報導 TFC/警方查核）。
# 需同時命中「查核語境」與「不實判定詞」才算，避免把一般報導誤標
# （例：「警方成立闢謠專區」只有語境詞 → 不算；「高雄警急闢謠：那是假的」→ 算）。
# 這條規則解決同一謠言在不同媒體報導下被 AI 判成一邊 MISINFO 一邊 SAFE 的不一致。
_DEBUNK_CONTEXT_RE = re.compile(r"(事實查核|查核|闢謠|澄清|媒體識讀|網傳|瘋傳|流傳)")
_DEBUNK_VERDICT_RE = re.compile(r"(不實|誤導|謠言|假的|假消息|假訊息|錯假|過度誇大|錯誤|全錯|莫信|勿信|打臉)")


def _title_indicates_debunk(title: str) -> bool:
    """標題明示「這是查核報導且結論為不實」→ 可確定性標 MISINFO（判定對象是被查核的主張）。"""
    t = (title or "").strip()
    return bool(_DEBUNK_CONTEXT_RE.search(t) and _DEBUNK_VERDICT_RE.search(t))


# 給 AI 分析新聞報導時的補充指示：判定對象是「被流傳的主張」不是「報導行為」。
# 沒有這段時，AI 對查核報導會不一致（有時判謠言 MISINFO、有時判報導本身 SAFE）。
_NEWS_ANALYSIS_GUIDANCE = (
    "這是自動抓取的新聞報導。請判定「報導中被流傳的主張」而非「報導行為本身」："
    "若內容是查核/闢謠報導（指出某流傳說法不實、誤導或過度誇大）→ risk_type 填 MISINFO，"
    "summary 填被查核的原始不實主張；"
    "若查核結論是「說法為真」，或內容是一般正確新聞、官方公告、反詐宣導、犯罪偵破報導"
    "（沒有不實主張被當真流傳）→ risk_type 填 SAFE。"
)


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


def _index_factcheck_claim(url: str, title: str, source_meta: dict):
    """
    Extract the false claim and save it to knowledge_base.parquet
    so future user queries about this claim hit the cache.
    """
    claim = _extract_claim_from_title(title)
    if not _is_real_claim(claim):
        _print(f"[NewsFetcher]   not a real claim, skip indexing: {claim[:30]}")
        return

    content_hash = _cache_service.generate_hash(claim)

    # Skip if already indexed
    if _pandas_store.find_by_hash(content_hash):
        _print(f"[NewsFetcher]   already indexed: {claim}")
        return

    # Generate embedding for vector search
    try:
        vector = _vector.vectorize_content(claim)
    except Exception as e:
        _print(f"[NewsFetcher]   embedding failed: {e}")
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
        label_source="rule",
    )
    _print(f"[NewsFetcher]   indexed claim: '{claim}' -> MISINFO")


_DETERMINISTIC_LABELS = ("rule", "gold", "admin")


def _platform_of(url: str) -> str:
    return "cofacts" if "cofacts.tw" in (url or "") else "rss"


def _merge_source_tier(prior, url: str, tier: int) -> int:
    """Cofacts 網址離線／查詢失敗時一律得 3；不可因此把先前線上分級（清洗腳本 FR-18
    規則 4 或 _analyze_record 的線上查詢）得到的 1/2 降級（與 clean_sources grade_url 同規則）。"""
    if tier == 3 and _platform_of(url) == "cofacts" and prior in (1, 2):
        return int(prior)
    return tier


def _fill_record_provenance(rec, url: str, title: str, tier=None) -> None:
    """補寫 platform / source_tier / verified，唯一定義 = spec 6.3（與 FR-18 規則 4 相同）：
    label_source in (rule, gold, admin) → True；ai 且 source_url 為 Tier 1/2 → True；其餘 False。
    trending 列的 verified 只看 source_url（RSS 餵來的真實網址），不看 AI 回的 sources——
    AI sources 經 url_validator + 分級後只決定「知識庫列」的 verified（spec 6.2 / FR-17 (a)）。
    tier=None 時零網路：tier_of(offline=True)。"""
    rec.platform = rec.platform or _platform_of(url)
    if tier is None:
        tier = tier_of(url, title, offline=True)
    rec.source_tier = _merge_source_tier(rec.source_tier, url, tier)
    if rec.label_source in _DETERMINISTIC_LABELS:
        rec.verified = True
    elif rec.label_source == "ai":
        rec.verified = rec.source_tier in (1, 2)
    else:
        rec.verified = False


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
                rec.label_source = "rule"
        elif source and source.get("is_factcheck") and confirmed_false:
            # 只有「明確被判定為假訊息」才標 MISINFO
            rec.risk_type = "MISINFO"
            rec.category = source["category"]
            rec.ai_score = 0.95
            claim = _extract_claim_from_title(title)
            rec.ai_summary = f"[{source['name']}] {claim or title}"
            rec.label_source = "rule"
        elif not source and _title_indicates_debunk(title) and \
                rec.risk_type in (None, "", "PENDING", "UNKNOWN", "SAFE"):
            # 主流媒體轉載查核結果：標題明示不實判定 → 確定性標 MISINFO
            # （可覆寫先前 AI 誤標的 SAFE，但不動已標 MISINFO/SCAM 的）
            rec.risk_type = "MISINFO"
            rec.category = "已查核假訊息"
            rec.ai_score = 0.9
            claim = _extract_claim_from_title(title)
            rec.ai_summary = f"[事實查核報導] {claim or title}"
            rec.label_source = "rule"

        # D-01 / spec 6.3：判斷樹之後只補寫欄位（不影響上面任何判定）
        _fill_record_provenance(rec, url, title)

        db.commit()

        # Phase 2: 只索引「確定不實 + 真實主張」的項目進知識庫
        if source and source.get("is_factcheck") and confirmed_false:
            _index_factcheck_claim(url, title, source)
        elif not source and _title_indicates_debunk(title):
            _index_factcheck_claim(url, title, {"name": "事實查核報導", "category": "已查核假訊息"})
    finally:
        db.close()


def _get_pending_records(limit: int = 10) -> List[FactCheckRecord]:
    from sqlalchemy import or_
    db = SessionLocal()
    try:
        # 注意：SQL 的 IN 永遠比不中 NULL，risk_type 為 NULL 的舊記錄要用 IS NULL
        # 撈（先前 .in_([..., None]) 讓 15 筆 NULL 記錄對 retry 永遠隱形）
        return db.query(FactCheckRecord).filter(
            FactCheckRecord.is_trending == True,
            or_(
                FactCheckRecord.risk_type.is_(None),
                FactCheckRecord.risk_type.in_(["PENDING", "UNKNOWN"]),
            ),
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
            elif not source and _title_indicates_debunk(title) and \
                    r.risk_type in (None, "", "PENDING", "UNKNOWN", "SAFE"):
                # 主流媒體查核報導被 AI 誤標 SAFE（判成報導本身而非被查核的謠言）→ 修正
                r.risk_type = "MISINFO"
                r.category = "已查核假訊息"
                r.ai_score = 0.9
                claim = _extract_claim_from_title(title)
                r.ai_summary = f"[事實查核報導] {claim or title}"
                _index_factcheck_claim(
                    r.source_url, title,
                    {"name": "事實查核報導", "category": "已查核假訊息"},
                )
                fixed += 1
            elif r.ai_summary == "等待 AI 分析":
                r.ai_summary = None
                r.risk_type = "PENDING"
                fixed += 1
        db.commit()
        if fixed:
            _print(f"[NewsFetcher] Cleaned/reclassified {fixed} records")
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
        _print(f"[NewsFetcher] Crawl error: {e}")

    if len(content) < 50:
        return "short"   # 內容不足（終態）：呼叫端標 UNVERIFIABLE，不再每輪重試

    ai_result = None
    try:
        content_hash = _cache_service.generate_hash(url)
        # 阻塞 IO（Parquet 讀寫、AI HTTP 呼叫）一律走 to_thread，不卡 event loop（CLAUDE.md §7）
        cached = await asyncio.to_thread(_pandas_store.find_by_hash, content_hash)
        if cached and isinstance(cached.get("ai_analysis"), dict) and not is_fallback(cached["ai_analysis"]):
            # 快取命中只沿用判定（risk_type/summary/category）；快取列的 sources 不寫進
            # SQLite、也不參與 trending verified（該值只由 source_url 決定，見 _fill_record_provenance）
            ai_result = cached["ai_analysis"]
        else:
            ai_result = await asyncio.to_thread(
                _ai.analyze_content,
                content, url=url,
                context={"extra_instructions": _NEWS_ANALYSIS_GUIDANCE},
            )
            if ai_result and not is_fallback(ai_result):
                # FR-17 (a)：Tier 1/2 必須先通過 url_validator，再分級（比照 B-15）
                tiered, related = await _validate_and_grade(ai_result.get("sources") or [])
                ai_result = {**ai_result, "sources": tiered}
                try:
                    await asyncio.to_thread(
                        _pandas_store.save_record,
                        data_type="URL", raw_content=content,
                        content_hash=content_hash, ai_result=ai_result, source_url=url,
                        label_source="ai", verified=bool(tiered),
                        related_discussions=related,
                    )
                except Exception:
                    pass
    except Exception as e:
        _print(f"[NewsFetcher] AI error: {e}")

    if not ai_result or is_fallback(ai_result):
        # explanation 已是固定文案（spec §5.5），限流/額度改讀內部欄位 error_kind（B-11）
        kind = ai_result.get("error_kind") if isinstance(ai_result, dict) else None
        if kind in ("ratelimit", "quota"):
            return "ratelimit"   # 呼叫端中止本輪批次，避免每筆都打完整 fallback 鏈燒點數
        return "ai_unavailable"   # AI 暫時失敗（額度/網路）：保留 PENDING，額度恢復後再試

    # trending 列 source_tier：對 source_url 本身分級（Cofacts 需線上查回覆，grade_sources
    # 內部已 to_thread + 總逾時；非 Cofacts 零網路）
    try:
        graded, _rel, _ms = await grade_sources([{"url": url, "title": title}])
        url_tier = int(graded[0]["tier"]) if graded else 3
    except Exception as e:
        _print(f"[NewsFetcher] source tier error: {e}")
        url_tier = 3

    # SQLite 寫入是阻塞 IO → to_thread（CLAUDE.md §7）
    await asyncio.to_thread(_apply_ai_result, url, ai_result, content, title, url_tier)
    return "ok"


async def _validate_and_grade(sources: list):
    """url_validator（阻塞 → to_thread）→ grade_sources。回傳 (Tier 1/2, Tier 3)。"""
    try:
        valid = await asyncio.to_thread(filter_valid_sources, sources)
    except Exception as e:
        _print(f"[NewsFetcher] URL validation error: {e}")
        valid = []   # 驗證失敗 → 保守視為無可信來源
    tiered, related, _tier_ms = await grade_sources(valid)
    return tiered, related


def _apply_ai_result(url: str, ai_result: dict, content: str, title: str,
                     url_tier=None) -> None:
    """把 AI 判定寫回熱門記錄（同步，供 asyncio.to_thread 呼叫）。
    url_tier：source_url 的分級（None → 離線 tier_of）；verified 依 spec 6.3 由它決定。"""
    db = SessionLocal()
    try:
        rec = db.query(FactCheckRecord).filter_by(source_url=url).first()
        if rec:
            rec.ai_score = ai_result.get("confidence_score")
            rec.ai_summary = ai_result.get("summary")
            rec.risk_type = ai_result.get("risk_type")
            rec.category = ai_result.get("category")
            rec.content = content[:2000]
            rec.label_source = "ai"
            _fill_record_provenance(rec, url, title, tier=url_tier)
            rec.updated_at = datetime.utcnow()
            db.commit()
            _print(f"[NewsFetcher]   AI done: {rec.risk_type} - {title[:30]}")
    finally:
        db.close()


async def run_trending_fetch():
    """Full pipeline: RSS fetch + classify + AI analyze. Runs every 6 hours."""
    _print(f"\n{'='*60}")
    _print(f"[NewsFetcher] Full fetch at {datetime.now():%Y-%m-%d %H:%M}")
    _print(f"{'='*60}")

    # SQLite / Parquet / RSS HTTP 皆為阻塞呼叫 → to_thread（只包呼叫，不動判斷邏輯）
    await asyncio.to_thread(_cleanup_legacy_strings)

    items = await asyncio.to_thread(SearchService.fetch_rss_items, num_per_feed=4)
    _print(f"[NewsFetcher] RSS items: {len(items)}")
    classified = 0
    for item in items:
        await asyncio.to_thread(_save_rss_record, item)
        if _detect_source(item.get("url", "")):
            classified += 1
    _print(f"[NewsFetcher] {len(items)} saved, {classified} auto-classified")

    await retry_pending_records()


def _mark_unverifiable(url: str) -> None:
    """內容不足/爬不到的記錄標為 UNVERIFIABLE（終態），不再每輪空轉重試。
    前端會顯示為「未查證」；只有 PENDING/UNKNOWN 會被標，不覆蓋已有判定。"""
    db = SessionLocal()
    try:
        rec = db.query(FactCheckRecord).filter_by(source_url=url).first()
        if rec and rec.risk_type in (None, "", "PENDING", "UNKNOWN"):
            rec.risk_type = "UNVERIFIABLE"
            if not rec.ai_summary:
                rec.ai_summary = "內容不足或無法爬取，無法自動查證"
            db.commit()
    finally:
        db.close()


async def retry_pending_records() -> int:
    """
    Lightweight job: retry AI analysis on PENDING records.
    Runs every 30 minutes - so 503 failures get retried quickly.
    Also called as part of run_trending_fetch(). 回傳本輪成功分析筆數。
    """
    pending = await asyncio.to_thread(_get_pending_records, limit=_MAX_AI_CALLS_PER_RUN)
    if not pending:
        return 0

    _print(f"[NewsFetcher] Retry job: {len(pending)} pending records")
    ok = 0
    for rec in pending:
        result = await _analyze_record(rec.source_url, rec.news_title or "", rec.content or "")
        if result == "ratelimit":
            _print(f"[NewsFetcher] Rate limited, will retry next cycle")
            break
        if result == "ok":
            ok += 1
        elif result == "short":
            # 內容太短/爬不到 → 終態，否則排程與批次會對同幾筆無限空轉
            await asyncio.to_thread(_mark_unverifiable, rec.source_url)
            _print(f"[NewsFetcher]   unverifiable (content too short): {(rec.news_title or rec.source_url)[:40]}")
        await asyncio.sleep(2)
    _print(f"[NewsFetcher] Retry done: {ok}/{len(pending)} analyzed")
    return ok
