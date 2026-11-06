r"""
換 embedding 模型時重新校準語意快取門檻與證據信心的數字（票 B-52：Mercury 的 bge-m3）。
只讀本機檔案、只呼叫 embedding（bge-m3 是學校本地模型，不計額度），不寫任何資料庫、不呼叫判讀模型。

在負責人電腦的 code\backend 執行（先跑 evidence_confidence_study.py 產生新模型的話術原型，這裡才算得出話術差距）：

    $env:EMBED_RELAY_URL='https://air.cgu.edu.tw/mercuryapi/v1'; $env:EMBED_MODEL='bge-m3'; $env:VECTOR_DIMENSION='1024'
    .\venv\Scripts\python scripts\evidence_confidence_study.py
    .\venv\Scripts\python scripts\embedding_calibration.py

量法（和 2026-07 校準 0.75 一樣：門檻要落在噪音帶之上、改寫帶之下）：
1. 改寫帶：PF-2 兩組改寫句（docs/test/pf2_paraphrases.csv、results/pf2_rerun_2026-09-21.csv）對它要命中的知識庫原文。
2. 噪音帶：
   a. 不同謠言之間：PF-2 的原文兩兩相比；
   b. 安全訊息：評測題庫 50 題 SAFE 對查核語料可入庫列（data/factcheck_corpus.parquet，約 1.85 萬筆）的最近鄰；
   參考：詐騙、假訊息題的最近鄰（可能真的有同一則，不算噪音）。
3. 每個候選門檻：改寫句有幾句會命中原文、安全題誤命中幾題、不同謠言對超過幾對。
   依規則算出的門檻 = 噪音帶上緣（安全題最近鄰最高、不同謠言對 99 百分位）與改寫帶中位數的中點
   （舊模型用同一個規則算出 0.76，實際用 0.75，可見規則重現得了當初的校準）。
4. 證據信心的 0.65（最近已證實不實內容）、0.60（相似查證列出下限）、0.10（話術差距）：
   把舊模型的值在 150 題最近鄰（話術差距）分布中的位置（分位數），換到新模型同一個位置，並列出新模型每一段真的有風險的比例。
同一套量法也用舊模型 text-embedding-3-small 已存的向量（語料、data/evidence_study_vectors.parquet）算一次，
確認量法能重現 0.75。舊模型的向量當初用原文算，所以兩邊的查詢都用原文；新模型另外列一行經 matching_text（正式站的查法）的結果。

報告 docs/test/results/<模型>_calibration_<日期>.md 只放數字與題號，不放訊息原文。
建議值只是依上面的規則算出來的，**要負責人看過同意才改設定**；不為了讓 PF-2 過關挑門檻。
"""
import argparse
import os
import sys
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional

os.environ.setdefault("STORAGE_BACKEND", "local")

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parents[1]
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(BACKEND / "scripts"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from app.config import settings  # noqa: E402

DATA = BACKEND / "data"
CORPUS = DATA / "factcheck_corpus.parquet"
OLD_QUESTION_VECTORS = DATA / "evidence_study_vectors.parquet"
OLD_PROTOTYPES = DATA / "claim_prototypes.npz"
EVAL = DATA / "eval_set.csv"
PF2_SETS = [
    (REPO / "docs/test/pf2_paraphrases.csv", "no", "original", "paraphrase"),
    (REPO / "docs/test/results/pf2_rerun_2026-09-21.csv", "編號", "知識庫原文", "改寫句"),
]
OLD_MODEL = "text-embedding-3-small"
OLD_VALUES = {"threshold": 0.75, "mid": 0.65, "similar_news": 0.60, "margin": 0.10}
CANDIDATES = [round(x, 2) for x in np.arange(0.50, 0.96, 0.01)]
RISK = {"SCAM", "MISINFO"}


def say(msg: str) -> None:
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        enc = getattr(sys.stdout, "encoding", None) or "ascii"
        print(msg.encode(enc, "replace").decode(enc, "replace"), flush=True)


def unit(matrix: np.ndarray) -> np.ndarray:
    matrix = np.asarray(matrix, dtype=np.float32)
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return matrix / norms


def load_pairs() -> pd.DataFrame:
    frames = []
    for path, no, orig, para in PF2_SETS:
        if path.exists():
            df = pd.read_csv(path, encoding="utf-8-sig")
            frames.append(pd.DataFrame({"set": path.stem, "no": df[no].astype(str),
                                        "original": df[orig].astype(str), "paraphrase": df[para].astype(str)}))
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=["set", "no", "original", "paraphrase"])


