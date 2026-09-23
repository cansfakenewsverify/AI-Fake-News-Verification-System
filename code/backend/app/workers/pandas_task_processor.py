"""
任務處理器 - 三層快取 + AI 分析
Layer 0: URL 快取 → Layer 1: Hash 快取 → Layer 2: 向量快取 → Layer 3: AI

注意：AI / embedding / 來源驗證都是同步 requests（最長 AI_TIMEOUT_SECONDS），
必須用 asyncio.to_thread 丟到執行緒，否則會把整個 FastAPI event loop
卡死（/api/analyze/sync 分析期間連 /api/trending 都無法回應）。

結果 v2（spec §5.3 result 區塊、§5.4）：
- sources 只含 Tier 1／2（每項帶 tier / tier_label），Tier 3 放 related_discussions（FR-16）。
- verification_status 推導順序固定：rule → verified → unverified（UNVERIFIABLE 與 ai_unavailable 固定 unverified）。
- frame_type / frame_label 一律由 verdict.frame_of 決定（spec §7.8 單一權威）。
"""
import asyncio
import json
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from app.config import settings
from app.services.task_store import TaskStore
from app.services.pandas_store import PandasStore, DETERMINISTIC_LABEL_SOURCES
from app.services import evidence as evidence_mod
from app.services.store_factory import get_knowledge_store, get_task_store
from app.services.crawler import CrawlerService
from app.services.ai_budget import ai_budget
from app.services.ai_service import AIService, _default_fallback_result
from app.services.cache_service import CacheService
from app.services.vector_service import VectorService
from app.utils.labels import category_label
from app.utils.source_tier import TIER_LABELS, grade_sources, tier_of
from app.utils.url_validator import filter_valid_sources
from app.utils.verdict import frame_of, is_fallback

logger = logging.getLogger(__name__)

TZ_TAIPEI = timezone(timedelta(hours=8))

# 每 1M tokens 的 USD 單價（input, output）；只作 log 估算（PF-1／PF-2 彙整用），
# 以 CGU /v1/me/usage 的實際扣款為準。查不到型號或回應沒有 usage → usd 記 null。
MODEL_PRICING_PER_1M: Dict[str, Tuple[float, float]] = {
    "gpt-5-mini": (0.25, 2.00),
    "gpt-5": (1.25, 10.00),
    # CGU_MODEL 預設型號：CGU 閘道實際計價（OpenAI 公告價 0.75／4.50 的 2 倍；DEF-06，2026-09-16 PF-5 以
    # /me/usage 核對，2026-09-23 批次 embedding 實扣也是牌價的 2 倍）
    "gpt-5.4-mini": (1.50, 9.00),
}

# ai_service 附在分析結果上的呼叫資訊（只供 log，不寫進知識庫／回應）
AI_CALL_META_KEYS = ("usage", "provider", "model")


def _safe_list(val):
    """Safely convert value to list, handling numpy arrays from parquet."""
    if val is None:
        return []
    if isinstance(val, str):
        try:
            parsed = json.loads(val)
        except (TypeError, ValueError):
            return []
        return parsed if isinstance(parsed, list) else []
    if hasattr(val, "tolist"):  # numpy array
        return val.tolist()
    if isinstance(val, list):
        return val
    try:
        return list(val)
    except Exception:
        return []


def _safe_str(val):
    if val is None:
        return ""
    if hasattr(val, "item"):  # numpy scalar
        try:
            val = val.item()
        except Exception:
            pass
    return str(val) if val else ""


def _is_verified_row(row: Dict[str, Any]) -> bool:
    """知識庫列的 verified（numpy bool／None／NaN 都要算對；NaN 視為未證實）。"""
    value = row.get("verified")
    if isinstance(value, float) and value != value:
        return False
    return bool(value)


