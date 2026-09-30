"""
每週新查核自動評測（spec FR-24；docs/test/上線後準確率驗證計畫.md 的 M5）。

CGU 的 OpenAI 額度每週 USD 10、用不完不累積。本工作把每週剩下的額度拿來量「AI 判讀準不準」：
題目與真值都來自查核機構已發布的結論，不由 AI 助理或組員產生。

- 本週新查核（part=fresh）：最近 7 天（台灣時間）發布、已有判定的查核結論——MyGoPen 標題標籤、台灣事實查核中心
  「查核結果」、Cofacts 獲認可的 RUMOR／NOT_RUMOR 回覆（收錄規則同 factcheck_corpus；SAFE 題也收，才量得到偽陽性）。
  一篇查核報告只出一題。這些內容出現在模型訓練之後，是主要數字。
- 歷史抽樣（part=history）：額度還有剩時，風險題取自知識庫中查核機構已證實的列（origin=factcheck_batch）——
  依固定順序每週往下取一段（每週 2,000 題，約 1.85 萬筆約 9～10 週輪完一遍，之後從頭再來），累積起來就是整個知識庫的
  判讀正確率；安全題取自 Cofacts 獲認可的 NOT_RUMOR 訊息（每週以 ISO 週次為 seed 抽樣，會與前幾週重複）。
  風險題:安全題 = 2:1。可能在模型訓練資料中，報告分開列。
- 直接呼叫 AIService，與 scripts/evaluate.py 相同：不經快取、不帶 web_search、不寫知識庫、不計入每日 AI 次數。
- 額度護欄：開始前讀 CGU /me/usage，可用額 = min(WEEKLY_EVAL_MAX_USD, 剩餘 − WEEKLY_EVAL_RESERVE_USD)；
  每 20 題以回應的 usage 估算花費，每 100 題重讀一次 /me/usage（網站使用者同時在用），快碰到保留額就停。
  讀不到 /me/usage 時只跑本週新查核，且上限 USD 1。整批 AI 都失敗（額度用完、閘道故障）時立刻停。
- 結果只存在記憶體（最近一次）。GitHub Actions 的 weekly-eval workflow 等它做完，把 Markdown 報告與 CSV 存進
  docs/test/results/weekly/。CSV 不含訊息原文（Cofacts 訊息可能含個資），只有網址、雜湊與判定。
"""
import csv
import hashlib
import io
import logging
import math
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

from app.config import settings
from app.services import factcheck_corpus as fc
from app.services.store_factory import get_knowledge_store
from app.utils.verdict import is_fallback

logger = logging.getLogger(__name__)

TZ_TAIPEI = timezone(timedelta(hours=8))
FRESH_DAYS = 7
EST_USD_PER_CALL = 0.0015        # 2026-09-30 實測：gpt-5.6-luna、medium、無 web_search 每次約 USD 0.0014
UNKNOWN_USAGE_CAP_USD = 1.0      # 讀不到 CGU 用量時的上限（只跑本週新查核）
HISTORY_MAX = 3000               # 每週歷史抽樣上限（風險 2,000＋安全 1,000；約 75 分鐘、USD 4.5）
HISTORY_RISKY_PER_WEEK = 2000    # 風險題每週往下輪的段長（固定，不隨額度變動，各週的段才不會重疊）
HISTORY_SEED = "fnv-weekly-history-v1"
HISTORY_EPOCH = date(2026, 9, 28)   # 第 0 段的那一週（週一）
HISTORY_SAFE_SHARE = 1 / 3       # 歷史抽樣中 SAFE 題的比例（風險題:安全題 = 2:1）
COFACTS_RECENT_LIMIT = 300       # 本週新查核：Cofacts 最近有新回覆的訊息各抓幾則（RUMOR、NOT_RUMOR）
COFACTS_EVAL_MIN_REQUESTS = 1    # 評測的真值來自獲認可的回覆；回報人數門檻是入庫條件，評測不需要
COFACTS_SAFE_POOL = 1500         # 歷史抽樣的 SAFE 題庫：Cofacts 最多人回報的 NOT_RUMOR 訊息
CONCURRENCY = 4
CHUNK = 20
USAGE_CHECK_EVERY = 100
MAX_MINUTES = 150                # GitHub Actions 的 workflow 最多等 200 分鐘
MAX_CHARS = 20000                # 與 /api/analyze/text 的輸入上限相同
RISKY = {"SCAM", "MISINFO"}
LABELS = ("SCAM", "MISINFO", "SAFE")
PRED_COLUMNS = ("SCAM", "MISINFO", "SAFE", "UNVERIFIABLE", "其他")
CSV_COLUMNS = ["run_date", "part", "source", "url", "content_hash", "published", "gold", "predicted",
               "fallback", "confidence_score", "correct_risk", "correct_exact", "usd"]

