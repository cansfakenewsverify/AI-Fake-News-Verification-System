r"""
純模型比較（docs/test/模型比較計畫.md）：同一份凍結題庫、同一份系統提示，比閘道上能用的模型。

在 GitHub Actions 的 research workflow 上跑。步驟：

  freeze  從查核機構語料凍結 2,000 題（有風險 1,000、安全 1,000；同一則謠言的不同版本只抽一題；
          近 30 天的新查核全收、每類最多 200 題）→ docs/test/results/model_benchmark_items.csv
          （只有網址、雜湊、真值，不存原文）。需要語料與 text-embedding-3-small 向量（信心驗證的 fetch、embed）。
  run     一個模型答一遍（--model --effort --api responses|chat；--limit 50 先試跑）。
          逐題結果附加到 docs/test/results/model_benchmark/<模型>__<推理強度>.csv（可中斷續跑；連線錯誤的題目下次重試）。
          花錢的模型經過額度護欄：開始前與每 100 題讀 /me/usage、保留 USD 3；台灣時間週日不跑。
  report  所有跑過的模型 → docs/test/results/model_benchmark_<日期>.md：準確率、精確率／召回率／F1、漏判、
          無法查證、格式錯誤、耗時、花費、Wilson 信賴區間、與 gpt-5.6-luna（medium）的 McNemar 精確檢定；
          最後一列「完整系統」＝先查知識庫（只用比題目早的查核，相似度 ≥ 0.75 沿用結論），沒命中才用 gpt-5.6-luna。

系統提示與正式站相同（ai_service.SYSTEM_PROMPT_V41＋_build_prompt）；不帶 web_search、不經快取。
閘道的 OpenAI 模型走 Responses API（ai_service._responses_analyze，與正式站相同，逾時同 AI_TIMEOUT_SECONDS）；
本地與算力池模型走 chat/completions（同 scripts/llm_second_opinion.py）。

    python scripts/model_benchmark.py freeze
    python scripts/model_benchmark.py run --model gpt-5.6-luna --effort medium --api responses --limit 50 --max-usd 1
    python scripts/model_benchmark.py report
"""
import argparse
import csv
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import requests  # noqa: E402

import research_common as rc  # noqa: E402

ITEMS = rc.RESULTS / "model_benchmark_items.csv"
RUNS = rc.RESULTS / "model_benchmark"
BASELINE = ("gpt-5.6-luna", "medium")
N_RISKY = N_SAFE = 1000
RECENT_DAYS = 30
RECENT_SHARE = 0.2                 # 近期新查核每類最多佔幾成
GROUP_THRESHOLD = 0.90
SEED = "fnv-benchmark-v1"
CACHE_THRESHOLD = 0.75             # 完整系統的語意快取（settings.SIMILARITY_THRESHOLD）
MAX_CHARS = 20000                  # 與 /api/analyze/text 的輸入上限相同
CHAT_MAX_TOKENS = 4000
CHAT_TIMEOUT = 300
CHUNK = 20
CONCURRENCY = {"responses": 4, "chat": 2}
# 不花 OpenAI 額度的模型（學校算力池 Spark、閘道本地 Ollama）
FREE_MODELS = {"gemma-4-26b-a4b-it", "gpt-oss-120b", "nemotron-3-super-120b-a12b", "nemotron-3.5-bolt-74b-a9b",
               "gpt-oss:20b"}
DEFAULT_EST_USD = 0.002            # 不知道單價的模型，第一批的預估（之後改用 /me/usage 實際增加量）
ITEM_COLUMNS = ["item_id", "content_hash", "url", "source", "gold", "published", "recent", "freeze_date"]
RESULT_COLUMNS = ["item_id", "content_hash", "url", "source", "gold", "model", "effort", "api", "predicted",
                  "format_error", "detail", "error", "sec", "input_tokens", "output_tokens", "usd", "run_date"]


def slug(model: str, effort: str) -> str:
    return re.sub(r"[^A-Za-z0-9.\-]+", "_", f"{model}__{effort}")