def _stored_vector(value: Any) -> Optional[List[float]]:
    """快取列內存的向量（本機版有、Postgres 版的 find_* 不載入）；不是可用的 1536 維就回 None。"""
    if value is None:
        return None
    try:
        vector = [float(x) for x in (value.tolist() if hasattr(value, "tolist") else value)]
    except (TypeError, ValueError):
        return None
    return vector if len(vector) == settings.VECTOR_DIMENSION and any(vector) else None


def _now_taipei_iso() -> str:
    return datetime.now(TZ_TAIPEI).isoformat(timespec="seconds")


# ── 來源分級（離線補齊；線上 Cofacts 查詢只在 L3 AI 之後由 grade_sources 做）──
def _coerce_tier(value: Any) -> Optional[int]:
    try:
        tier = int(value) if value is not None else None
    except (TypeError, ValueError):
        return None
    return tier if tier in TIER_LABELS else None


def _plain_source(source: Any) -> Dict[str, Any]:
    """parquet 讀回的 struct 會帶 None 欄位（其他列才有的鍵）；去掉 None 讓回應乾淨。"""
    if isinstance(source, dict):
        return {k: v for k, v in source.items() if v is not None}
    return {"title": "", "url": str(source or "")}


def _partition_sources(sources: Any) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    逐項確保 tier / tier_label：已帶合法 tier 者直接採用（B-13／D-03 寫入，Cofacts 沿用清洗結論），
    缺 tier 者以 tier_of(url, title, offline=True) 補（不發網路請求）。回傳 (Tier 1/2, Tier 3)。
    """
    tiered: List[Dict[str, Any]] = []
    related: List[Dict[str, Any]] = []
    for raw in _safe_list(sources):
        item = _plain_source(raw)
        tier = _coerce_tier(item.get("tier"))
        if tier is None:
            tier = tier_of(item.get("url") or "", item.get("title") or "", offline=True)
        item["tier"] = tier
        item["tier_label"] = TIER_LABELS[tier]
        (related if tier == 3 else tiered).append(item)
    return tiered, related


def _normalize_cached_sources(row: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """快取命中：KB 列的 sources 補分級，Tier 3 移到 related_discussions（併入列上既有的相關討論）。"""
    ai_analysis = row.get("ai_analysis") if isinstance(row.get("ai_analysis"), dict) else {}
    sources = row.get("sources")
    if not _safe_list(sources):
        sources = (ai_analysis or {}).get("sources")
    tiered, moved = _partition_sources(sources)
    existing = [_plain_source(s) for s in _safe_list(row.get("related_discussions"))]
    return tiered, existing + moved


def _verification_status(
    label_source: str, tiered: List[Dict[str, Any]], ai_analysis: Dict[str, Any],
    ai_unavailable: bool,
) -> str:
    """
    spec §5.3 固定順序：① rule/gold/admin → rule；② Tier 1/2 來源 → verified；③ unverified。
    只看 label_source 與（已正規化的）Tier 1/2 清單，不看 KB 列存的 verified 旗標：
    死連結在 save_record 前已剔除（FN-13 iv），留在 sources 的 Tier 1/2 即可作為證實依據，
    避免「列出 Tier 1 來源卻顯示尚無查核機構證實」的矛盾組合（§8.3 S2 state 10）。
    """
    risk_type = str((ai_analysis or {}).get("risk_type") or "").upper()
    if ai_unavailable or risk_type == "UNVERIFIABLE":
        return "unverified"
    if label_source in DETERMINISTIC_LABEL_SOURCES:
        return "rule"
    return "verified" if tiered else "unverified"


def _build_result(
    ai_analysis: Dict[str, Any],
    *,
    cached: bool = False,
    cache_layer: Optional[str] = None,
    result_id: Optional[str] = None,
    label_source: str = "ai",
    sources: Optional[List[Dict[str, Any]]] = None,
    related_discussions: Optional[List[Dict[str, Any]]] = None,
    kb_id: Optional[str] = None,
    evidence: Optional[Dict[str, Any]] = None,
    similar: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    ai_analysis = ai_analysis if isinstance(ai_analysis, dict) else {}
    ai_unavailable = is_fallback(ai_analysis)

    # 無論哪條路徑都再過一次離線分級，保證 sources 只有 Tier 1/2（spec §5.3）
    tiered, moved = _partition_sources(ai_analysis.get("sources") if sources is None else sources)
    related = [_plain_source(s) for s in _safe_list(related_discussions)] + moved
    if ai_unavailable:
        tiered, related = [], []

    label_source = label_source or "ai"
    status = _verification_status(label_source, tiered, ai_analysis, ai_unavailable)
    source_tier = min((s["tier"] for s in tiered), default=None)

    ft, fl, _light = frame_of({
        **ai_analysis,
        "ai_unavailable": ai_unavailable,
        "verification_status": status,
    })
    conf = float(ai_analysis.get("confidence_score") or 0.0)
    category = _safe_str(ai_analysis.get("category")) or "Irrelevant"
    risk_type = _safe_str(ai_analysis.get("risk_type")) or "SAFE"
    # 信心等級依證據（夾角；app/services/evidence.py），不用 AI 自評分數。沒帶 evidence 時
    # （快取命中的舊資料、圖片）只依標記來源與查核來源判斷
    ev = evidence or evidence_mod.assess(
        risk_type, ai_unavailable=ai_unavailable, label_source=label_source, verification_status=status,
    )
    return {
        "result_id": result_id,
        "frame_type": ft,
        "frame_label": fl,
        "ai_unavailable": ai_unavailable,
        "is_risk": bool(ai_analysis.get("is_risk", False)),
        "risk_type": risk_type,
        "category": category,
        "category_label": category_label(category),
        "confidence_score": conf,
        "confidence_level": ev["level"],
        "confidence_basis": ev["basis"],
        "confidence_note": ev["note"],
        "evidence": {k: ev.get(k) for k in ("nearest_similarity", "nearest_degrees", "pattern_margin")},
        "summary": _safe_str(ai_analysis.get("summary")),
        "explanation": _safe_str(ai_analysis.get("explanation")),
        "sources": tiered,
        "related_discussions": related,
        "verified": status != "unverified",
        "verification_status": status,
        "source_tier": source_tier,
        # FR-02：知識庫中的相似查證（向量近鄰，只在 AI 判讀時計算；快取命中為 []）
        "similar_news": list(similar or []),
        "cached": cached,
        # 哪一層快取命中（url / hash / vector；None = 走了完整 AI 分析）。
        "cache_layer": cache_layer,
        "label_source": label_source,
        "kb_id": kb_id,
        "analyzed_at": _now_taipei_iso(),
    }


def _stored_evidence(row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """知識庫列存下的證據（第一次 AI 判讀時算的）；等級與說明依現行規則重新對應，舊資料沒有則 None。"""
    analysis = row.get("ai_analysis") if isinstance(row.get("ai_analysis"), dict) else {}
    stored = analysis.get("evidence")
    if not isinstance(stored, dict) or stored.get("basis") not in evidence_mod.LEVEL_OF_BASIS:
        return None
    basis = stored["basis"]
    return {**stored, "level": evidence_mod.LEVEL_OF_BASIS[basis], "note": evidence_mod.NOTE_OF_BASIS[basis]}


async def _evidence_inputs(store: Any, vector: Optional[List[float]]) -> Tuple[List[Dict[str, Any]], Optional[float]]:
    """證據信心的輸入：最接近的已證實列與話術差距。加分項：查詢失敗只記 log，信心退回只看來源。"""
    if not vector:
        return [], None
    try:
        neighbours = await asyncio.to_thread(store.nearest_verified, vector, evidence_mod.EVIDENCE_NEIGHBOURS)
    except Exception as e:
        logger.warning("evidence neighbour lookup failed: %s", e)
        neighbours = []
    return neighbours, evidence_mod.pattern_margin(vector)


def _estimate_usd(ai_result: Dict[str, Any], model: Optional[str]) -> Optional[float]:
    """以回應 usage × 模型單價估算；無 usage、無單價或快取命中 → None。"""
    usage = (ai_result or {}).get("usage") if isinstance(ai_result, dict) else None
    price = MODEL_PRICING_PER_1M.get(str(model or ""))
    if not isinstance(usage, dict) or not price:
        return None
    try:
        tin = float(usage.get("input_tokens") or usage.get("prompt_tokens") or 0)
        tout = float(usage.get("output_tokens") or usage.get("completion_tokens") or 0)
    except (TypeError, ValueError):
        return None
    return round((tin * price[0] + tout * price[1]) / 1_000_000, 6)


def _provider_model(meta: Optional[Dict[str, Any]]) -> Tuple[Optional[str], Optional[str]]:
    """實際回應的 provider／model（ai_service._run_analysis 附上）；不猜 providers[0]，避免 fallback 記錯。"""
    meta = meta if isinstance(meta, dict) else {}
    provider = _safe_str(meta.get("provider")) or None
    model = _safe_str(meta.get("model")) or None
    if not model and provider:
        model = {
            "cgu": getattr(settings, "CGU_MODEL", None),
            "openai": getattr(settings, "OPENAI_MODEL", None),
            "claude": getattr(settings, "CLAUDE_MODEL", None),
        }.get(provider)
    return provider, model


def _log_verification(
    result: Dict[str, Any], origin: str, started: float,
    provider: Optional[str], tier_ms: Optional[int], usd: Optional[float],
) -> None:
    """spec §9 可觀測：每筆查證一行結構化 log（PF-1、PF-2 從這行彙整）。"""
    record = {
        "result_id": result.get("result_id"),
        "origin": origin,
        "cache_layer": result.get("cache_layer"),
        "provider": provider,
        "elapsed_ms": int((time.perf_counter() - started) * 1000),
        "tier_ms": tier_ms,
        "usd": usd,
    }
    logger.info("verification %s", json.dumps(record, ensure_ascii=True))


# ── 網址爬取失敗 → UNVERIFIABLE（FR-02 驗收 3、4；B-19）──────────────────
CRAWL_FAILURE_REASONS = {
    "blocked_url": "網址指向內部或保留位址",
    "timeout": "連線逾時",
    "too_large": "網頁超過 2 MB",
    "http_error": "網頁無法存取",
    "too_short": "網頁內文過短",
}
MSG_UNSUPPORTED_PLATFORM = "目前不支援影片與 Facebook／Instagram 連結，請貼上文字內容"
MSG_UNREADABLE_PAGE = "無法讀取此網頁內容（{reason}），請改貼文字內容再試"


def _crawl_failure_explanation(crawl_result: Dict[str, Any]) -> str:
    code = str((crawl_result or {}).get("error_code") or "http_error")
    if code == "unsupported_platform":
        return MSG_UNSUPPORTED_PLATFORM
    reason = CRAWL_FAILURE_REASONS.get(code, CRAWL_FAILURE_REASONS["http_error"])
    return MSG_UNREADABLE_PAGE.format(reason=reason)


def _unverifiable_analysis(explanation: str) -> Dict[str, Any]:
    """不呼叫 AI 的 UNVERIFIABLE 判定（summary 不可用 fallback 前綴，否則會被當成 AI 不可用）。"""
    return {
        "is_risk": False,
        "risk_type": "UNVERIFIABLE",
        "category": "Irrelevant",
        "confidence_score": 0.0,
        "summary": explanation,
        "explanation": explanation,
        "sources": [],
    }


# 兩段式公用二級網域（example.com.tw、example.gov.tw、example.co.uk…）
_SECOND_LEVEL_LABELS = {"com", "org", "gov", "edu", "net", "co", "ac", "idv", "mil", "or", "ne", "go"}


def _site_domain(url: str) -> str:
    """取「站台網域」：去 www、取最後 2 段（公用二級網域取 3 段）；非 http(s) 回空字串。"""
    try:
        parsed = urlparse((url or "").strip())
    except Exception:
        return ""
    if parsed.scheme not in ("http", "https"):
        return ""
    host = (parsed.hostname or "").lower().rstrip(".")
    labels = [p for p in host.split(".") if p]
    if len(labels) <= 2:
        return ".".join(labels)
    if len(labels[-1]) == 2 and labels[-2] in _SECOND_LEVEL_LABELS:
        return ".".join(labels[-3:])
    return ".".join(labels[-2:])


def _drop_same_domain_sources(sources: List[Any], input_url: Optional[str]) -> List[Any]:
    """FR-02 驗收 6：被查的網址本身（同網域含子網域）不得當成自己的查核來源。"""
    site = _site_domain(input_url or "")
    if not site:
        return list(sources or [])
    kept = []
    for s in sources or []:
        url = (s or {}).get("url") if isinstance(s, dict) else str(s or "")
        if _site_domain(url or "") == site:
            continue
        kept.append(s)
    return kept


async def _call_ai_within_budget(call, *args, **kwargs) -> Dict[str, Any]:
    """
    FR-14：真的要呼叫 AI 前先扣每日額度（原子操作）。今天已達 DAILY_AI_CALL_CAP → 不呼叫，
    回 fallback 結果（同 AI 不可用：不寫知識庫、Threads 機器人不回覆不標記，隔日自動恢復）。
    網頁端在建立任務前就會先回 429（app/api/analyze.py）；這裡是同時送出與 Threads 機器人的最後防線。
    """
    if not await asyncio.to_thread(ai_budget.try_consume):
        fallback = _default_fallback_result("daily AI call cap reached (DAILY_AI_CALL_CAP)")
        fallback["error_kind"] = "quota"
        return fallback
    return await asyncio.to_thread(call, *args, **kwargs)


def _complete(task_store: TaskStore, task_id: str, result: Dict[str, Any]) -> None:
    """update_task(status=completed) 同步寫 v2 欄位（spec §6.1，供 /api/result）。"""
    task_store.update_task(
        task_id, status="completed",
        result_data=json.dumps(result, ensure_ascii=False),
        completed_at=datetime.utcnow(),
        ai_unavailable=bool(result.get("ai_unavailable")),
        label_source=result.get("label_source") or "ai",
        kb_id=result.get("kb_id"),
        verified=bool(result.get("verified")),
        source_tier=result.get("source_tier"),
        related_discussions=result.get("related_discussions") or [],
    )


async def cache_would_hit(input_data: str, input_type: str) -> bool:
    """
    每日額度用完時的放行判斷（app/api/analyze.py）：只查快取，不爬、不呼叫 AI。
    與主流程同一組查詢：L0 URL → L1 hash → 文字輸入的 L2 向量（以使用者原文比對）。
    網址輸入的 L2 要先爬內文、圖片沒有快取層：額度用完時這兩種沒查過的輸入一律擋下。
    （命中時 hit_count 會被這裡與主流程各加一次，只發生在額度用完的期間，可接受。）
    """
    if input_type == "image":
        return False
    pandas_store = get_knowledge_store() if settings.use_supabase else PandasStore()

    def _usable(row: Optional[Dict[str, Any]]) -> bool:
        return bool(row) and not is_fallback(row.get("ai_analysis"))

    is_url = input_data.startswith("http://") or input_data.startswith("https://")
    if is_url and _usable(await asyncio.to_thread(pandas_store.find_by_url, input_data)):
        return True
    content_hash = CacheService().generate_hash(input_data)
    if _usable(await asyncio.to_thread(pandas_store.find_by_hash, content_hash)):
        return True
    if not is_url:
        query_vector = await asyncio.to_thread(VectorService().vectorize_content, input_data)
        if _usable(await asyncio.to_thread(pandas_store.find_similar_by_vector, query_vector)):
            return True
    return False


async def process_analysis_task_async(
    task_id: str, input_data: str, input_type: str
) -> Dict[str, Any]:
    """
    非同步處理分析任務。三層快取策略：
      Layer 0: URL 快取（URL 輸入專用）
      Layer 1: Hash 快取（完全重複）
      Layer 2: 向量快取（語義相似）
      Layer 3: AI 分析（全流程）
    """
    started = time.perf_counter()
    # 本機：沿用模組層級的 TaskStore／PandasStore（測試以 monkeypatch 替換這兩個名稱）；
    # STORAGE_BACKEND=supabase：store_factory 的 Postgres 單例（介面相同）
    task_store = get_task_store() if settings.use_supabase else TaskStore()
    pandas_store = get_knowledge_store() if settings.use_supabase else PandasStore()
    crawler = CrawlerService()
    ai_service = AIService()
    cache_service = CacheService()
    vector_service = VectorService()

    # Parquet 讀寫是阻塞 IO：一律丟執行緒，不卡 event loop（CLAUDE.md §7）
    task = await asyncio.to_thread(task_store.get_task, task_id) or {}
    origin = task.get("origin") or "web"

    await asyncio.to_thread(task_store.update_task, task_id, status="processing")

    async def _finish_cached(
        row: Dict[str, Any], layer: str, input_urls: Tuple[Optional[str], ...] = (),
    ) -> Dict[str, Any]:
        tiered, related = _normalize_cached_sources(row)
        # FR-02 驗收 6：快取命中（L0/L1/L2）也不得把被查網址的同站頁面當成查核來源
        for input_url in input_urls:
            tiered = _drop_same_domain_sources(tiered, input_url)
            related = _drop_same_domain_sources(related, input_url)
        label_source = _safe_str(row.get("label_source")) or "ai"
        result = _build_result(
            row.get("ai_analysis"), cached=True, cache_layer=layer, result_id=task_id,
            label_source=label_source,
            sources=tiered, related_discussions=related,
            kb_id=_safe_str(row.get("id")) or None,
            evidence=None if label_source in DETERMINISTIC_LABEL_SOURCES else _stored_evidence(row),
        )
        await asyncio.to_thread(_complete, task_store, task_id, result)
        _log_verification(result, origin, started, None, None, None)
        return result

    def _usable(row: Optional[Dict[str, Any]]) -> bool:
        return bool(row) and not is_fallback(row.get("ai_analysis"))

    async def _newer_factcheck(row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        查核結果回補：URL／hash 層不過濾 verified，所以一字不差的重複查詢會一直拿到當初
        「尚無查核機構證實」的舊結果。命中的是未證實列時，先以它的內容到向量層只找確定性標記
        （rule／gold／admin，即查核機構文章索引或人工確認的結論）；對得上就改回那一筆。
        只限確定性標記：舊結果是針對這段原文判的，換掉它要有查核機構層級的證據，
        一般 AI 判定＋來源的列不夠（可能只是長得像的另一則訊息）。
        已證實的列、embedding 不可用、沒有對上 → None，照舊回原列。不呼叫判讀模型。
        這一步是加分項：查詢出錯只記 log、照舊回原列，不讓原本會命中的快取變成失敗。
        """
        if _is_verified_row(row):
            return None
        try:
            vector = _stored_vector(row.get("content_vector"))
            if vector is None:
                text = _safe_str(row.get("raw_content"))
                if not text:
                    return None
                vector = await asyncio.to_thread(vector_service.vectorize_content, text)
            if not vector:
                return None
            found = await asyncio.to_thread(
                lambda: pandas_store.find_similar_by_vector(
                    vector, label_sources=DETERMINISTIC_LABEL_SOURCES,
                )
            )
        except Exception as e:
            logger.warning("fact-check supersede lookup failed for task %s: %s", task_id, e)
            return None
        return found if _usable(found) else None

    try:
        is_url = input_data.startswith("http://") or input_data.startswith("https://")

        # ── Layer 0: URL 快取 ──────────────────────────────────────────
        if input_type in ("text", "url") and is_url:
            url_cached = await asyncio.to_thread(pandas_store.find_by_url, input_data)
            if _usable(url_cached):
                newer = await _newer_factcheck(url_cached)
                if newer is not None:
                    return await _finish_cached(newer, "vector", (input_data,))
                return await _finish_cached(url_cached, "url", (input_data,))

        # ── Layer 1: Hash 快取（對原始輸入做 hash）────────────────────
        content_hash = cache_service.generate_hash(input_data)
        # find_by_hash 命中時會回寫整個 knowledge_base.parquet（hit_count）
        hash_cached = await asyncio.to_thread(pandas_store.find_by_hash, content_hash)
        if _usable(hash_cached):
            input_urls = (input_data,) if is_url else ()
            newer = await _newer_factcheck(hash_cached)
            if newer is not None:
                return await _finish_cached(newer, "vector", input_urls)
            return await _finish_cached(hash_cached, "hash", input_urls)

        # ── 圖片分析路徑（無快取層、不寫知識庫）──────────────────────
        if input_type == "image":
            if not os.path.isfile(input_data):
                raise Exception("圖片檔案不存在")
            ai_result = await _call_ai_within_budget(ai_service.analyze_image, input_data)
            try:
                os.remove(input_data)
            except Exception:
                pass
            return await _finish_ai(
                task_store, task_id, ai_result, ai_service, origin, started, kb_id=None,
            )

        # ── Layer 2（文字輸入）：向量快取 ──────────────────────────────
        # 知識庫存的是「謠言主張」的向量，必須拿使用者原文比對才會命中
        # 「換句話說的同一謠言」。命中即回，AI 呼叫就省下。勿改回拿網頁全文比對。
        query_vector: list = []
        if not is_url:
            query_vector = await asyncio.to_thread(
                vector_service.vectorize_content, input_data
            )
            vector_cached = await asyncio.to_thread(
                pandas_store.find_similar_by_vector, query_vector
            )
            if _usable(vector_cached):
                return await _finish_cached(vector_cached, "vector")

        # ── 取得分析內容 ───────────────────────────────────────────────
        # FR-01：文字輸入不爬、不送任何搜尋引擎，分析對象一律是使用者原文。
        if is_url:
            crawl_result = await crawler.process_input(input_data, "url") or {}
            if not crawl_result.get("success"):
                # FR-02：爬取失敗 / 不支援平台 → completed + UNVERIFIABLE；不呼叫 AI、不寫知識庫
                logger.info(
                    "crawl failed for task %s: %s", task_id, crawl_result.get("error_code"),
                )
                result = _build_result(
                    _unverifiable_analysis(_crawl_failure_explanation(crawl_result)),
                    cached=False, cache_layer=None, result_id=task_id,
                    label_source="ai", sources=[], related_discussions=[],
                )
                await asyncio.to_thread(_complete, task_store, task_id, result)
                _log_verification(result, origin, started, None, None, None)
                return result
            content = crawl_result.get("content", input_data) or input_data
            url = crawl_result.get("url") or input_data
        else:
            content = input_data
            url = None

        # ── Layer 2（網址輸入）：向量快取，以爬到的內文語意比對 ───────
        if is_url:
            content_vector = await asyncio.to_thread(vector_service.vectorize_content, content)
            vector_cached = await asyncio.to_thread(pandas_store.find_similar_by_vector, content_vector)
            if _usable(vector_cached):
                # 輸入網址與轉址後的最終網址都要剔除
                return await _finish_cached(vector_cached, "vector", (input_data, url))
        else:
            # 文字輸入沿用原文向量（上面已比對過、未命中），存檔用
            content_vector = query_vector

        # ── Layer 3: AI 分析（全流程）─────────────────────────────────
        # 證據信心的近鄰查詢與 AI 判讀同時進行（查詢約 0.2～0.5 秒，AI 9～27 秒，不增加等待時間）
        evidence_task = asyncio.create_task(_evidence_inputs(pandas_store, content_vector))
        try:
            ai_result = await _call_ai_within_budget(
                ai_service.analyze_content, content, url=url, context={"similar_news": []}
            )
        except BaseException:
            evidence_task.cancel()
            raise
        neighbours, margin = await evidence_task

        return await _finish_ai(
            task_store, task_id, ai_result, ai_service, origin, started,
            input_url=url, neighbours=neighbours, margin=margin,
            save=lambda graded_ai, related: pandas_store.save_record(
                data_type=input_type.upper(),
                # 文字輸入存「使用者原文」：與 content_vector 語意一致；網址輸入存爬到的內文
                raw_content=content if is_url else input_data,
                content_hash=content_hash,
                content_vector=content_vector,
                ai_result=graded_ai,
                source_url=url,
                label_source="ai",
                origin=origin,
                last_result_id=task_id,
                related_discussions=related,
            ),
        )

    except Exception as e:
        await asyncio.to_thread(
            task_store.update_task, task_id, status="failed", error_message=str(e),
        )
        raise