_lock = threading.Lock()
STATUS: Dict[str, Any] = {}
LAST: Dict[str, Any] = {"rows": [], "meta": None}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def today_taipei() -> date:
    return datetime.now(TZ_TAIPEI).date()


def _reset(max_usd: float, plan_only: bool) -> None:
    STATUS.clear()
    STATUS.update(state="queued", phase=None, started_at=_now(), finished_at=None, plan_only=plan_only,
                  max_usd=max_usd, allowed_usd=None, usage_before=None, usage_after=None,
                  available_fresh=0, planned=0, planned_fresh=0, planned_history=0, done=0, fallbacks=0,
                  spent_usd=0.0,
                  stop_reason=None, source_errors={}, summary=None, error=None)


_reset(0.0, False)
STATUS["state"] = "idle"


def is_running() -> bool:
    return _lock.locked()


def status() -> Dict[str, Any]:
    return {**STATUS, "source_errors": dict(STATUS.get("source_errors") or {})}


# ── 題目 ─────────────────────────────────────────────────────

def _source_of(url: str) -> str:
    u = str(url or "")
    if "mygopen.com" in u:
        return "MyGoPen"
    if "tfc-taiwan.org.tw" in u:
        return "TFC"
    if "cofacts.tw" in u:
        return "Cofacts"
    return "其他"


def _item(part: str, row: Dict[str, Any]) -> Dict[str, Any]:
    return {"part": part, "source": row["source"], "url": row.get("url") or "", "content_hash": row["content_hash"],
            "published": str(row.get("published") or ""), "gold": row["label"], "text": row["text"]}


def fresh_items(days: int = FRESH_DAYS, today: Optional[date] = None) -> Tuple[List[dict], dict]:
    """最近 days 天發布的已判定查核結論 → (題目, 抓取失敗的來源)。"""
    cutoff = ((today or today_taipei()) - timedelta(days=days)).isoformat()
    skipped: dict = {}
    errors: dict = {}
    rows: List[dict] = []

    def cofacts() -> List[dict]:
        out = []
        for want in ("RUMOR", "NOT_RUMOR"):
            nodes = fc.cofacts_nodes(want, COFACTS_EVAL_MIN_REQUESTS, COFACTS_RECENT_LIMIT, order="replied")
            out.extend(fc.cofacts_rows(nodes, want, skipped))
        return out

    fetchers = (
        ("MyGoPen", lambda: fc.mygopen_rows(fc.mygopen_entries(max_pages=1), skipped)),
        ("TFC", lambda: fc.tfc_rows(report_pages=1, rumor_pages=3, skipped=skipped)),
        ("Cofacts", cofacts),
    )
    for name, fetch in fetchers:
        STATUS["phase"] = f"fetch:{name}"
        try:
            rows.extend(r for r in fetch() if str(r.get("published") or "") >= cutoff)
        except Exception as exc:
            logger.exception("weekly eval: %s fetch failed", name)
            errors[name] = f"{type(exc).__name__}: {exc}"[:200]
    items, seen, rank = [], set(), {}
    for row in sorted(fc.dedupe_rows(rows, skipped), key=lambda r: (r["source"], r["url"], r["content_hash"])):
        if row["url"] in seen:   # 台灣事實查核中心一篇報告可能對應多則謠言原文：只出一題
            continue
        seen.add(row["url"])
        rank[row["source"]] = rank.get(row["source"], -1) + 1
        items.append({**_item("fresh", row), "_rank": rank[row["source"]]})
    # 三個來源輪流排：額度不夠、只能跑前幾題時，每個來源都有題目
    items.sort(key=lambda i: (i.pop("_rank"), i["source"]))
    return items, errors


