r"""
信心程度驗證（docs/test/信心程度驗證計畫.md 第 3 節；嵌入模型比較併在這裡）。

在 GitHub Actions 的 research workflow 上跑（雲端 session 沒有金鑰、連不到 CGU 與查核網站）。步驟分開、可重跑：

  fetch    抓查核機構語料（含查核結論出現的日期）＋把每週評測的題目對回原文。不花額度。
  embed    為題目、語料、PF-2 改寫句算向量（--model；--limit 50 先試跑並估全部的花費；額度護欄見 research_common.Budget）
  analyze  離線計算，不花額度：
           重複內容只算一次 → 同網址＋相似度 ≥ 0.90 分群 → 依群分開發組／測試組（各半）
           → 時間切分的最近鄰（只比對查核結論早於題目日期的語料）
           → 只用開發組定門檻與話術原型 → 測試組套 evidence.assess → 第 4 節四項過關標準、可靠度圖／ECE／Brier
           → docs/test/results/confidence_validation_<日期>.md（報告）與 .csv（逐題，不含原文）

題目：每週評測（判定校準 v4 起，--since 2026-10-19）已判讀過的題目；AI 判定沿用 CSV，不再呼叫判讀模型。
訊息原文只存在 data/research/（gitignored，workflow 以 actions/cache 保存）。

    python scripts/confidence_validation.py fetch [--since 2026-10-19] [--refresh]
    python scripts/confidence_validation.py embed --model text-embedding-3-small [--limit 50] [--max-usd 1]
    python scripts/confidence_validation.py analyze [--models text-embedding-3-small,text-embedding-3-large,bge-m3:latest]
"""
import argparse
import contextlib
import math
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import research_common as rc  # noqa: E402

QUESTIONS = rc.RESEARCH / "questions.parquet"   # 含訊息原文，不進 git
WEEKLY_SINCE = "2026-10-19"          # 判定校準 v4（現行系統提示）的第一週
GROUP_THRESHOLD = 0.90               # 同一則謠言的不同版本
SENSITIVITY_THRESHOLD = 0.75         # 分群的敏感度檢查
SPLIT_SEED = "fnv-confidence-v1"
PRODUCTION_CACHE = 0.75              # settings.SIMILARITY_THRESHOLD（text-embedding-3-small 實測校準值）
PRODUCTION_MID, PRODUCTION_MARGIN = 0.65, 0.10
K_RISK, K_SAFE = 40, 12              # 話術原型與正常訊息原型的群數（同 evidence_confidence_study.py）
NEIGHBOURS = 5
MIN_N = 30                           # 開發組定門檻時，一個門檻至少要涵蓋幾題
MAX_MISSING_SHARE = 0.01             # 閘道拒絕少數文字時（沒有向量）最多容許幾成題目不算
TARGET_MID = 0.90                    # 標準 1：「中」的正確率
TARGET_HIGH = 0.95                   # 標準 2：「高」的結論一致率
GRID_SIM = [round(0.40 + 0.01 * i, 2) for i in range(60)]       # 0.40～0.99
GRID_MARGIN = [round(0.01 * i, 2) for i in range(31)]           # 0.00～0.30
SCORE_BINS = [0.5, 0.6, 0.7, 0.8, 0.9, 1.0001]
LEVELS = ("高", "中", "低")
CSV_KEEP = ["content_hash", "url", "source", "part", "run_date", "gold", "predicted", "confidence_score", "q_date",
            "group", "split"]


# ── fetch ────────────────────────────────────────────────────

def load_weekly(since: str = WEEKLY_SINCE, weekly_dir: Path = rc.WEEKLY) -> pd.DataFrame:
    frames = []
    for path in sorted(weekly_dir.glob("weekly_eval_*.csv")):
        if path.stem.replace("weekly_eval_", "") < since:
            continue
        frames.append(pd.read_csv(path, dtype=str, keep_default_na=False))
    if not frames:
        raise SystemExit(f"no weekly_eval_*.csv on or after {since} in {weekly_dir}")
    return pd.concat(frames, ignore_index=True)