async def _finish_ai(
    task_store: TaskStore, task_id: str, ai_result: Dict[str, Any], ai_service: Any,
    origin: str, started: float, save=None, kb_id: Optional[str] = None,
    input_url: Optional[str] = None,
    neighbours: Optional[List[Dict[str, Any]]] = None, margin: Optional[float] = None,
) -> Dict[str, Any]:
    """L3 之後：剔除同網域 → filter_valid_sources → grade_sources → 寫知識庫（fallback 不寫）→ 組結果。"""
    ai_result = dict(ai_result) if isinstance(ai_result, dict) else {}
    # 呼叫資訊只進 log：先拆出來，避免寫進知識庫 ai_analysis
    meta = {k: ai_result.pop(k) for k in AI_CALL_META_KEYS if k in ai_result}
    fallback = is_fallback(ai_result)
    tiered: List[Dict[str, Any]] = []
    related: List[Dict[str, Any]] = []
    tier_ms: Optional[int] = None

    if not fallback:
        sources = _drop_same_domain_sources(_safe_list(ai_result.get("sources")), input_url)
        if sources:
            # 過濾 AI 幻覺／死連結（FN-13 iv：Tier 1 來源被判死 → 不算證實）
            try:
                sources = await asyncio.to_thread(filter_valid_sources, sources)
            except Exception as e:
                # 驗證不了 = 未驗證：整批丟棄，不讓可能的幻覺連結算作證實或寫進 KB
                logger.warning("URL validation error, dropping %d unvalidated sources: %s", len(sources), e)
                sources = []
        tiered, related, tier_ms = await grade_sources(sources)
        ai_result["sources"] = tiered

    evidence = evidence_mod.assess(
        _safe_str(ai_result.get("risk_type")) or "SAFE", ai_unavailable=fallback, label_source="ai",
        verification_status=_verification_status("ai", tiered, ai_result, fallback),
        neighbours=neighbours, margin=margin,
    )
    if not fallback:
        # 存進知識庫的 ai_analysis：之後快取命中沿用同一份依據（同一則訊息每次查都得到相同的信心）
        ai_result["evidence"] = evidence
        if save is not None:
            record = await asyncio.to_thread(save, ai_result, related)
            kb_id = (record or {}).get("id") or kb_id

    result = _build_result(
        ai_result, cached=False, cache_layer=None, result_id=task_id,
        label_source="ai", sources=tiered, related_discussions=related, kb_id=kb_id,
        evidence=evidence, similar=[] if fallback else evidence_mod.similar_news(neighbours),
    )
    await asyncio.to_thread(_complete, task_store, task_id, result)

    provider, model = _provider_model(meta)
    _log_verification(
        result, origin, started, provider, tier_ms,
        None if fallback else _estimate_usd(meta, model),
    )
    return result


def process_analysis_task(task_id: str, input_data: str, input_type: str) -> None:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        loop.create_task(process_analysis_task_async(task_id, input_data, input_type))
    else:
        asyncio.run(process_analysis_task_async(task_id, input_data, input_type))