def _md5_key(content_hash: str, seed: str) -> str:
    return hashlib.md5((content_hash + seed).encode("utf-8")).hexdigest()


def history_risky_rows(store: Any, n: int, run_day: date) -> List[dict]:
    """知識庫查核機構列依固定順序的第 week 段（每段 HISTORY_RISKY_PER_WEEK 筆），到尾端就從頭接上。"""
    pool = store.verified_origin_count(fc.ORIGIN)
    if pool == 0 or n <= 0:
        return []
    week = max((run_day - HISTORY_EPOCH).days // 7, 0)
    offset = (week * HISTORY_RISKY_PER_WEEK) % pool
    rows = store.sample_verified(fc.ORIGIN, n, seed=HISTORY_SEED, offset=offset)
    if len(rows) < n and offset > 0:
        rows += store.sample_verified(fc.ORIGIN, min(n - len(rows), offset), seed=HISTORY_SEED)
    return rows


def history_items(n: int, run_day: date, exclude: Iterable[str], store: Any) -> List[dict]:
    """歷史抽樣 n 題：風險題是知識庫查核機構列的本週那一段，安全題取自 Cofacts 獲認可的 NOT_RUMOR 訊息（2:1）。"""
    if n <= 0:
        return []
    skip = set(exclude)
    n_risky = n - int(n * HISTORY_SAFE_SHARE)
    risky = [{"part": "history", "source": _source_of(r["source_url"]), "url": r["source_url"] or "",
              "content_hash": r["data_hash"], "published": "", "gold": str(r["risk_type"]).upper(),
              "text": r["raw_content"]}
             for r in history_risky_rows(store, n_risky, run_day) if r["data_hash"] not in skip]
    # 知識庫還沒有查核機構資料時不抽安全題，避免歷史抽樣只剩 SAFE 題
    n_safe = min(n - n_risky, len(risky) // 2)
    iso = run_day.isocalendar()
    seed = f"{iso[0]}-W{iso[1]:02d}"
    safe: List[dict] = []
    if n_safe > 0:
        STATUS["phase"] = "fetch:Cofacts NOT_RUMOR pool"
        # 沿用入庫門檻（至少 3 人回報）：題目比較像真的在流傳的訊息
        nodes = fc.cofacts_nodes("NOT_RUMOR", fc.COFACTS_MIN_REQUESTS, COFACTS_SAFE_POOL)
        pool = [r for r in fc.dedupe_rows(fc.cofacts_rows(nodes, "NOT_RUMOR")) if r["content_hash"] not in skip]
        pool.sort(key=lambda r: _md5_key(r["content_hash"], seed))
        safe = [_item("history", r) for r in pool[:n_safe]]
    return risky + safe


# ── 判讀 ─────────────────────────────────────────────────────

def _predict(ai: Any, item: Dict[str, Any]) -> Dict[str, Any]:
    from app.workers.pandas_task_processor import _estimate_usd

    try:
        res = ai.analyze_content(item["text"][:MAX_CHARS], use_web_search=False)
    except Exception as exc:   # analyze_content 自己會回 fallback；這裡只防意外
        res = {"ai_unavailable": True, "summary": f"AI 分析暫時無法使用：{type(exc).__name__}"}
    fallback = is_fallback(res)
    predicted = None if fallback else str(res.get("risk_type") or "UNKNOWN").upper()
    gold = item["gold"]
    row = {k: v for k, v in item.items() if k != "text"}
    row.update(
        predicted=predicted, fallback=fallback,
        confidence_score=None if fallback else res.get("confidence_score"),
        correct_risk=None if fallback else (
            (gold in RISKY and predicted in RISKY) or (gold == "SAFE" and predicted == "SAFE")),
        correct_exact=None if fallback else predicted == gold,
        usd=None if fallback else _estimate_usd(res, res.get("model")),
        provider=res.get("provider"), model=res.get("model"),
    )
    return row


# ── 執行 ─────────────────────────────────────────────────────

def try_start(max_usd: Optional[float] = None, plan_only: bool = False, days: int = FRESH_DAYS,
              background_tasks: Optional[Any] = None) -> bool:
    """在請求當下取得鎖並排入背景；已有一輪在跑回 False。"""
    if not _lock.acquire(blocking=False):
        return False
    cap = _cap(max_usd)
    _reset(cap, plan_only)
    if background_tasks is not None:
        background_tasks.add_task(_run_locked, cap, plan_only, days)
    else:
        threading.Thread(target=_run_locked, args=(cap, plan_only, days), daemon=True).start()
    return True


def run_eval(max_usd: Optional[float] = None, plan_only: bool = False, days: int = FRESH_DAYS,
             store: Any = None, ai: Any = None, today: Optional[date] = None) -> Dict[str, Any]:
    """評測一次並等它做完（測試與腳本用）。已有一輪在跑時直接回傳目前狀態。"""
    if not _lock.acquire(blocking=False):
        return status()
    cap = _cap(max_usd)
    _reset(cap, plan_only)
    return _run_locked(cap, plan_only, days, store, ai, today)


def _cap(max_usd: Optional[float]) -> float:
    cap = float(settings.WEEKLY_EVAL_MAX_USD)
    return min(cap, float(max_usd)) if max_usd is not None else cap


def _run_locked(cap: float, plan_only: bool, days: int, store: Any = None, ai: Any = None,
                today: Optional[date] = None) -> Dict[str, Any]:
    """呼叫前必須已持有 _lock；結束時釋放。"""
    try:
        STATUS.update(state="running", phase="usage")
        run_day = today or today_taipei()
        reserve = float(settings.WEEKLY_EVAL_RESERVE_USD)
        usage = fc.cgu_usage()
        remaining = usage["remaining_usd"]
        known = remaining >= 0
        allowed = min(cap, remaining - reserve) if known else min(cap, UNKNOWN_USAGE_CAP_USD)
        STATUS.update(usage_before=usage, allowed_usd=round(allowed, 4))
        if allowed <= 0 and not plan_only:
            STATUS.update(state="skipped", phase=None, finished_at=_now(), stop_reason="reserve")
            LAST.update(rows=[], meta=_meta(run_day, days, usage, None, cap, reserve))
            return status()

        fresh, errors = fresh_items(days, run_day)
        STATUS.update(source_errors=errors, available_fresh=len(fresh))
        fresh = fresh[:max(int(allowed / EST_USD_PER_CALL), 0)]
        history: List[dict] = []
        n_history = min(HISTORY_MAX, int((allowed - len(fresh) * EST_USD_PER_CALL) / EST_USD_PER_CALL))
        if known and n_history > 0:
            history = history_items(n_history, run_day, {i["content_hash"] for i in fresh},
                                    store or get_knowledge_store())
        items = fresh + history
        STATUS.update(planned=len(items), planned_fresh=len(fresh), planned_history=len(history))
        if plan_only:
            STATUS.update(state="done", phase=None, finished_at=_now())
            return status()
        rows = _judge(items, allowed, reserve, known, ai)
        meta = _meta(run_day, days, usage, fc.cgu_usage() if rows else None, cap, reserve)
        for r in rows:   # 實際回答的模型（主模型下架時會是 CGU_FALLBACK_MODEL）
            if r.get("model"):
                meta["models_used"][r["model"]] = meta["models_used"].get(r["model"], 0) + 1
        LAST.update(rows=rows, meta=meta)
        STATUS.update(state="done", phase=None, finished_at=_now(), usage_after=meta["usage_after"],
                      summary={part: summarize([r for r in rows if r["part"] == part]) for part in ("fresh", "history")})
        logger.info("weekly eval done: %d judged, %d fallbacks, est USD %.4f",
                    STATUS["done"], STATUS["fallbacks"], STATUS["spent_usd"])
    except Exception as exc:
        logger.exception("weekly eval failed")
        STATUS.update(state="failed", phase=None, finished_at=_now(), error=f"{type(exc).__name__}: {exc}"[:300])
    finally:
        _lock.release()
    return status()


def _judge(items: List[dict], allowed: float, reserve: float, usage_known: bool, ai: Any) -> List[dict]:
    if ai is None:
        from app.services.ai_service import AIService
        ai = AIService()
    STATUS["phase"] = "judge"
    rows: List[dict] = []
    spent, priced = 0.0, 0
    deadline = time.monotonic() + MAX_MINUTES * 60
    with ThreadPoolExecutor(max_workers=CONCURRENCY) as pool:
        for start in range(0, len(items), CHUNK):
            chunk = items[start:start + CHUNK]
            per_call = spent / priced if priced else EST_USD_PER_CALL
            if time.monotonic() > deadline:
                STATUS["stop_reason"] = "time"
                break
            if spent + per_call * len(chunk) > allowed:
                STATUS["stop_reason"] = "budget"
                break
            if usage_known and start and start % USAGE_CHECK_EVERY == 0:
                left = fc.cgu_usage()["remaining_usd"]
                if 0 <= left and left - per_call * len(chunk) < reserve:
                    STATUS["stop_reason"] = "reserve"
                    break
            got = list(pool.map(lambda it: _predict(ai, it), chunk))
            rows.extend(got)
            for r in got:
                if r["usd"] is not None:
                    spent += float(r["usd"])
                    priced += 1
            STATUS.update(done=len(rows), fallbacks=sum(1 for r in rows if r["fallback"]), spent_usd=round(spent, 4))
            if all(r["fallback"] for r in got):
                STATUS["stop_reason"] = "ai_unavailable"
                break
    return rows


def _meta(run_day: date, days: int, before: dict, after: Optional[dict], cap: float, reserve: float) -> Dict[str, Any]:
    """報告用的執行條件；在一輪結束時與結果一起存進 LAST，下一輪開始後報告仍與結果一致。"""
    return {"run_date": run_day.isoformat(), "window_start": (run_day - timedelta(days=days)).isoformat(),
            "days": days, "provider": settings.AI_PROVIDER, "model": settings.CGU_MODEL,
            "reasoning_effort": settings.CGU_REASONING_EFFORT, "use_web_search": False,
            "usage_before": before, "usage_after": after, "max_usd": cap, "reserve_usd": reserve,
            "stop_reason": STATUS.get("stop_reason"), "source_errors": dict(STATUS.get("source_errors") or {}),
            "available_fresh": STATUS.get("available_fresh", 0), "models_used": {}}


# ── 統計與報告 ───────────────────────────────────────────────

def wilson(k: int, n: int, z: float = 1.96) -> Tuple[float, float]:
    if n == 0:
        return 0.0, 0.0
    p = k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return round(max(0.0, centre - half), 6), round(min(1.0, centre + half), 6)


def summarize(rows: List[dict]) -> Dict[str, Any]:
    valid = [r for r in rows if not r["fallback"]]
    n = len(valid)
    risk_ok = sum(1 for r in valid if r["correct_risk"])
    exact_ok = sum(1 for r in valid if r["correct_exact"])
    matrix = {g: {p: 0 for p in PRED_COLUMNS} for g in LABELS}
    for r in valid:
        col = r["predicted"] if r["predicted"] in PRED_COLUMNS else "其他"
        if r["gold"] in matrix:
            matrix[r["gold"]][col] += 1
    by_source: Dict[str, Dict[str, int]] = {}
    for r in valid:
        s = by_source.setdefault(r["source"], {"n": 0, "risk_ok": 0, "fn": 0})
        s["n"] += 1
        s["risk_ok"] += int(bool(r["correct_risk"]))
        s["fn"] += int(r["gold"] in RISKY and r["predicted"] == "SAFE")
    return {
        "n": len(rows), "valid": n, "fallbacks": len(rows) - n,
        "risk_accuracy": round(risk_ok / n, 4) if n else None, "risk_ci": [round(x, 4) for x in wilson(risk_ok, n)],
        "exact_accuracy": round(exact_ok / n, 4) if n else None, "exact_ci": [round(x, 4) for x in wilson(exact_ok, n)],
        "fn": sum(1 for r in valid if r["gold"] in RISKY and r["predicted"] == "SAFE"),
        "fp": sum(1 for r in valid if r["gold"] == "SAFE" and r["predicted"] in RISKY),
        "unverifiable": sum(1 for r in valid if r["predicted"] == "UNVERIFIABLE"),
        "gold_counts": {g: sum(1 for r in rows if r["gold"] == g) for g in LABELS},
        "matrix": matrix, "by_source": by_source,
        "usd": round(sum(float(r["usd"]) for r in valid if r["usd"] is not None), 4),
    }


def has_report() -> bool:
    return LAST.get("meta") is not None


def results_csv() -> str:
    meta = LAST.get("meta") or {}
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=CSV_COLUMNS, extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    for r in LAST.get("rows") or []:
        writer.writerow({**r, "run_date": meta.get("run_date", "")})
    return out.getvalue()


def _pct(x: Optional[float]) -> str:
    return "—" if x is None else f"{x * 100:.1f}%"


def _usage_line(u: Optional[dict]) -> str:
    if not u or u.get("cost_usd", -1) < 0:
        return "讀不到"
    return f"本週已用 USD {u['cost_usd']:.4f}，剩 USD {u['remaining_usd']:.4f}（額度 USD {u['quota_usd']:.2f}）"


STOP_REASONS = {
    None: "全部題目都已判讀", "budget": "達到本次可用額度", "reserve": "CGU 剩餘額度接近保留額（留給網站使用者）",
    "time": f"超過 {MAX_MINUTES} 分鐘", "ai_unavailable": "整批 AI 判讀都失敗（額度用完或閘道故障）",
}


def _part_section(title: str, note: str, s: Dict[str, Any], rows: List[dict]) -> List[str]:
    lines = [f"## {title}", "", note, ""]
    if not s["n"]:
        return lines + ["本次沒有這一類題目。", ""]
    lo, hi = s["risk_ci"]
    elo, ehi = s["exact_ci"]
    gold = "、".join(f"{g} {s['gold_counts'][g]}" for g in LABELS)
    lines += [
        f"- 題數 {s['n']}（{gold}）；有效判讀 {s['valid']}，AI 服務不可用 {s['fallbacks']}",
        f"- **風險判定一致率 {_pct(s['risk_accuracy'])}**（95% 信賴區間 {_pct(lo)}–{_pct(hi)}）："
        "真值有風險（SCAM／MISINFO）時 AI 也判有風險、真值 SAFE 時 AI 也判 SAFE；AI 判「無法查證」算不一致",
        f"- 三類完全一致率 {_pct(s['exact_accuracy'])}（{_pct(elo)}–{_pct(ehi)}）",
        f"- **偽陰性（真值有風險、AI 判 SAFE）{s['fn']} 筆**；偽陽性 {s['fp']} 筆；AI 判「無法查證」{s['unverifiable']} 筆",
        f"- 估算花費 USD {s['usd']:.4f}",
        "",
        "| 真值 ＼ AI 判定 | " + " | ".join(PRED_COLUMNS) + " |",
        "|---|" + "---:|" * len(PRED_COLUMNS),
    ]
    for g in LABELS:
        lines.append(f"| {g} | " + " | ".join(str(s["matrix"][g][p]) for p in PRED_COLUMNS) + " |")
    lines += ["", "| 來源 | 有效題數 | 風險判定一致率 | 偽陰性 |", "|---|---:|---:|---:|"]
    for src, v in sorted(s["by_source"].items()):
        lines.append(f"| {src} | {v['n']} | {_pct(v['risk_ok'] / v['n'] if v['n'] else None)} | {v['fn']} |")
    wrong = [r for r in rows if not r["fallback"] and not r["correct_risk"]]
    if wrong:
        lines += ["", "風險判定不一致的題目（原文請開查核網址；報告不存訊息原文）：", "",
                  "| 來源 | 真值 | AI 判定 | 查核網址 |", "|---|---|---|---|"]
        for r in wrong:
            lines.append(f"| {r['source']} | {r['gold']} | {r['predicted']} | {r['url']} |")
    return lines + [""]


def report_markdown() -> str:
    meta = LAST.get("meta")
    if meta is None:
        return ""
    rows = LAST.get("rows") or []
    fresh = [r for r in rows if r["part"] == "fresh"]
    history = [r for r in rows if r["part"] == "history"]
    s_fresh, s_history = summarize(fresh), summarize(history)
    lines = [
        f"# 每週新查核自動評測 {meta['run_date']}",
        "",
        "（`app/services/weekly_eval.py` 自動產生；方法見 `docs/test/上線後準確率驗證計畫.md` 的 M5。"
        "真值是查核機構已發布的結論；AI 不經快取、不帶 web_search，量的是 AI 判讀本身，不含快取與來源分級。）",
        "",
        f"- 模型：{meta['provider']} `{meta['model']}`，推理強度 {meta['reasoning_effort']}，web_search 關"
        + ("" if set(meta["models_used"]) <= {meta["model"]} else
           "；實際回答：" + "、".join(f"`{m}` {n} 題" for m, n in sorted(meta["models_used"].items()))),
        f"- 本週範圍：{meta['window_start']} 起發布的查核結論（{meta['days']} 天）",
        f"- 額度：執行前{_usage_line(meta['usage_before'])}；執行後{_usage_line(meta['usage_after'])}；"
        f"本次上限 USD {meta['max_usd']:.2f}、保留 USD {meta['reserve_usd']:.2f} 給網站使用者",
        f"- 本週可出題的查核結論 {meta['available_fresh']} 題",
        f"- 結束原因：{STOP_REASONS.get(meta['stop_reason'], meta['stop_reason'])}",
    ]
    if meta["source_errors"]:
        lines.append("- 抓取失敗的來源：" + "；".join(f"{k}（{v}）" for k, v in meta["source_errors"].items()))
    lines.append("")
    lines += _part_section("本週新查核（主要數字）",
                           "模型訓練之後才出現的內容，最接近上線後的真實表現。", s_fresh, fresh)
    lines += _part_section("歷史抽樣（參考）",
                           "知識庫中查核機構已證實的訊息（風險題）與 Cofacts 認可為非謠言的訊息（安全題），2:1 抽樣；"
                           "可能出現在模型訓練資料中，數字偏樂觀。", s_history, history)
    lines += [
        "## 解讀注意",
        "",
        "1. Cofacts 的 RUMOR 一律記為 MISINFO，其中的詐騙訊息被 AI 判為 SCAM 算風險判定正確、三類不一致；"
        "所以以「風險判定一致率」為主要數字。",
        "2. Cofacts 的題目是使用者回報的原始訊息，常是詐騙對話中的一句（例如「你今天有時間去辦理一下預付卡嗎」），"
        "單看一句本來就難以判斷；MyGoPen 與台灣事實查核中心的題目是查核機構整理過的主張。兩者請分開看上面的來源表。",
        "3. 偽陰性是本系統唯一的絕對禁止項：每一筆都要打開查核網址確認。查核機構文章的偽陰性依準確率驗證計畫第 5 節做錯誤分析；"
        "Cofacts 的對話片段若單看該句確實無法判斷，在覆核紀錄註明後不列為缺陷。",
        "4. 網站上的燈號另外要求查核來源（沒有 Tier 1／2 來源不給綠燈），所以使用者實際看到的綠燈比這裡的 SAFE 判定更保守。",
        "",
    ]
    return "\n".join(lines)