# ── freeze ───────────────────────────────────────────────────

def pick_items(pool: pd.DataFrame, vectors: np.ndarray, n: int, today, recent_days: int = RECENT_DAYS,
               seed: str = SEED) -> pd.DataFrame:
    """同網址或相似度 ≥ 0.90 的同一群只抽一題；近期新查核先收（最多兩成），其餘依固定亂數順序補滿。"""
    pool = pool.reset_index(drop=True)
    groups = rc.group_ids(pool["url"].tolist(), vectors, GROUP_THRESHOLD)
    order = pool["content_hash"].map(lambda h: rc.stable_key(h, seed))
    reps = pool.assign(_group=groups, _order=order).sort_values("_order").drop_duplicates("_group")
    cutoff = (today - timedelta(days=recent_days)).isoformat()
    recent = reps[reps["published"].astype(str) >= cutoff].head(int(n * RECENT_SHARE))
    rest = reps.drop(recent.index).head(n - len(recent))
    picked = pd.concat([recent, rest])
    return picked.assign(recent=picked.index.isin(recent.index)).drop(columns=["_group", "_order"])


def cmd_freeze(args) -> int:
    if ITEMS.exists() and not args.force:
        raise SystemExit(f"{ITEMS} already exists (the item set is frozen); pass --force to rebuild it")
    corpus = rc.load_corpus()
    store = rc.EmbeddingStore(rc.DEFAULT_EMBED)
    today = rc.now_taipei().date()
    picked, dropped = [], {}
    for name, pool, n in (("risky", corpus[corpus["use"] == "kb"], args.risky),
                          ("safe", corpus[corpus["label"] == "SAFE"], args.safe)):
        has = pool["content_hash"].isin(store.vectors)
        dropped[name] = int((~has).sum())
        pool = pool[has]
        picked.append(pick_items(pool, store.matrix(pool["content_hash"].tolist()), n, today))
    items = pd.concat(picked, ignore_index=True)
    items = items.assign(_order=items["content_hash"].map(lambda h: rc.stable_key(h, SEED + "-order")))
    items = items.sort_values("_order").reset_index(drop=True)
    items["item_id"] = np.arange(1, len(items) + 1)
    items["gold"] = items["label"]
    items["freeze_date"] = today.isoformat()
    items[ITEM_COLUMNS].to_csv(ITEMS, index=False, encoding="utf-8")
    counts = items.groupby(["gold", "source"]).size()
    rc.update_status("benchmark_freeze", {"items": int(len(items)), "by": {f"{g}:{s}": int(n) for (g, s), n in counts.items()},
                                          "recent": int(items["recent"].sum()), "no_vector_dropped": dropped})
    rc.step_summary("## 模型比較：凍結題庫\n\n" + f"- {len(items)} 題：" + "、".join(f"{g} {s} {n}" for (g, s), n in counts.items())
                    + f"\n- 近 {RECENT_DAYS} 天的新查核 {int(items['recent'].sum())} 題\n- 檔案：`{ITEMS.relative_to(rc.REPO)}`")
    return 0


# ── run ──────────────────────────────────────────────────────

def full_prompt(text: str) -> str:
    """與正式站 AIService.analyze_content 相同的提示。"""
    from app.services.ai_service import SYSTEM_PROMPT_V41, AIService

    return f"{SYSTEM_PROMPT_V41}\n\n---\n\n{AIService.__new__(AIService)._build_prompt(text[:MAX_CHARS])}"


def responses_call(model: str, effort: str, prompt: str) -> Dict[str, Any]:
    from app.config import settings
    from app.services.ai_service import AIService

    ai = AIService.__new__(AIService)   # 只借用解析方法，不需要 provider 設定
    return ai._responses_analyze("CGU", (settings.CGU_BASE_URL or "").rstrip("/"), (settings.CGU_API_KEY or "").strip(),
                                 model, "" if effort == "none" else effort, prompt, None, False)