# ── 量測（兩個模型共用） ───────────────────────────────────────
def measure(K: np.ndarray, orig: np.ndarray, para: np.ndarray, orig_text: List[str],
            questions: np.ndarray, labels: np.ndarray) -> Dict[str, np.ndarray]:
    """K：可入庫列；orig／para：PF-2 原文與改寫句（同列一對）；questions：評測題。全部是單位向量。"""
    out: Dict[str, np.ndarray] = {}
    out["para"] = (orig * para).sum(axis=1)                                  # 改寫句對它的原文
    # 改寫句的最近「別的」列：和原文幾乎一樣的列（同一則被多個來源收錄）不算
    sims = para @ K.T
    same = (orig @ K.T) >= 0.98
    sims[same] = -1.0
    out["para_other"] = sims.max(axis=1) if K.shape[0] else np.zeros(len(para))
    # 不同謠言之間：PF-2 原文兩兩相比（文字相同的只算一次）
    _, first = np.unique(np.asarray(orig_text), return_index=True)
    uniq = orig[np.sort(first)]
    pair = uniq @ uniq.T
    iu = np.triu_indices(len(uniq), k=1)
    out["cross"] = pair[iu]
    nn = (questions @ K.T).max(axis=1) if K.shape[0] else np.zeros(len(questions))
    out["nn"] = nn
    out["labels"] = labels
    out["safe_nn"] = nn[labels == "SAFE"]
    out["risk_nn"] = nn[np.isin(labels, list(RISK))]
    return out


def threshold_rows(m: Dict[str, np.ndarray]) -> List[dict]:
    rows = []
    for t in CANDIDATES:
        rows.append({
            "t": t,
            "para_hit": int((m["para"] >= t).sum()),
            "para_right": int(((m["para"] >= t) & (m["para"] >= m["para_other"])).sum()),
            "safe_false": int((m["safe_nn"] >= t).sum()),
            "cross_over": int((m["cross"] >= t).sum()),
            "risk_hit": int((m["risk_nn"] >= t).sum()),
        })
    return rows


def _stat(values: np.ndarray, fn) -> Optional[float]:
    return float(fn(values)) if len(values) else None


def suggest(m: Dict[str, np.ndarray]) -> Dict[str, float]:
    """噪音帶上緣（安全題最近鄰最高、不同謠言對的 99 百分位）與改寫帶中位數的中點，取到小數第二位。
    不同謠言對取 99 百分位：PF-2 #14、#15 是同一套貸款詐騙話術的兩段，舊模型就有 0.83，算噪音會把門檻推太高。"""
    safe_max = _stat(m["safe_nn"], np.max) or 0.0
    cross_max = _stat(m["cross"], np.max) or 0.0
    cross_p99 = _stat(m["cross"], lambda v: np.percentile(v, 99)) or 0.0
    noise = max(safe_max, cross_p99)
    para_median = _stat(m["para"], np.median) or 0.0
    return {"noise_max": noise, "safe_max": safe_max, "cross_max": cross_max, "cross_p99": cross_p99,
            "para_min": _stat(m["para"], np.min) or 0.0,
            "para_p25": _stat(m["para"], lambda v: np.percentile(v, 25)) or 0.0,
            "para_median": para_median, "suggest": round((noise + para_median) / 2 + 1e-9, 2)}


def top_cross_pairs(orig: np.ndarray, orig_ids: List[str], n: int = 3) -> List[tuple]:
    """最像的幾對不同謠言原文：[(相似度, 題號, 題號)]，只給題號、不給文字。"""
    _, first = np.unique(np.asarray(orig_ids), return_index=True)
    first = np.sort(first)
    if len(first) < 2:
        return []
    U = orig[first]
    sim = U @ U.T
    iu = np.triu_indices(len(U), k=1)
    order = np.argsort(-sim[iu])[:n]
    return [(float(sim[iu][k]), orig_ids[first[iu[0][k]]], orig_ids[first[iu[1][k]]]) for k in order]


def quantile_map(old: np.ndarray, new: np.ndarray, value: float) -> Optional[float]:
    """value 在 old 分布的分位數 → new 分布同一個分位數的值。"""
    if not len(old) or not len(new):
        return None
    q = float((old < value).mean())
    return float(np.quantile(new, min(max(q, 0.0), 1.0)))


def margins(questions: np.ndarray, prototypes: Path) -> Optional[np.ndarray]:
    if not prototypes.exists():
        return None
    with np.load(prototypes) as data:
        risk, safe = unit(data["risk"]), unit(data["safe"])
    if risk.shape[1] != questions.shape[1]:
        return None
    return (questions @ risk.T).max(axis=1) - (questions @ safe.T).max(axis=1)