def dedupe_questions(weekly: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    一字不差的重複（content_hash 相同）只算一次，取最早那一週的 AI 判定；AI 服務不可用的列不算。
    同內容但真值不同的整組剔除。另外統計同一則內容兩週判定不同的比例（計畫第 3 節第 4 步的附帶發現）。
    """
    valid = weekly[weekly["fallback"].str.lower() != "true"].copy()
    stats: Dict[str, Any] = {"rows": int(len(weekly)), "fallback_rows": int(len(weekly) - len(valid)),
                             "weeks": sorted(weekly["run_date"].unique().tolist())}
    kept, conflicting, repeated, verdict_changed, correctness_changed = [], 0, 0, 0, 0
    for _, group in valid.sort_values(["run_date", "part"]).groupby("content_hash", sort=False):
        if group["gold"].nunique() > 1:
            conflicting += 1
            continue
        if len(group) > 1:
            repeated += 1
            verdict_changed += int(group["predicted"].nunique() > 1)
            correctness_changed += int(group["correct_risk"].nunique() > 1)
        first = group.iloc[0].to_dict()
        first["repeats"] = int(len(group))
        kept.append(first)
    out = pd.DataFrame(kept)
    stats.update(unique=int(len(out)), conflicting_gold=conflicting, repeated=repeated,
                 verdict_changed=verdict_changed, correctness_changed=correctness_changed)
    return out, stats


def attach_texts(questions: pd.DataFrame, corpus: pd.DataFrame, cache=None) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    題目 → 原文與日期。語料裡有同一段文字就用語料（q_date＝發布日，Cofacts 為訊息建立日）；
    Cofacts 的題目不在語料裡（例如回報人數不到 3 的本週新查核）就以文章 id 單獨抓。
    """
    by_hash = corpus.drop_duplicates("content_hash").set_index("content_hash")
    texts, q_dates, verdict_dates, found = [], [], [], []
    for _, q in questions.iterrows():
        h = q["content_hash"]
        text, q_date, v_date, how = None, None, None, "missing"
        if h in by_hash.index:
            row = by_hash.loc[h]
            text, q_date, v_date, how = row["text"], row["published"], row["verdict_date"], "corpus"
        elif q["source"] == "Cofacts" and "/article/" in str(q["url"]):
            node = rc.fetch_cofacts_article(str(q["url"]).rsplit("/", 1)[-1], cache)
            body = ((node or {}).get("text") or "").strip()
            if body and rc.text_hash(body) == h:
                want = "RUMOR" if rc.is_risky(q["gold"]) else "NOT_RUMOR"
                text, q_date, how = body, str(node.get("createdAt") or "")[:10], "cofacts_article"
                v_date = rc.cofacts_verdict_dates([node], want).get(f"https://cofacts.tw/article/{node['id']}")
            else:
                how = "cofacts_text_changed" if body else "cofacts_missing"
        q_date = q_date or str(q.get("published") or "")[:10] or None
        texts.append(text)
        q_dates.append(q_date)
        verdict_dates.append(v_date)
        found.append(how)
    out = questions.copy()
    out["text"], out["q_date"], out["verdict_date"], out["found"] = texts, q_dates, verdict_dates, found
    stats = {f"{src}:{how}": int(n) for (src, how), n in out.groupby(["source", "found"]).size().items()}
    stats["no_date"] = int(out["text"].notna().sum() - (out["text"].notna() & out["q_date"].fillna("").ne("")).sum())
    return out, stats


def cmd_fetch(args) -> int:
    corpus, skipped = rc.fetch_corpus(refresh=args.refresh, cofacts_max=args.cofacts_max)
    rc.RESEARCH.mkdir(parents=True, exist_ok=True)
    corpus.to_parquet(rc.CORPUS, index=False)
    weekly = load_weekly(args.since)
    unique, dstats = dedupe_questions(weekly)
    questions, astats = attach_texts(unique, corpus)
    questions.to_parquet(QUESTIONS, index=False)
    by = {f"{s}:{l}:{u}": int(n) for (s, l, u), n in corpus.groupby(["source", "label", "use"]).size().items()}
    rc.update_status("confidence_fetch", {"since": args.since, "corpus_rows": int(len(corpus)), "corpus_by": by,
                                          "dedupe": dstats, "matching": astats})
    lines = ["## 信心驗證：抓資料", "", f"- 語料 {len(corpus):,} 列：" + "、".join(f"{k} {v:,}" for k, v in by.items()),
             f"- 每週評測（{args.since} 起）{dstats['rows']:,} 列，AI 不可用 {dstats['fallback_rows']}，"
             f"不同內容 {dstats['unique']:,}；兩週都出現 {dstats['repeated']}，其中判定不同 {dstats['verdict_changed']}、"
             f"一對一錯 {dstats['correctness_changed']}；真值矛盾剔除 {dstats['conflicting_gold']}",
             "- 對回原文：" + "、".join(f"{k} {v}" for k, v in sorted(astats.items()))]
    rc.step_summary("\n".join(lines))
    return 0


# ── embed ────────────────────────────────────────────────────

def texts_to_embed(corpus: pd.DataFrame, questions: pd.DataFrame) -> List[Tuple[str, str]]:
    """要算向量的文字（hash, text），依重要性排：題目 → 可入庫語料 → 已證實為真的語料 → PF-2 改寫句。"""
    ordered: List[Tuple[str, str]] = []
    seen = set()

    def add(text: Any) -> None:
        if isinstance(text, str) and text.strip():
            t = text.strip()
            h = rc.text_hash(t)
            if h not in seen:
                seen.add(h)
                ordered.append((h, t))

    for t in questions["text"]:
        add(t)
    for t in corpus.loc[corpus["use"] == "kb", "text"]:
        add(t)
    for t in corpus.loc[corpus["label"] == "SAFE", "text"]:
        add(t)
    for orig, para in rc.pf2_texts():
        add(orig)
        add(para)
    return ordered


def est_tokens(texts: Sequence[str]) -> int:
    # 中文約 1 token／字；多估兩成
    return int(sum(len(t[:2000]) for t in texts) * 1.2) + 1


def run_embedding(model: str, todo: List[Tuple[str, str]], store: "rc.EmbeddingStore", budget: "rc.Budget",
                  batch: int, embed=rc.embed_call, save_every: int = 20) -> Dict[str, Any]:
    price = rc.EMBED_MODELS[model]["usd_per_m"]
    tokens, done_chars, latencies, rejected = 0, 0, [], 0
    try:
        for n, start in enumerate(range(0, len(todo), batch), 1):
            chunk = todo[start:start + batch]
            texts = [t for _, t in chunk]
            if not budget.guard(est_tokens(texts) * price / 1e6, len(chunk)):
                rc.log(f"  stop: {budget.stop_reason}")
                break
            t0 = time.monotonic()
            vectors, used = embed(model, texts)
            latencies.append(time.monotonic() - t0)
            for (h, _), v in zip(chunk, vectors):
                if v is None:
                    rejected += 1
                else:
                    store.add(h, v)
            used = used or est_tokens(texts)
            tokens += used
            done_chars += sum(len(t[:2000]) for t in texts)
            budget.record(used * price / 1e6, len(chunk))
            if n % save_every == 0:
                store.save()
                rc.log(f"  embedded {min(start + batch, len(todo))}/{len(todo)} tokens={tokens}")
    finally:
        store.save()   # 中途失敗也保留已算好的向量（workflow 的 cache 照樣存）
    return {"tokens": tokens, "chars": done_chars, "rejected": rejected,
            "batch_seconds_p50": round(float(np.median(latencies)), 3) if latencies else None}


def cmd_embed(args) -> int:
    model = args.model
    if model not in rc.EMBED_MODELS:
        raise SystemExit(f"unknown embedding model {model}; choose from {list(rc.EMBED_MODELS)}")
    block = rc.spending_block_reason()
    if block and rc.EMBED_MODELS[model]["usd_per_m"] > 0:
        rc.step_summary(f"## 信心驗證：算向量\n\n沒有執行：{block}")
        return 2
    corpus = rc.load_corpus()
    questions = pd.read_parquet(QUESTIONS)
    wanted = texts_to_embed(corpus, questions)
    store = rc.EmbeddingStore(model)
    todo = [(h, t) for h, t in wanted if h not in store]
    trial = bool(args.limit)
    if trial:
        todo = todo[:args.limit]
    price = rc.EMBED_MODELS[model]["usd_per_m"]
    rc.log(f"[embed] {model}: wanted {len(wanted)}, already have {sum(h in store for h, _ in wanted)}, this run {len(todo)}")
    try:
        budget = rc.Budget(args.max_usd, free=price == 0)
    except rc.BudgetError as exc:
        rc.step_summary(f"## 信心驗證：算向量 `{model}`\n\n沒有執行：{exc}")
        return 2
    got = run_embedding(model, todo, store, budget, args.batch)
    remaining = [(h, t) for h, t in wanted if h not in store]
    latency = None
    if not trial and not remaining and args.latency_probe:
        latency = probe_latency(model, [t for _, t in wanted[:args.latency_probe]], budget)
    spent = budget.summary()
    per_char = got["tokens"] / got["chars"] if got["chars"] else None
    rest_tokens = int(sum(len(t[:2000]) for _, t in remaining) * per_char) if per_char else None
    data = {"model": model, "wanted": len(wanted), "embedded_total": len(store), "remaining": len(remaining),
            "this_run": got, "budget": spent, "trial": trial,
            "estimated_remaining_tokens": rest_tokens,
            "estimated_remaining_usd": None if rest_tokens is None else round(rest_tokens * price / 1e6, 4),
            "single_text_seconds": latency}
    rc.update_status(f"embed_{rc.EMBED_MODELS[model]['slug']}", data)
    lines = [f"## 信心驗證：算向量 `{model}`{'（試跑）' if trial else ''}", "",
             f"- 這次算了 {spent['items']} 筆，tokens {got['tokens']:,}；總共需要 {len(wanted):,} 筆，已有 {len(store):,}，"
             f"還差 {len(remaining):,}",
             f"- 花費：估算 USD {spent['estimated_usd']}，/me/usage 增加 USD {spent['usage_delta_usd']}"
             f"（同時段網站使用者的用量也算在內）；剩餘 USD {spent['usage_after'].get('remaining_usd')}",
             f"- 結束原因：{spent['stop_reason'] or '做完'}"]
    if data["estimated_remaining_usd"] is not None and remaining:
        lines.append(f"- 依這次的 tokens／字數推估：剩下的約 {rest_tokens:,} tokens、USD {data['estimated_remaining_usd']}")
    if latency:
        lines.append(f"- 單筆查詢延遲 p50 {latency['p50']} 秒、p90 {latency['p90']} 秒（{latency['n']} 次）")
    rc.step_summary("\n".join(lines))
    return 0


def probe_latency(model: str, texts: List[str], budget: "rc.Budget", embed=rc.embed_call) -> Optional[Dict[str, Any]]:
    """單筆 embedding 的延遲（網站上每則新查詢要算一次）；成本可忽略，仍經過額度護欄。"""
    secs = []
    price = rc.EMBED_MODELS[model]["usd_per_m"]
    for t in texts:
        if not budget.guard(est_tokens([t]) * price / 1e6):
            break
        t0 = time.monotonic()
        _, used = embed(model, [t])
        secs.append(time.monotonic() - t0)
        budget.record((used or est_tokens([t])) * price / 1e6, 1)
    if not secs:
        return None
    return {"n": len(secs), "p50": round(float(np.percentile(secs, 50)), 3), "p90": round(float(np.percentile(secs, 90)), 3)}


# ── analyze ──────────────────────────────────────────────────

def build_evidence(corpus: pd.DataFrame, questions: pd.DataFrame) -> pd.DataFrame:
    """
    模擬的知識庫：查核機構的可入庫列（只有 MISINFO／SCAM），加上語料裡沒有、但本來就在正式知識庫的歷史題
    （例如每日同步以「最近有新回覆」抓進來的 Cofacts 訊息）。
    """
    kb = corpus.loc[corpus["use"] == "kb", ["content_hash", "url", "source", "label", "verdict_date"]]
    extra = questions[(questions["found"] == "cofacts_article") & (questions["part"] == "history")
                      & questions["gold"].map(rc.is_risky) & questions["verdict_date"].notna()]
    extra = extra.rename(columns={"gold": "label"})[["content_hash", "url", "source", "label", "verdict_date"]]
    ev = pd.concat([kb, extra], ignore_index=True).drop_duplicates("content_hash").reset_index(drop=True)
    return ev


def assign_groups(q: pd.DataFrame, vectors: np.ndarray) -> Tuple[List[int], List[str], Dict[str, Any]]:
    """同網址＋相似度 ≥ 0.90 分群，依群分開發組／測試組；另以 0.75 分群看最大的群會不會連成一大串。"""
    groups = rc.group_ids(q["url"].tolist(), vectors, GROUP_THRESHOLD)
    hashes = q["content_hash"].tolist()
    split = ["dev" if int(rc.stable_key(hashes[g], SPLIT_SEED), 16) % 2 == 0 else "test" for g in groups]
    loose = rc.group_ids(q["url"].tolist(), vectors, SENSITIVITY_THRESHOLD)
    sizes = pd.Series(groups).value_counts()
    loose_sizes = pd.Series(loose).value_counts()
    stats = {"groups": int(len(sizes)), "largest_group": int(sizes.max()) if len(sizes) else 0,
             "multi_item_groups": int((sizes > 1).sum()),
             "groups_at_075": int(len(loose_sizes)), "largest_group_at_075": int(loose_sizes.max()) if len(loose_sizes) else 0}
    return groups, split, stats


def derive_threshold(values: np.ndarray, positive: np.ndarray, mask: np.ndarray, grid: Sequence[float],
                     target: float, min_n: int = MIN_N) -> float:
    """開發組：涵蓋至少 min_n 題、且其中真的有風險的比例 ≥ target 的最低門檻；找不到 → inf（規則停用）。"""
    for t in grid:
        sel = mask & (values >= t)
        n = int(sel.sum())
        if n >= min_n and positive[sel].mean() >= target:
            return float(t)
    return math.inf


def kmeans_centroids(matrix: np.ndarray, k: int, seed: int = 7) -> np.ndarray:
    from sklearn.cluster import KMeans

    k = max(1, min(k, len(matrix)))
    model = KMeans(n_clusters=k, n_init=3, random_state=seed).fit(matrix)
    c = model.cluster_centers_.astype(np.float32)
    return c / np.maximum(np.linalg.norm(c, axis=1, keepdims=True), 1e-12)


def max_sim_to(rows: np.ndarray, targets: np.ndarray, chunk: int = 2048) -> np.ndarray:
    if len(targets) == 0 or len(rows) == 0:
        return np.full(len(rows), -1.0, dtype=np.float32)
    out = np.empty(len(rows), dtype=np.float32)
    for start in range(0, len(rows), chunk):
        out[start:start + chunk] = (rows[start:start + chunk] @ targets.T).max(axis=1)
    return out


@contextlib.contextmanager
def evidence_thresholds(mid: float, margin: float):
    """evidence.assess 讀模組常數 MID_SIMILARITY／PATTERN_MARGIN：暫時換成開發組定出的值。"""
    from app.services import evidence

    old = evidence.MID_SIMILARITY, evidence.PATTERN_MARGIN
    evidence.MID_SIMILARITY, evidence.PATTERN_MARGIN = mid, margin
    try:
        yield evidence
    finally:
        evidence.MID_SIMILARITY, evidence.PATTERN_MARGIN = old


def assess_all(predicted: Sequence[str], sims: np.ndarray, idx: np.ndarray, ev_labels: Sequence[str],
               margin: np.ndarray, cache_hit: np.ndarray, mid: float, margin_t: float) -> pd.DataFrame:
    """每一題的信心等級與網站最後的判定：語意快取命中 → 沿用查核結論（高）；否則 AI 判定＋evidence.assess。"""
    out = []
    with evidence_thresholds(mid, margin_t) as evidence:
        for i, pred in enumerate(predicted):
            if cache_hit[i]:
                out.append({"level": "高", "basis": "factchecked", "final": ev_labels[idx[i, 0]]})
                continue
            neighbours = [{"similarity": float(sims[i, j]), "risk_type": ev_labels[idx[i, j]]}
                          for j in range(sims.shape[1]) if idx[i, j] >= 0]
            res = evidence.assess(pred, neighbours=neighbours, margin=float(margin[i]), ai_checked=True)
            out.append({"level": res["level"], "basis": res["basis"], "final": pred})
    return pd.DataFrame(out)


def risk_correct(final: pd.Series, gold: pd.Series) -> np.ndarray:
    f = final.str.upper()
    g = gold.str.upper()
    return ((f.isin(rc.RISKY) & g.isin(rc.RISKY)) | ((f == "SAFE") & (g == "SAFE"))).to_numpy()


def criteria(frame: pd.DataFrame, mask: np.ndarray) -> Dict[str, Any]:
    """第 4 節四項標準（frame 需有 level、basis、final、predicted、gold、cache_hit、correct）。"""
    f = frame[mask]
    gold_risky = f["gold"].map(rc.is_risky).to_numpy()
    ai_risky = f["predicted"].map(rc.is_risky).to_numpy()
    cache = f["cache_hit"].to_numpy()
    correct = f["correct"].to_numpy()
    level = f["level"].to_numpy()

    pop1 = ~cache & ai_risky
    mid, low = pop1 & (level == "中"), pop1 & (level == "低")
    k_mid, n_mid, k_low, n_low = int(correct[mid].sum()), int(mid.sum()), int(correct[low].sum()), int(low.sum())
    ci_mid, ci_low = rc.wilson(k_mid, n_mid), rc.wilson(k_low, n_low)
    c1 = {"mid": (k_mid, n_mid), "low": (k_low, n_low), "ci_mid": ci_mid, "ci_low": ci_low,
          "pass": bool(n_mid and n_low and k_mid / n_mid >= TARGET_MID and ci_mid[0] > ci_low[1])}

    k2, n2 = int(gold_risky[cache].sum()), int(cache.sum())
    exact2 = int((f["final"][cache].str.upper() == f["gold"][cache].str.upper()).sum())
    c2 = {"hit": (k2, n2), "exact": exact2, "pass": bool(n2 and k2 / n2 >= TARGET_HIGH)}

    safe = ~cache & (f["predicted"].str.upper() == "SAFE").to_numpy()
    conflict = safe & (f["basis"].to_numpy() == "conflict")
    quiet = safe & ~conflict
    kc, nc, kq, nq = int(gold_risky[conflict].sum()), int(conflict.sum()), int(gold_risky[quiet].sum()), int(quiet.sum())
    rate_c = kc / nc if nc else None
    rate_q = kq / nq if nq else None
    c3_pass = bool(rate_c is not None and rate_q is not None and rate_c > 0 and rate_c >= 2 * rate_q)
    unv = ~cache & (f["predicted"].str.upper() == "UNVERIFIABLE").to_numpy()
    unv_conflict = unv & (f["basis"].to_numpy() == "conflict")
    c3 = {"conflict": (kc, nc), "quiet": (kq, nq), "ratio": (rate_c / rate_q) if rate_c is not None and rate_q else None,
          "unverifiable_conflict": (int(gold_risky[unv_conflict].sum()), int(unv_conflict.sum())),
          "unverifiable_quiet": (int(gold_risky[unv & ~unv_conflict].sum()), int((unv & ~unv_conflict).sum())),
          "pass": c3_pass}

    system_risky = cache | (~cache & ai_risky)
    k4 = int((system_risky & np.isin(level, ["中", "高"])).sum())
    n4 = int(system_risky.sum())
    c4 = {"share": (k4, n4), "pass": bool(n4 and k4 / n4 >= 0.20)}
    return {"c1": c1, "c2": c2, "c3": c3, "c4": c4, "n": int(mask.sum()), "cache_hits": n2,
            "all_pass": c1["pass"] and c2["pass"] and c3["pass"] and c4["pass"]}


def reliability_levels(frame: pd.DataFrame, dev: np.ndarray, test: np.ndarray) -> Dict[str, Any]:
    """等級的可靠度：開發組各等級的正確率當作該等級的機率，看測試組實際正確率差多少（ECE）與 Brier。"""
    answered = frame["final"].str.upper().isin(list(rc.RISKY) + ["SAFE"]).to_numpy()
    correct = frame["correct"].to_numpy()
    gold_risky = frame["gold"].map(rc.is_risky).to_numpy()
    final_risky = frame["final"].map(rc.is_risky).to_numpy()
    p_dev, rows = {}, []
    for level in LEVELS:
        d = dev & answered & (frame["level"].to_numpy() == level)
        p_dev[level] = float(correct[d].mean()) if d.any() else None
    t = test & answered
    n_t = int(t.sum())
    ece = 0.0
    for level in LEVELS:
        sel = t & (frame["level"].to_numpy() == level)
        n = int(sel.sum())
        acc = float(correct[sel].mean()) if n else None
        rows.append({"level": level, "p_dev": p_dev[level], "n_test": n, "acc_test": acc})
        if n and p_dev[level] is not None:
            ece += n / n_t * abs(acc - p_dev[level])
    p_correct = np.array([p_dev.get(lv) if p_dev.get(lv) is not None else 0.5 for lv in frame["level"]], dtype=float)
    p_risky = np.where(final_risky, p_correct, 1 - p_correct)
    brier = float(np.mean((p_risky[t] - gold_risky[t]) ** 2)) if n_t else None
    base = float(gold_risky[dev & answered].mean()) if (dev & answered).any() else 0.5
    brier_base = float(np.mean((base - gold_risky[t]) ** 2)) if n_t else None
    return {"rows": rows, "ece": round(ece, 4) if n_t else None, "brier": brier, "brier_base_rate": brier_base,
            "base_rate": base}


def reliability_ai_score(frame: pd.DataFrame, test: np.ndarray) -> Dict[str, Any]:
    """AI 自評分數（confidence_score）的可靠度圖、ECE、Brier、AUROC 與綠燈門檻表（與 embedding 無關）。"""
    score = pd.to_numeric(frame["confidence_score"], errors="coerce").to_numpy()
    pred = frame["predicted"].str.upper()
    answered = pred.isin(list(rc.RISKY) + ["SAFE"]).to_numpy() & ~np.isnan(score) & test
    correct = risk_correct(frame["predicted"], frame["gold"])
    gold_risky = frame["gold"].map(rc.is_risky).to_numpy()
    bins, ece, n_all = [], 0.0, int(answered.sum())
    for lo, hi in zip(SCORE_BINS[:-1], SCORE_BINS[1:]):
        sel = answered & (score >= lo) & (score < hi)
        n = int(sel.sum())
        acc = float(correct[sel].mean()) if n else None
        conf = float(score[sel].mean()) if n else None
        bins.append({"range": f"{lo:.1f}–{min(hi, 1.0):.1f}", "n": n, "mean_score": conf, "acc": acc})
        if n:
            ece += n / n_all * abs(acc - conf)
    below = answered & (score < SCORE_BINS[0])
    p_risky = np.where(pred.isin(list(rc.RISKY)).to_numpy(), score, 1 - score)
    green = []
    safe = answered & (pred == "SAFE").to_numpy()
    for t in (0.6, 0.7, 0.8, 0.9):
        kept = safe & (score >= t)
        green.append({"threshold": t, "kept": int(kept.sum()), "of": int(safe.sum()),
                      "precision": float((~gold_risky[kept]).mean()) if kept.any() else None})
    return {"n": n_all, "below_0_5": int(below.sum()), "bins": bins, "ece": round(ece, 4) if n_all else None,
            "brier": float(np.mean((p_risky[answered] - gold_risky[answered]) ** 2)) if n_all else None,
            "auroc": rc.auroc(score[answered], correct[answered]), "green": green}


def search_ms(Q: np.ndarray, E: np.ndarray, n: int = 200) -> Optional[float]:
    """在整個知識庫裡找前 5 名最近鄰（numpy 暴力法）的每題毫秒數 p50；正式站用 pgvector，只看相對差距。"""
    if len(Q) == 0 or len(E) == 0:
        return None
    times = []
    for q in Q[:n]:
        t0 = time.perf_counter()
        s = E @ q
        np.argpartition(-s, min(4, len(s) - 1))[:5]
        times.append((time.perf_counter() - t0) * 1000)
    return round(float(np.median(times)), 2)


def evaluate_model(model: str, q: pd.DataFrame, ev: pd.DataFrame, safe_rows: pd.DataFrame,
                   store: "rc.EmbeddingStore", production_prototypes: Optional[Tuple[np.ndarray, np.ndarray]] = None
                   ) -> Dict[str, Any]:
    ev = ev[ev["content_hash"].isin(store.vectors)].reset_index(drop=True)
    safe_rows = safe_rows[safe_rows["content_hash"].isin(store.vectors)].reset_index(drop=True)
    Q = store.matrix(q["content_hash"].tolist())
    E = store.matrix(ev["content_hash"].tolist())
    S = store.matrix(safe_rows["content_hash"].tolist()) if len(safe_rows) else np.zeros((0, Q.shape[1]), np.float32)
    dev = (q["split"] == "dev").to_numpy()
    test = ~dev

    sims, idx = rc.nearest_earlier(Q, q["q_date"].tolist(), q["content_hash"].tolist(),
                                   E, ev["verdict_date"].tolist(), ev["content_hash"].tolist(), k=NEIGHBOURS)
    nn = sims[:, 0]
    gold_risky = q["gold"].map(rc.is_risky).to_numpy()
    ai_risky = q["predicted"].map(rc.is_risky).to_numpy()

    # 話術原型：只用開發組那一側的語料（排除測試組題目本身、同網址、與測試組題目相似度 ≥ 0.90 的列）
    test_hashes, test_urls = set(q.loc[test, "content_hash"]), set(q.loc[test, "url"])
    Qt = Q[test]

    def train_mask(rows: pd.DataFrame, M: np.ndarray) -> np.ndarray:
        leak = rows["content_hash"].isin(test_hashes).to_numpy() | rows["url"].isin(test_urls).to_numpy()
        return ~leak & (max_sim_to(M, Qt) < GROUP_THRESHOLD)

    risk_train, safe_train = train_mask(ev, E), train_mask(safe_rows, S)
    C_risk = kmeans_centroids(E[risk_train], K_RISK)
    C_safe = kmeans_centroids(S[safe_train], K_SAFE) if safe_train.any() else None
    margin = (Q @ C_risk.T).max(axis=1) - ((Q @ C_safe.T).max(axis=1) if C_safe is not None else 0)

    production = model == rc.DEFAULT_EMBED
    t_cache = PRODUCTION_CACHE if production else derive_threshold(nn, gold_risky, dev, GRID_SIM, TARGET_HIGH)
    cache_hit = nn >= t_cache
    pop = dev & ~cache_hit & ai_risky
    t_mid = derive_threshold(nn, gold_risky, pop, [t for t in GRID_SIM if t < t_cache], TARGET_MID)
    t_margin = derive_threshold(margin, gold_risky, pop, GRID_MARGIN, TARGET_MID)

    def frame_for(mid: float, margin_t: float, margins: np.ndarray) -> pd.DataFrame:
        a = assess_all(q["predicted"].str.upper().tolist(), sims, idx, ev["label"].tolist(), margins, cache_hit,
                       mid, margin_t)
        f = q[["gold", "predicted", "confidence_score"]].reset_index(drop=True).copy()
        f[["level", "basis", "final"]] = a[["level", "basis", "final"]]
        f["cache_hit"] = cache_hit
        f["correct"] = risk_correct(f["final"], f["gold"])
        return f

    frame = frame_for(t_mid, t_margin, margin)
    result = {
        "model": model, "dims": int(Q.shape[1]), "evidence_rows": int(len(ev)), "safe_rows": int(len(safe_rows)),
        "prototype_rows": {"risk": int(risk_train.sum()), "safe": int(safe_train.sum())},
        "thresholds": {"cache": t_cache, "mid": t_mid, "margin": t_margin},
        "no_earlier_evidence": int((idx[:, 0] < 0).sum()),
        "all": criteria(frame, test), "novel": criteria(frame, test & ~cache_hit),
        "levels": level_table(frame, test), "reliability": reliability_levels(frame, dev, test),
        "pf2": pf2_hit_rate(store, t_cache), "search_ms_p50": search_ms(Q, E),
        "per_question": frame[["level", "basis", "final"]].assign(nn_sim=np.round(nn, 4)),
    }
    if production and production_prototypes is not None:
        pr, ps = production_prototypes
        if pr.shape[1] == Q.shape[1]:
            prod_margin = (Q @ pr.T).max(axis=1) - (Q @ ps.T).max(axis=1)
            prod = frame_for(PRODUCTION_MID, PRODUCTION_MARGIN, prod_margin)
            result["production"] = criteria(prod, test)
    return result


def level_table(frame: pd.DataFrame, test: np.ndarray) -> List[Dict[str, Any]]:
    """測試組：等級 × AI 判定 → 題數與風險判定正確率。"""
    rows = []
    f = frame[test]
    kind = np.where(f["cache_hit"], "語意快取（沿用查核結論）",
                    np.where(f["predicted"].map(rc.is_risky), "AI 判有風險",
                             np.where(f["predicted"].str.upper() == "SAFE", "AI 判安全", "AI 判無法查證")))
    for (k, level, basis), g in f.assign(kind=kind).groupby(["kind", "level", "basis"]):
        rows.append({"kind": k, "level": level, "basis": basis, "n": int(len(g)), "correct": int(g["correct"].sum())})
    return rows


def pf2_hit_rate(store: "rc.EmbeddingStore", threshold: float) -> Optional[Dict[str, Any]]:
    pairs = [(rc.text_hash(o.strip()), rc.text_hash(p.strip())) for o, p in rc.pf2_texts() if o.strip() and p.strip()]
    pairs = [(a, b) for a, b in pairs if a in store and b in store]
    if not pairs:
        return None
    sims = [float(store.matrix([a])[0] @ store.matrix([b])[0]) for a, b in pairs]
    return {"pairs": len(pairs), "hits": int(sum(s >= threshold for s in sims)), "median": round(float(np.median(sims)), 4)}


def load_production_prototypes() -> Optional[Tuple[np.ndarray, np.ndarray]]:
    path = rc.BACKEND / "data" / "claim_prototypes.npz"
    if not path.exists():
        return None
    with np.load(path) as data:
        return data["risk"].astype(np.float32), data["safe"].astype(np.float32)


def cmd_analyze(args) -> int:
    corpus = rc.load_corpus()
    questions = pd.read_parquet(QUESTIONS)
    q = questions[questions["text"].notna() & questions["q_date"].fillna("").ne("")].reset_index(drop=True)
    excluded = {"no_text": int(questions["text"].isna().sum()),
                "no_date": int((questions["text"].notna() & questions["q_date"].fillna("").eq("")).sum())}
    group_store = rc.EmbeddingStore(args.group_model)
    has_vector = q["content_hash"].isin(group_store.vectors)
    if has_vector.mean() < 1 - MAX_MISSING_SHARE:
        raise SystemExit(f"{int((~has_vector).sum())} questions have no {args.group_model} vector: run the embed task first")
    excluded["no_vector"] = int((~has_vector).sum())   # 閘道拒絕的少數文字
    q = q[has_vector].reset_index(drop=True)
    q["group"], q["split"], gstats = assign_groups(q, group_store.matrix(q["content_hash"].tolist()))
    ev = build_evidence(corpus, questions)
    safe_rows = corpus.loc[corpus["label"] == "SAFE", ["content_hash", "url"]]
    protos = load_production_prototypes()

    results = []
    for model in [m.strip() for m in args.models.split(",") if m.strip()]:
        store = rc.EmbeddingStore(model)
        has = q["content_hash"].isin(store.vectors)
        if has.mean() < 1 - MAX_MISSING_SHARE:
            rc.log(f"[analyze] skip {model}: {int((~has).sum())} questions have no vector")
            results.append({"model": model, "skipped": f"{int((~has).sum())} 題沒有向量（先跑 embed）"})
            continue
        rc.log(f"[analyze] {model}")
        r = evaluate_model(model, q[has], ev, safe_rows, store, protos)
        r["per_question"].index = q.index[has.to_numpy()]
        r["questions_without_vector"] = int((~has).sum())
        results.append(r)
    ai = reliability_ai_score(q.reset_index(drop=True), (q["split"] == "test").to_numpy())

    day = rc.run_date()
    report = rc.RESULTS / f"confidence_validation_{day}.md"
    per_q = rc.RESULTS / f"confidence_validation_{day}.csv"
    out = q[CSV_KEEP].copy()
    for r in results:
        if "per_question" in r:
            slug = rc.EMBED_MODELS.get(r["model"], {"slug": r["model"]})["slug"]
            pq = r.pop("per_question")
            for col in ("nn_sim", "level", "basis", "final"):
                out[f"{col}_{slug}"] = pq[col].reindex(out.index)
    out.to_csv(per_q, index=False, encoding="utf-8")
    meta = {"since": args.since_note, "questions": int(len(questions)), "used": int(len(q)), "excluded": excluded,
            "groups": gstats, "dev": int((q["split"] == "dev").sum()), "test": int((q["split"] == "test").sum()),
            "test_risky": int((q["split"].eq("test") & q["gold"].map(rc.is_risky)).sum()),
            "evidence_rows": int(len(ev)), "fetch": rc_status("confidence_fetch")}
    report.write_text(render_report(day, meta, results, ai), encoding="utf-8")
    rc.update_status("confidence_analyze", {
        "report": str(report.relative_to(rc.REPO)), "per_question": str(per_q.relative_to(rc.REPO)),
        "summary": {r["model"]: (r.get("skipped") or {"pass": r["all"]["all_pass"], "thresholds": r["thresholds"]})
                    for r in results}})
    rc.step_summary(summary_table(results) + f"\n\n報告：`{report.relative_to(rc.REPO)}`")
    return 0


def rc_status(section: str) -> Dict[str, Any]:
    import json

    if not rc.STATUS.exists():
        return {}
    return json.loads(rc.STATUS.read_text(encoding="utf-8")).get(section, {})


# ── 報告 ─────────────────────────────────────────────────────

def _yn(ok: bool) -> str:
    return "**過**" if ok else "沒過"


def _t(x: float) -> str:
    return "停用（開發組找不到合格門檻）" if math.isinf(x) else f"{x:.2f}"


def summary_table(results: List[Dict[str, Any]]) -> str:
    lines = ["## 信心驗證結論（測試組；四項全過才算過關）", "",
             "| embedding | 1「中」比「低」準 | 2「高」一致率 | 3 衝突提醒 | 4「中」以上比例 | 結果 |", "|---|---|---|---|---|---|"]
    for r in results:
        if "skipped" in r:
            lines.append(f"| `{r['model']}` | 略過：{r['skipped']} |  |  |  |  |")
            continue
        a = r["all"]
        c1, c2, c3, c4 = a["c1"], a["c2"], a["c3"], a["c4"]
        ratio = (f"{c3['ratio']:.1f} 倍" if c3["ratio"] is not None
                 else "沒提醒的都安全" if c3["pass"] else "—")
        lines.append(
            f"| `{r['model']}` | 中 {rate_short(*c1['mid'])} vs 低 {rate_short(*c1['low'])} {_yn(c1['pass'])} "
            f"| {rate_short(*c2['hit'])} {_yn(c2['pass'])} | {ratio} {_yn(c3['pass'])} "
            f"| {rate_short(*c4['share'])} {_yn(c4['pass'])} | {'**過關**' if a['all_pass'] else '沒過關'} |")
    return "\n".join(lines)


def rate_short(k: int, n: int) -> str:
    return f"{rc.pct(k / n) if n else '—'}（{k}／{n}）"


def render_report(day: str, meta: Dict[str, Any], results: List[Dict[str, Any]], ai: Dict[str, Any]) -> str:
    f = meta.get("fetch") or {}
    d = f.get("dedupe") or {}
    g = meta["groups"]
    lines = [
        f"# 信心程度驗證 {day}", "",
        "（`code/backend/scripts/confidence_validation.py` 由 GitHub Actions 的 research workflow 產生；方法見 "
        "`docs/test/信心程度驗證計畫.md` 第 3 節，過關標準是第 4 節草案。報告與逐題 CSV 不含訊息原文，只有查核網址與雜湊。）", "",
        summary_table(results), "",
        "## 資料", "",
        f"- 題目：每週評測 {', '.join(d.get('weeks', []))} 的逐題 CSV，共 {d.get('rows', '?')} 列；AI 服務不可用 "
        f"{d.get('fallback_rows', '?')} 列不算；不同內容 {d.get('unique', '?')} 則（真值矛盾剔除 {d.get('conflicting_gold', '?')}）",
        f"- 重複內容：{d.get('repeated', '?')} 則出現不只一週，其中 **{d.get('verdict_changed', '?')} 則 AI 判定不同**、"
        f"{d.get('correctness_changed', '?')} 則一次判對一次判錯（取最早那一週的判定）",
        "- 對回原文：" + "、".join(f"{k} {v}" for k, v in sorted((f.get("matching") or {}).items())),
        f"- 可用題目 {meta['used']}（沒有原文 {meta['excluded']['no_text']}、沒有日期 {meta['excluded']['no_date']}、"
        f"沒有向量 {meta['excluded'].get('no_vector', 0)} 不算）",
        f"- 分群（同網址或相似度 ≥ {GROUP_THRESHOLD}，以 `{rc.DEFAULT_EMBED}` 計算）：{g['groups']} 群，"
        f"{g['multi_item_groups']} 群不只一題，最大一群 {g['largest_group']} 題；敏感度檢查（≥ {SENSITIVITY_THRESHOLD}）："
        f"{g['groups_at_075']} 群、最大一群 {g['largest_group_at_075']} 題",
        f"- 開發組 {meta['dev']} 題、測試組 {meta['test']} 題（其中有風險 {meta['test_risky']}）；同一群一定在同一組",
        f"- 模擬的知識庫：查核機構可入庫列 {meta['evidence_rows']}（只有 MISINFO／SCAM）；每一題只比對查核結論日期早於該題日期的列",
        "",
    ]
    for r in results:
        if "skipped" in r:
            lines += [f"## `{r['model']}`", "", f"略過：{r['skipped']}", ""]
            continue
        th = r["thresholds"]
        lines += [
            f"## `{r['model']}`（{r['dims']} 維）", "",
            "開發組定出的參數（報告只列測試組的數字）：", "",
            f"- 「高」語意快取門檻：{_t(th['cache'])}"
            + ("（正式站現值，固定不重算）" if r["model"] == rc.DEFAULT_EMBED
               else f"（開發組中結論一致率 ≥ {TARGET_HIGH:.0%} 的最低門檻）"),
            f"- 「中」相近案例門檻：{_t(th['mid'])}；話術差距門檻：{_t(th['margin'])}"
            f"（開發組 AI 判有風險的題目中，正確率 ≥ {TARGET_MID:.0%} 且至少 {MIN_N} 題的最低門檻）",
            f"- 話術原型：{K_RISK} 群取自 {r['prototype_rows']['risk']} 列可入庫語料、正常訊息原型 {K_SAFE} 群取自 "
            f"{r['prototype_rows']['safe']} 列已證實為真的語料（排除測試組題目、同網址與相似度 ≥ {GROUP_THRESHOLD} 的列）",
            f"- 沒有任何更早查核可比對的題目：{r['no_earlier_evidence']}", "",
            "| 標準 | 全部題目（看這一欄） | 全新謠言（沒有更早的相近查核，即語意快取沒命中） |", "|---|---|---|",
        ]
        a, nv = r["all"], r["novel"]
        lines += [
            f"| 1「中」正確率 ≥ 90% 且高於「低」 | 中 {rc.rate_cell(*a['c1']['mid'])}；低 {rc.rate_cell(*a['c1']['low'])} → "
            f"{_yn(a['c1']['pass'])} | 中 {rc.rate_cell(*nv['c1']['mid'])}；低 {rc.rate_cell(*nv['c1']['low'])} |",
            f"| 2「高」結論一致 ≥ 95% | {rc.rate_cell(*a['c2']['hit'])}（三類完全一致 {a['c2']['exact']}）→ {_yn(a['c2']['pass'])} | — |",
            f"| 3 衝突提醒中真的有風險 ≥ 沒提醒的 2 倍 | 有提醒 {rc.rate_cell(*a['c3']['conflict'])}；沒提醒 "
            f"{rc.rate_cell(*a['c3']['quiet'])} → {_yn(a['c3']['pass'])} | 有提醒 {rc.rate_cell(*nv['c3']['conflict'])}；"
            f"沒提醒 {rc.rate_cell(*nv['c3']['quiet'])} |",
            f"| 4 判有風險的題目拿到「中」以上 ≥ 20% | {rc.rate_cell(*a['c4']['share'])} → {_yn(a['c4']['pass'])} "
            f"| {rc.rate_cell(*nv['c4']['share'])} |",
            "",
            f"AI 判「無法查證」的題目（參考，不在標準 3）：有衝突提醒 {rc.rate_cell(*a['c3']['unverifiable_conflict'])} 真的有風險；"
            f"沒提醒 {rc.rate_cell(*a['c3']['unverifiable_quiet'])}。", "",
        ]
        if "production" in r:
            p = r["production"]
            lines += [f"參考：正式站現行參數（{PRODUCTION_MID}／{PRODUCTION_MARGIN}、`data/claim_prototypes.npz`；"
                      "原型由全部語料算出、包含測試組，數字偏樂觀）："
                      f"標準 1 中 {rc.rate_cell(*p['c1']['mid'])}、低 {rc.rate_cell(*p['c1']['low'])} {_yn(p['c1']['pass'])}；"
                      f"標準 3 {_yn(p['c3']['pass'])}；標準 4 {rc.rate_cell(*p['c4']['share'])} {_yn(p['c4']['pass'])}", ""]
        lines += ["測試組等級分布：", "", "| 情況 | 等級 | 依據 | 題數 | 風險判定正確率 |", "|---|---|---|---:|---|"]
        for row in r["levels"]:
            lines.append(f"| {row['kind']} | {row['level']} | {row['basis']} | {row['n']} | {rc.rate_cell(row['correct'], row['n'])} |")
        rel = r["reliability"]
        lines += ["", "等級的可靠度（開發組各等級的正確率當機率，對照測試組）：", "",
                  "| 等級 | 開發組正確率 | 測試組題數 | 測試組正確率 |", "|---|---|---:|---|"]
        for row in rel["rows"]:
            lines.append(f"| {row['level']} | {rc.pct(row['p_dev'])} | {row['n_test']} | {rc.pct(row['acc_test'])} |")
        lines += ["", f"- ECE {rel['ece']}；Brier {fmt(rel['brier'])}（全部猜基準比例 {rc.pct(rel['base_rate'])} 的 Brier "
                  f"{fmt(rel['brier_base_rate'])}；比它小才代表等級帶有資訊）"]
        pf2 = r["pf2"]
        if pf2:
            lines.append(f"- PF-2 改寫句：{pf2['pairs']} 組中 {pf2['hits']} 組達「高」門檻（相似度中位數 {pf2['median']}）")
        emb = rc_status(f"embed_{rc.EMBED_MODELS.get(r['model'], {'slug': r['model']})['slug']}")
        latency = emb.get("single_text_seconds") or {}
        lines.append(f"- 檢索速度：知識庫最近鄰（numpy）每題 p50 {r['search_ms_p50']} 毫秒"
                     + (f"；單筆 embedding p50 {latency.get('p50')} 秒、p90 {latency.get('p90')} 秒" if latency else ""))
        lines.append("")
    lines += [
        "## AI 自評分數 `confidence_score`（參考，與 embedding 無關；測試組）", "",
        f"有 SAFE／有風險判定且有分數的題目 {ai['n']}（低於 0.5 的 {ai['below_0_5']} 題不在表內）。", "",
        "| 分數 | 題數 | 平均分數 | 風險判定正確率 |", "|---|---:|---|---|",
    ]
    for b in ai["bins"]:
        lines.append(f"| {b['range']} | {b['n']} | {fmt(b['mean_score'])} | {rc.pct(b['acc'])} |")
    lines += ["", f"- ECE {ai['ece']}；Brier {fmt(ai['brier'])}；以分數區分判對／判錯的 AUROC {fmt(ai['auroc'])}",
              "- 綠燈門檻 `GREEN_MIN_CONFIDENCE`（AI 判 SAFE 的題目；不含「要有查核來源」那一條）：", "",
              "| 門檻 | 留下 | 留下的真的安全 |", "|---|---|---|"]
    for gr in ai["green"]:
        lines.append(f"| {gr['threshold']} | {gr['kept']}／{gr['of']} | {rc.pct(gr['precision'])} |")
    lines += [
        "", "## 限制", "",
        "1. 規則 5、7（AI 引用 Tier 1／2 查核來源）無法重現：每週評測不存來源、不帶 web_search。網站上這兩條會讓少數題目多拿到「中」。",
        "2. 歷史抽樣的題目可能出現在模型訓練資料中；安全題全取自 Cofacts 認可為非謠言的訊息，與網站上的真實輸入不同。",
        "3. 題目日期：MyGoPen／台灣事實查核中心取文章發布日、Cofacts 取訊息建立日；查核結論日期：Cofacts 取最早一則獲認可回覆的日期。"
        "這只是近似，真實情況下訊息出現的時間通常早於查核文章。",
        "4. 話術原型只排除了測試組的題目與近似內容，沒有做時間切分。",
        "5. 每週評測不經快取：語意快取的「高」是模擬出來的（相似度 ≥ 門檻就沿用最近那筆查核的結論）。",
        "",
    ]
    return "\n".join(lines)


def fmt(x: Optional[float]) -> str:
    return "—" if x is None else f"{x:.3f}"


# ── main ─────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fetch")
    f.add_argument("--since", default=WEEKLY_SINCE)
    f.add_argument("--refresh", action="store_true")
    f.add_argument("--cofacts-max", type=int, default=9000)
    e = sub.add_parser("embed")
    e.add_argument("--model", default=rc.DEFAULT_EMBED)
    e.add_argument("--limit", type=int, default=0, help=f"trial: only this many texts (use {rc.TRIAL_ITEMS})")
    e.add_argument("--max-usd", type=float, default=1.0)
    e.add_argument("--batch", type=int, default=50)
    e.add_argument("--latency-probe", type=int, default=20)
    a = sub.add_parser("analyze")
    a.add_argument("--models", default=",".join(rc.EMBED_MODELS))
    a.add_argument("--group-model", default=rc.DEFAULT_EMBED)
    a.add_argument("--since-note", default=WEEKLY_SINCE)
    args = parser.parse_args()
    return {"fetch": cmd_fetch, "embed": cmd_embed, "analyze": cmd_analyze}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