def chat_call(model: str, effort: str, prompt: str) -> Dict[str, Any]:
    from app.config import settings
    from app.services.ai_service import AIService

    body: Dict[str, Any] = {"model": model, "messages": [{"role": "user", "content": prompt}], "max_tokens": CHAT_MAX_TOKENS}
    if effort and effort != "none":
        body["reasoning_effort"] = effort
    r = requests.post(f"{(settings.CGU_BASE_URL or '').rstrip('/')}/chat/completions",
                      headers={"Authorization": f"Bearer {(settings.CGU_API_KEY or '').strip()}"}, json=body,
                      timeout=CHAT_TIMEOUT)
    r.raise_for_status()
    data = r.json()
    content = ((data.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
    if not content.strip():
        raise ValueError("empty answer")
    ai = AIService.__new__(AIService)
    result = AIService._parse_json_loose(content)
    ai._validate_result(result)
    usage = AIService._usage_of(data)
    if usage:
        result["usage"] = usage
    return result


def judge(item: Dict[str, Any], text: str, model: str, effort: str, api: str,
          call: Optional[Callable[[str, str, str], Dict[str, Any]]] = None) -> Dict[str, Any]:
    """答一題 → 結果列（不含原文與模型的說明文字）。連線錯誤記在 error（下次續跑會重試）；讀不到判定記 format_error。"""
    from app.workers.pandas_task_processor import _estimate_usd

    call = call or (responses_call if api == "responses" else chat_call)
    row = {k: item.get(k) for k in ("item_id", "content_hash", "url", "source", "gold")}
    row.update(model=model, effort=effort, api=api, predicted="", format_error=False, detail="", error="", sec=None,
               input_tokens=None, output_tokens=None, usd=None, run_date=rc.run_date())
    t0 = time.monotonic()
    try:
        res = call(model, effort, full_prompt(text))
        row["predicted"] = str(res.get("risk_type") or "").upper()
        usage = res.get("usage") or {}
        row["input_tokens"], row["output_tokens"] = usage.get("input_tokens"), usage.get("output_tokens")
        row["usd"] = 0.0 if model in FREE_MODELS else _estimate_usd(res, model)
    except requests.exceptions.HTTPError as exc:
        row["error"] = f"HTTP {getattr(exc.response, 'status_code', '?')}"
    except requests.exceptions.RequestException as exc:
        row["error"] = type(exc).__name__
    except (ValueError, KeyError, TypeError) as exc:   # JSON 讀不到或缺欄位：模型本身的問題，算格式錯誤
        row["format_error"] = True
        row["detail"] = f"{type(exc).__name__}: {exc}"[:100]   # 例外訊息只有欄位名稱或位置，不含回答內容
    row["sec"] = round(time.monotonic() - t0, 2)
    return row


def load_results(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=RESULT_COLUMNS)
    return pd.read_csv(path, dtype=str, keep_default_na=False)


def append_rows(path: Path, rows: List[Dict[str, Any]]) -> None:
    new = not path.exists()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=RESULT_COLUMNS, extrasaction="ignore")
        if new:
            w.writeheader()
        w.writerows(rows)


def compact_results(path: Path) -> None:
    """重試成功後，同一題只留最後一筆沒有連線錯誤的結果（都失敗就留最後一筆）。"""
    df = load_results(path)
    if df.empty:
        return
    df["_ok"] = df["error"].eq("")
    df = df.sort_values(["item_id", "_ok"], key=lambda s: s.astype(int) if s.name == "item_id" else s, kind="stable")
    df = df.drop_duplicates("item_id", keep="last").drop(columns=["_ok"])
    df.to_csv(path, index=False, encoding="utf-8")


def run_model(items: pd.DataFrame, texts: Dict[str, str], model: str, effort: str, api: str, limit: int,
              budget: "rc.Budget", out: Path, max_minutes: float, call=None, concurrency: Optional[int] = None
              ) -> Dict[str, Any]:
    from app.workers.pandas_task_processor import MODEL_PRICING_PER_1M

    done = load_results(out)
    finished = set(done.loc[done["error"].eq(""), "item_id"].astype(int))
    todo = [r for r in items.to_dict("records") if int(r["item_id"]) not in finished and r["content_hash"] in texts]
    if limit:
        todo = todo[:limit]
    known = model in FREE_MODELS or model in MODEL_PRICING_PER_1M
    per_call = 0.0 if model in FREE_MODELS else DEFAULT_EST_USD
    deadline = time.monotonic() + max_minutes * 60
    answered, errors = 0, 0
    with ThreadPoolExecutor(max_workers=concurrency or CONCURRENCY.get(api, 2)) as pool:
        for start in range(0, len(todo), CHUNK):
            chunk = todo[start:start + CHUNK]
            if time.monotonic() > deadline:
                budget.stop_reason = "time"
                break
            if not budget.guard(per_call * len(chunk), len(chunk)):
                break
            rows = list(pool.map(lambda it: judge(it, texts[it["content_hash"]], model, effort, api, call), chunk))
            append_rows(out, rows)
            usd = [float(r["usd"]) for r in rows if r["usd"] is not None]
            budget.record(sum(usd) + per_call * (len(rows) - len(usd)) * (0 if known else 1), len(rows))
            if known and usd:
                per_call = max(per_call, float(np.mean(usd)))
            elif not known and budget.done:
                per_call = max(DEFAULT_EST_USD, budget.spent / budget.done)
            answered += sum(1 for r in rows if not r["error"])
            errors += sum(1 for r in rows if r["error"])
            rc.log(f"  {start + len(chunk)}/{len(todo)} answered={answered} errors={errors} est_usd={budget.spent:.4f}")
            if all(r["error"] for r in rows):
                budget.stop_reason = "all_failed"
                break
    compact_results(out)
    return {"todo": len(todo), "answered": answered, "errors": errors}


def item_texts(items: pd.DataFrame) -> Tuple[Dict[str, str], int]:
    corpus = rc.load_corpus()
    by_hash = dict(zip(corpus["content_hash"], corpus["text"]))
    texts = {h: by_hash[h] for h in items["content_hash"] if h in by_hash}
    return texts, int(len(items) - len(texts))


def cmd_run(args) -> int:
    block = rc.spending_block_reason()
    if block and args.model not in FREE_MODELS:
        rc.step_summary(f"## 模型比較：`{args.model}`\n\n沒有執行：{block}")
        return 2
    items = pd.read_csv(ITEMS, dtype=str, keep_default_na=False)
    texts, missing = item_texts(items)
    out = RUNS / f"{slug(args.model, args.effort)}.csv"
    from app.workers.pandas_task_processor import MODEL_PRICING_PER_1M

    try:
        budget = rc.Budget(args.max_usd, free=args.model in FREE_MODELS,
                           price_known=args.model in MODEL_PRICING_PER_1M or args.model in FREE_MODELS)
    except rc.BudgetError as exc:
        rc.step_summary(f"## 模型比較：`{args.model}`\n\n沒有執行：{exc}")
        return 2
    got = run_model(items, texts, args.model, args.effort, args.api, args.limit, budget, out, args.max_minutes)
    spent = budget.summary()
    results = load_results(out)
    ok = results[results["error"].eq("")]
    usd = pd.to_numeric(ok["usd"], errors="coerce")
    left = int(len(items) - len(ok) - missing)
    per_item = float(usd.mean()) if usd.notna().any() else None
    if per_item is None and spent["usage_delta_usd"] and spent["items"]:
        per_item = spent["usage_delta_usd"] / spent["items"]
    secs = pd.to_numeric(ok["sec"], errors="coerce")
    data = {"model": args.model, "effort": args.effort, "api": args.api, "trial": bool(args.limit), "this_run": got,
            "answered_total": int(len(ok)), "items": int(len(items)), "missing_text": missing, "budget": spent,
            "usd_per_item": None if per_item is None else round(per_item, 6),
            "estimated_usd_for_rest": None if per_item is None else round(per_item * left, 3),
            "sec_p50": None if secs.empty else round(float(secs.median()), 2)}
    rc.update_status(f"benchmark_{slug(args.model, args.effort)}", data)
    lines = [f"## 模型比較：`{args.model}` 推理 {args.effort}（{args.api}）{'試跑' if args.limit else ''}", "",
             f"- 這次 {got['todo']} 題：回答 {got['answered']}、連線錯誤 {got['errors']}；累計已答 {len(ok)}／{len(items)}"
             + (f"（{missing} 題找不到原文）" if missing else ""),
             f"- 花費：估算 USD {spent['estimated_usd']}，/me/usage 增加 USD {spent['usage_delta_usd']}；剩 USD "
             f"{spent['usage_after'].get('remaining_usd')}；結束原因 {spent['stop_reason'] or '做完'}",
             f"- 每題耗時 p50 {data['sec_p50']} 秒；每題約 USD {data['usd_per_item']}；剩下 {left} 題約 USD {data['estimated_usd_for_rest']}"]
    rc.step_summary("\n".join(lines))
    return 0


# ── report ───────────────────────────────────────────────────

def summarize(df: pd.DataFrame) -> Dict[str, Any]:
    """一個模型的逐題結果（已排除連線錯誤）→ 表格欄位。無法查證與格式錯誤都算答錯（同每週評測）。"""
    n = len(df)
    gold_risky = df["gold"].map(rc.is_risky).to_numpy()
    pred = df["predicted"].str.upper()
    pred_risky = pred.isin(list(rc.RISKY)).to_numpy()
    pred_safe = (pred == "SAFE").to_numpy()
    correct = (gold_risky & pred_risky) | (~gold_risky & pred_safe)
    tp, fp = int((gold_risky & pred_risky).sum()), int((~gold_risky & pred_risky).sum())
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / int(gold_risky.sum()) if gold_risky.any() else None
    f1 = 2 * precision * recall / (precision + recall) if precision and recall else None
    unv = (pred == "UNVERIFIABLE").to_numpy()
    fmt_err = df["format_error"].astype(str).str.lower().eq("true").to_numpy()
    answered = pred_risky | pred_safe
    secs = pd.to_numeric(df["sec"], errors="coerce")
    usd = pd.to_numeric(df["usd"], errors="coerce")
    return {"n": n, "correct": int(correct.sum()), "ci": rc.wilson(int(correct.sum()), n), "precision": precision,
            "recall": recall, "f1": f1, "fn": int((gold_risky & pred_safe).sum()), "fp": fp,
            "unverifiable": int(unv.sum()), "answered": int(answered.sum()), "answered_correct": int(correct[answered].sum()),
            "format_error": int(fmt_err.sum()), "sec_p50": float(secs.median()) if secs.notna().any() else None,
            "sec_p90": float(secs.quantile(0.9)) if secs.notna().any() else None,
            "usd_per_item": float(usd.mean()) if usd.notna().any() else None,
            "correct_by_item": dict(zip(df["item_id"].astype(int), correct))}


def full_system(items: pd.DataFrame, baseline: pd.DataFrame) -> Optional[pd.DataFrame]:
    """完整系統：先查知識庫（時間切分，≥ 0.75 沿用查核結論），沒命中才用基準模型的判讀。需要語料與 small 向量。"""
    if baseline.empty or not rc.CORPUS.exists():
        return None
    corpus = rc.load_corpus()
    store = rc.EmbeddingStore(rc.DEFAULT_EMBED)
    ev = corpus[(corpus["use"] == "kb") & corpus["content_hash"].isin(store.vectors)].reset_index(drop=True)
    base = baseline[baseline["error"].eq("")].merge(items[["item_id", "published"]].astype({"item_id": str}),
                                                    on="item_id", how="left")
    base = base[base["content_hash"].isin(store.vectors)].reset_index(drop=True)
    if base.empty or ev.empty:
        return None
    sims, idx = rc.nearest_earlier(store.matrix(base["content_hash"].tolist()), base["published"].tolist(),
                                   base["content_hash"].tolist(), store.matrix(ev["content_hash"].tolist()),
                                   ev["verdict_date"].tolist(), ev["content_hash"].tolist(), k=1)
    hit = sims[:, 0] >= CACHE_THRESHOLD
    labels = ev["label"].to_numpy()
    predicted = [labels[idx[i, 0]] if hit[i] else p for i, p in enumerate(base["predicted"])]
    return base.assign(predicted=predicted, cache_hit=hit, model="完整系統", effort="", sec="", usd="")


def cmd_report(args) -> int:
    items = pd.read_csv(ITEMS, dtype=str, keep_default_na=False)
    runs = []
    for path in sorted(RUNS.glob("*.csv")):
        df = load_results(path)
        ok = df[df["error"].eq("")]
        if ok.empty:
            continue
        runs.append((ok["model"].iloc[0], ok["effort"].iloc[0], ok["api"].iloc[0], ok, int(len(df) - len(ok))))
    base_df = next((ok for m, e, _, ok, _ in runs if (m, e) == BASELINE), pd.DataFrame())
    full = full_system(items, base_df)
    day = rc.run_date()
    report = rc.RESULTS / f"model_benchmark_{day}.md"
    report.write_text(render_report(day, items, runs, base_df, full), encoding="utf-8")
    rc.update_status("benchmark_report", {"report": str(report.relative_to(rc.REPO)), "models": [f"{m} {e}" for m, e, *_ in runs]})
    rc.step_summary(f"## 模型比較報告\n\n`{report.relative_to(rc.REPO)}`（{len(runs)} 個模型設定）")
    return 0


def _row(name: str, s: Dict[str, Any], base: Optional[Dict[str, Any]], total: int, failed: int = 0) -> str:
    lo, hi = s["ci"]
    p = "—"
    if base is not None:
        common = set(s["correct_by_item"]) & set(base["correct_by_item"])
        b = sum(1 for i in common if s["correct_by_item"][i] and not base["correct_by_item"][i])
        c = sum(1 for i in common if base["correct_by_item"][i] and not s["correct_by_item"][i])
        p = f"{rc.mcnemar_exact(b, c):.3f}（+{b}／−{c}）"
    usd = "0" if s["usd_per_item"] == 0 else ("—" if s["usd_per_item"] is None else f"{s['usd_per_item']:.5f}")
    sec = "—" if s["sec_p50"] is None else f"{s['sec_p50']:.1f}／{s['sec_p90']:.1f}"
    answered_acc = rc.pct(s["answered_correct"] / s["answered"]) if s["answered"] else "—"
    return (f"| {name} | {s['n']}／{total}" + (f"（錯誤 {failed}）" if failed else "") + f" | {rc.pct(s['correct'] / s['n'] if s['n'] else None)}"
            f"（{rc.pct(lo)}–{rc.pct(hi)}） | {rc.pct(s['precision'])}／{rc.pct(s['recall'])}／{fmt(s['f1'])} | **{s['fn']}** "
            f"| {rc.pct(s['unverifiable'] / s['n'] if s['n'] else None)}（作答的 {answered_acc}） "
            f"| {rc.pct(s['format_error'] / s['n'] if s['n'] else None)} | {sec} | {usd} | {p} |")


def fmt(x: Optional[float]) -> str:
    return "—" if x is None else f"{x:.3f}"


def render_report(day: str, items: pd.DataFrame, runs: list, base_df: pd.DataFrame, full: Optional[pd.DataFrame]) -> str:
    total = len(items)
    counts = items.groupby("gold").size().to_dict()
    header = ["| 模型 | 題數 | 準確率（95% 信賴區間） | 精確率／召回率／F1 | 漏判 | 無法查證 | 格式錯誤 | 秒數 p50／p90 | 每題 USD | 對基準 McNemar p |",
              "|---|---|---|---|---:|---|---|---|---|---|"]
    lines = [
        f"# 純模型比較 {day}", "",
        "（`code/backend/scripts/model_benchmark.py` 由 GitHub Actions 的 research workflow 產生；方法見 `docs/test/模型比較計畫.md`。"
        "題目只存網址與雜湊：`docs/test/results/model_benchmark_items.csv`。）", "",
        f"- 題庫 {total} 題（" + "、".join(f"{k} {v}" for k, v in sorted(counts.items())) + f"），凍結於 {items['freeze_date'].iloc[0] if total else '—'}",
        "- 準確率：風險判定（有風險 vs 安全）一致的比例；判「無法查證」與格式錯誤都算錯（同每週評測）。精確率／召回率以「有風險」為正類",
        "- **漏判**：有風險判成安全（本系統唯一的絕對禁止項）。McNemar：與 `gpt-5.6-luna`（medium）逐題比較，"
        "（+只有這個模型答對／−只有基準答對）", "",
        "## 全部題目", "", *header,
    ]
    base_s = summarize(base_df) if not base_df.empty else None
    item_ids = items.assign(item_id=items["item_id"].astype(int))

    def subset_rows(mask_fn) -> List[str]:
        out = []
        keep = set(item_ids.loc[mask_fn(item_ids), "item_id"])
        base_sub = summarize(base_df[base_df["item_id"].astype(int).isin(keep)]) if base_s else None
        for model, effort, api, ok, failed in runs:
            sub = ok[ok["item_id"].astype(int).isin(keep)]
            if sub.empty:
                continue
            base = None if (model, effort) == BASELINE else base_sub
            out.append(_row(f"`{model}` {effort}（{api}）", summarize(sub), base, len(keep), failed if len(keep) == total else 0))
        if full is not None:
            sub = full[full["item_id"].astype(int).isin(keep)]
            if not sub.empty:
                s = summarize(sub)
                hits = int(sub["cache_hit"].sum())
                out.append(_row(f"**完整系統**（知識庫命中 {hits} 題，其餘用基準）", s, base_sub, len(keep)))
        return out

    lines += subset_rows(lambda df: df["item_id"] > 0)
    lines += ["", f"## 近期新查核（凍結前 {RECENT_DAYS} 天內發布，模型訓練之後才出現）", "", *header]
    lines += subset_rows(lambda df: df["recent"].astype(str).str.lower() == "true")
    lines += ["", "## Cofacts（同一來源、最難分）", "", *header]
    lines += subset_rows(lambda df: df["source"] == "Cofacts")
    if full is None:
        lines += ["", "完整系統：還沒有基準模型的結果或語料向量，這一列之後補上。"]
    lines += ["", "## 解讀注意", "",
              "1. 系統提示與正式站相同、不帶 web_search、不經快取；量的是模型本身。網站上另有知識庫、來源分級與燈號規則。",
              "2. 安全題取自 Cofacts 認可為非謠言的訊息與查核機構「查核結果為真」的報告；有風險題取自查核機構已證實的列。"
              "Cofacts 的 RUMOR 一律記為 MISINFO，所以只看風險判定、不看三類。",
              "3. 歷史題目可能在模型訓練資料中；模型之間的差距以「近期新查核」為準，但題數少、信賴區間寬。",
              "4. 連線錯誤（逾時、HTTP 錯誤）不算在題數內，括號內另列；格式錯誤（讀不到判定）算答錯。", ""]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("freeze")
    f.add_argument("--risky", type=int, default=N_RISKY)
    f.add_argument("--safe", type=int, default=N_SAFE)
    f.add_argument("--force", action="store_true")
    r = sub.add_parser("run")
    r.add_argument("--model", required=True)
    r.add_argument("--effort", default="medium", help="reasoning effort; none = do not send one")
    r.add_argument("--api", choices=["responses", "chat"], default="responses")
    r.add_argument("--limit", type=int, default=0, help=f"trial: only this many items (use {rc.TRIAL_ITEMS})")
    r.add_argument("--max-usd", type=float, default=1.0)
    r.add_argument("--max-minutes", type=float, default=320)
    sub.add_parser("report")
    args = parser.parse_args()
    return {"freeze": cmd_freeze, "run": cmd_run, "report": cmd_report}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