# ── 向量來源 ────────────────────────────────────────────────────
def old_model_vectors(corpus: pd.DataFrame, pairs: pd.DataFrame, ev: pd.DataFrame):
    """舊模型：語料存著的向量＋題目快取（以原文為鍵）。缺的題目回 None（舊閘道已關，不重算）。"""
    if not OLD_QUESTION_VECTORS.exists():
        return None
    cache = pd.read_parquet(OLD_QUESTION_VECTORS)
    known = {t: np.asarray(v, dtype=np.float32) for t, v in zip(cache["text"], cache["vector"])}
    texts = list(pairs["original"]) + list(pairs["paraphrase"]) + list(ev["content"].astype(str))
    if any(t not in known for t in texts):
        say(f"舊模型的題目向量缺 {sum(t not in known for t in set(texts))} 筆，對照只算有的部分")
    kb = corpus[(corpus["use"] == "kb") & corpus["vector"].map(lambda v: v is not None and not isinstance(v, float))]
    K = unit(np.stack(kb["vector"].to_numpy()))
    ok_pairs = pairs[pairs["original"].isin(known) & pairs["paraphrase"].isin(known)]
    ok_ev = ev[ev["content"].astype(str).isin(known)]
    vec = lambda ts: unit(np.stack([known[t] for t in ts])) if len(ts) else np.zeros((0, K.shape[1]), np.float32)  # noqa: E731
    return (K, vec(list(ok_pairs["original"])), vec(list(ok_pairs["paraphrase"])), list(ok_pairs["original"]),
            vec(list(ok_ev["content"].astype(str))), ok_ev["gold_label"].to_numpy())


def new_model_vectors(corpus: pd.DataFrame, pairs: pd.DataFrame, ev: pd.DataFrame, matching: bool):
    from app.utils.claim_text import matching_text
    from embed_cache import EmbedCache

    cache = EmbedCache(settings.EMBED_MODEL, dim=int(settings.VECTOR_DIMENSION))
    kb = corpus[corpus["use"] == "kb"]
    kb_texts = kb["text"].astype(str).tolist()
    q = (lambda t: matching_text(t)) if matching else (lambda t: t)
    originals = list(pairs["original"])
    paraphrases = [q(t) for t in pairs["paraphrase"]]
    questions = [q(t) for t in ev["content"].astype(str)]
    cache.ensure(kb_texts, label="語料：")
    cache.ensure(originals + paraphrases + questions, label="題目：")
    _, K = cache.matrix(kb_texts)
    rows_p, O = cache.matrix(originals)
    rows_q, P = cache.matrix(paraphrases)
    keep = np.intersect1d(rows_p, rows_q)
    O = O[np.searchsorted(rows_p, keep)]
    P = P[np.searchsorted(rows_q, keep)]
    rows_e, E = cache.matrix(questions)
    return (unit(K), unit(O), unit(P), [originals[i] for i in keep], unit(E), ev["gold_label"].to_numpy()[rows_e])


# ── 報告 ───────────────────────────────────────────────────────
def fmt(x: Optional[float], nd: int = 3) -> str:
    return "—" if x is None else f"{x:.{nd}f}"


def band_table(results: Dict[str, Dict[str, np.ndarray]]) -> List[str]:
    lines = ["| 量測 | " + " | ".join(results) + " |", "|------|" + "------|" * len(results)]
    def row(name, fn):
        lines.append(f"| {name} | " + " | ".join(fn(m) for m in results.values()) + " |")
    p = lambda q: (lambda v: np.percentile(v, q))  # noqa: E731
    row("改寫句對原文：最小", lambda m: fmt(_stat(m["para"], np.min)))
    row("改寫句對原文：25%", lambda m: fmt(_stat(m["para"], p(25))))
    row("改寫句對原文：中位數", lambda m: fmt(_stat(m["para"], np.median)))
    row("改寫句對原文：最大", lambda m: fmt(_stat(m["para"], np.max)))
    row("不同謠言之間：最大", lambda m: fmt(_stat(m["cross"], np.max)))
    row("不同謠言之間：99%", lambda m: fmt(_stat(m["cross"], p(99))))
    row("安全題最近鄰：最大", lambda m: fmt(_stat(m["safe_nn"], np.max)))
    row("安全題最近鄰：中位數", lambda m: fmt(_stat(m["safe_nn"], np.median)))
    row("詐騙／假訊息題最近鄰：中位數", lambda m: fmt(_stat(m["risk_nn"], np.median)))
    row("句數（改寫對／不同謠言對／評測題）",
        lambda m: f"{len(m['para'])}／{len(m['cross'])}／{len(m['nn'])}")
    return lines


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=None, help="report path (default docs/test/results/<model>_calibration_<date>.md)")
    args = ap.parse_args(argv)

    model = settings.EMBED_MODEL
    if model == OLD_MODEL:
        say(f"EMBED_MODEL 還是 {OLD_MODEL}：先設定新模型（見檔案開頭的說明）。")
        return 2
    tag = "".join(c if c.isalnum() else "_" for c in model)
    out = Path(args.out) if args.out else REPO / "docs/test/results" / f"{tag}_calibration_{date.today().isoformat()}.md"

    corpus = pd.read_parquet(CORPUS)
    pairs = load_pairs()
    ev = pd.read_csv(EVAL, encoding="utf-8-sig")
    say(f"語料可入庫列 {int((corpus['use'] == 'kb').sum())} 筆；PF-2 {len(pairs)} 對；評測題 {len(ev)} 題")

    results: Dict[str, Dict[str, np.ndarray]] = {}
    old = old_model_vectors(corpus, pairs, ev)
    if old is not None:
        results[f"{OLD_MODEL}（原文）"] = measure(*old)
    new_raw = new_model_vectors(corpus, pairs, ev, matching=False)
    results[f"{model}（原文）"] = measure(*new_raw)
    new_match = new_model_vectors(corpus, pairs, ev, matching=True)
    results[f"{model}（matching_text，正式站查法）"] = measure(*new_match)

    new_key = f"{model}（matching_text，正式站查法）"
    tips = {name: suggest(m) for name, m in results.items()}
    say("各模型依規則算出的門檻（噪音帶上緣與改寫帶中位數的中點）："
        + "；".join(f"{n} {t['suggest']:.2f}" for n, t in tips.items()))

    lines = [f"# {model} 的語意門檻與證據信心校準（{date.today().isoformat()}，票 B-52）", "",
             "由 `code/backend/scripts/embedding_calibration.py` 產生。只放數字，不放訊息原文。",
             f"新模型：`{model}`（{settings.EMBED_RELAY_URL}，{int(settings.VECTOR_DIMENSION)} 維）；"
             f"對照：`{OLD_MODEL}`（1536 維，2026-09 存下的向量）。", "",
             "知識庫以查核語料可入庫列代表（`data/factcheck_corpus.parquet`，2026-09-24），和正式站的 1.9 萬筆大致相同。", "",
             "## 1. 改寫帶與噪音帶", ""]
    lines += band_table(results)
    label_of: Dict[str, str] = {}
    for _, r in pairs.iterrows():
        label_of.setdefault(r["original"], f"{r['set']} #{r['no']}")
    lines += ["", "最像的幾對不同謠言原文（只列題號）：", ""]
    for name, vecs in ([(f"{OLD_MODEL}", old)] if old is not None else []) + [(model, new_raw)]:
        tops = top_cross_pairs(vecs[1], [label_of.get(t, "?") for t in vecs[3]])
        lines.append(f"- {name}：" + "；".join(f"{a} 與 {b} {s:.3f}" for s, a, b in tops))
    lines += ["", "## 2. 候選門檻", "",
              "「改寫命中」＝改寫句對原文 ≥ 門檻；「命中且最近」＝同時比其他列都近（語意快取會回這一筆）；"
              "「安全誤命中」＝安全題的最近鄰 ≥ 門檻（入庫後會被判成詐騙或假訊息）；「不同謠言對」＝不同謠言的原文兩兩相比 ≥ 門檻。", ""]
    for name, m in results.items():
        t = tips[name]
        lines += [f"### {name}", "",
                  f"噪音帶上緣 {t['noise_max']:.3f}（安全題最高 {t['safe_max']:.3f}、不同謠言對 99% {t['cross_p99']:.3f}，"
                  f"最高 {t['cross_max']:.3f}）；改寫帶最低 {t['para_min']:.3f}、25% {t['para_p25']:.3f}、"
                  f"中位數 {t['para_median']:.3f}；**依規則算出的門檻（兩者中點）{t['suggest']:.2f}**。", "",
                  "| 門檻 | 改寫命中 | 命中且最近 | 安全誤命中 | 不同謠言對 | 詐騙／假訊息題最近鄰 ≥ 門檻 |",
                  "|------|----------|------------|------------|------------|------------------------------|"]
        n_para, n_safe, n_cross, n_risk = len(m["para"]), len(m["safe_nn"]), len(m["cross"]), len(m["risk_nn"])
        for r in threshold_rows(m):
            if round(r["t"] * 100) % 5 and abs(r["t"] - t["suggest"]) > 1e-9:
                continue
            mark = "**" if abs(r["t"] - t["suggest"]) < 1e-9 else ""
            lines.append(f"| {mark}{r['t']:.2f}{mark} | {r['para_hit']}／{n_para} | {r['para_right']}／{n_para} | "
                         f"{r['safe_false']}／{n_safe} | {r['cross_over']}／{n_cross} | {r['risk_hit']}／{n_risk} |")
        lines.append("")

    # ── 證據信心的數字：分位數換算 ──
    old_name = f"{OLD_MODEL}（原文）"
    new_name = f"{model}（原文）"
    lines += ["## 3. 證據信心的數字（分位數換算）", "",
              "舊模型的值在 150 題最近鄰相似度（話術差距）分布裡的位置，換到新模型同一個位置。"
              "兩邊都用原文查詢，和 2026-09-24 定 0.65／0.10 的研究相同。", ""]
    if old_name in results:
        o, n = results[old_name], results[new_name]
        mid = quantile_map(o["nn"], n["nn"], OLD_VALUES["mid"])
        similar = quantile_map(o["nn"], n["nn"], OLD_VALUES["similar_news"])
        thr = quantile_map(o["nn"], n["nn"], OLD_VALUES["threshold"])
        lines += ["| 設定 | 舊值 | 新模型同分位數的值 |", "|------|------|--------------------|",
                  f"| SIMILARITY_THRESHOLD（對照用） | {OLD_VALUES['threshold']} | {fmt(thr)} |",
                  f"| EVIDENCE_MID_SIMILARITY | {OLD_VALUES['mid']} | {fmt(mid)} |",
                  f"| SIMILAR_NEWS_MIN | {OLD_VALUES['similar_news']} | {fmt(similar)} |"]
        old_m = margins(old[4], OLD_PROTOTYPES) if old is not None else None
        tag_file = DATA / f"claim_prototypes_{''.join(c if c.isalnum() or c in '-.' else '_' for c in model)}.npz"
        new_m = margins(new_raw[4], tag_file)
        if old_m is not None and new_m is not None:
            lines.append(f"| EVIDENCE_PATTERN_MARGIN | {OLD_VALUES['margin']} | "
                         f"{fmt(quantile_map(old_m, new_m, OLD_VALUES['margin']))} |")
        else:
            lines.append(f"| EVIDENCE_PATTERN_MARGIN | {OLD_VALUES['margin']} | —（先跑 evidence_confidence_study.py 產生 `{tag_file.name}`） |")
        lines += ["", "新模型最近鄰相似度分段 → 題目真的有風險的比例（150 題，基準 66.7%）：", "",
                  "| 區間 | 題數 | 真的有風險 | 比例 |", "|------|------|------------|------|"]
        bins = [0.0, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90, 1.01]
        frame = pd.DataFrame({"nn": n["nn"], "risk": np.isin(n["labels"], list(RISK))})
        for interval, g in frame.groupby(pd.cut(frame["nn"], bins, right=False), observed=True):
            lines.append(f"| {interval.left:.2f}～{min(interval.right, 1.0):.2f} | {len(g)} | {int(g.risk.sum())} | "
                         f"{g.risk.mean():.0%} |")
    else:
        lines.append("沒有舊模型的題目向量（data/evidence_study_vectors.parquet），無法換算。")

    lines += ["", "## 4. 給負責人決定", "",
              f"- 語意快取門檻：依規則（噪音帶上緣與改寫帶中位數的中點）算出 **{tips[new_key]['suggest']:.2f}**"
              f"（正式站查法）。舊模型同一個規則算出 {tips.get(old_name, {}).get('suggest', float('nan')):.2f}，實際用 0.75。",
              "- 證據信心三個數字見第 3 節；建議先用分位數換算的值，上線後再用每週評測驗證。",
              "- 這些是建議，**負責人同意後**才寫進 `render.yaml`（`SIMILARITY_THRESHOLD`、`EVIDENCE_MID_SIMILARITY`、"
              "`SIMILAR_NEWS_MIN`、`EVIDENCE_PATTERN_MARGIN`、`CLAIM_PROTOTYPES_FILE`）。", ""]
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")
    say(f"報告：{out.relative_to(REPO) if out.is_relative_to(REPO) else out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
