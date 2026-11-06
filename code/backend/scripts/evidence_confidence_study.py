r"""
證據信心研究：用查核機構已證實的語料（scripts/ingest_factchecks.py 產生）量測「夾角（cosine 相似度）」
能不能當信心，以及把語料批次寫進知識庫後，語意快取會不會把正常訊息誤判成詐騙或假訊息。

只讀語料與題庫、不寫知識庫；embedding 只算題目本身（評測 150 題＋PF-2 改寫句組，約 200 筆輸入，成本可忽略）。

量測四件事：
1. 誤命中檢查：eval_set.csv 150 題（詐騙／假訊息／安全各 50）對「可入庫列」（MISINFO／SCAM）的最近相似度。
   安全題若有鄰居 ≥ 語意門檻，入庫後就會在語意快取層被判成詐騙或假訊息（偽陽性）。
2. 同一則謠言的改寫句夾角：PF-2 兩組改寫句與原句的相似度（「同一則」的分布）。
3. 夾角分段校準：依最近鄰相似度分段，每段中題目真的有風險（詐騙或假訊息）的比例。
4. 話術類型（規定集）：可入庫列分群（KMeans）取中心向量當「話術原型」，已證實為真的列另外分群當「正常訊息原型」；
   以「最近的風險原型 − 最近的正常原型」的差距判斷風險，看它分不分得出三類題目。

輸出：
  data/evidence_study_eval.csv                         逐題結果（gitignored）
  data/evidence_study_vectors.parquet                  題目向量快取（gitignored；重跑不再付 embedding）
  docs/test/results/evidence_confidence_<日期>.md       報告
  data/claim_prototypes.npz                            話術原型與正常訊息原型的中心向量（供線上證據信心使用，進版本庫）

    venv\Scripts\python scripts\evidence_confidence_study.py [--k 40] [--k-safe 12]

換 embedding 模型（票 B-52，Mercury 的 bge-m3）：EMBED_MODEL 不是 text-embedding-3-small 時，語料與題目都用新模型重算
（scripts/embed_cache.py 的本機快取，只存雜湊與向量；bge-m3 不計額度），輸出檔名加上模型名稱，舊模型的檔案不動：
  data/claim_prototypes_<模型>.npz、data/evidence_study_eval_<模型>.csv、docs/test/results/evidence_confidence_<模型>_<日期>.md
報告不放訊息原文（只放題號、查核網址）。語意門檻讀 settings.SIMILARITY_THRESHOLD（可用 --threshold 改）。

    $env:EMBED_RELAY_URL='https://air.cgu.edu.tw/mercuryapi/v1'; $env:EMBED_MODEL='bge-m3'; $env:VECTOR_DIMENSION='1024'
    .\venv\Scripts\python scripts\evidence_confidence_study.py
"""
import argparse
import os
import sys
from datetime import date
from pathlib import Path

os.environ.setdefault("STORAGE_BACKEND", "local")

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parents[1]
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(BACKEND / "scripts"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from app.config import settings  # noqa: E402
from ingest_factchecks import CORPUS, embed_batch, log  # noqa: E402

LEGACY_MODEL = "text-embedding-3-small"
MODEL = settings.EMBED_MODEL
LEGACY = MODEL == LEGACY_MODEL
TAG = "" if LEGACY else "_" + "".join(c if c.isalnum() or c in "-." else "_" for c in MODEL)

DATA = BACKEND / "data"
EVAL = DATA / "eval_set.csv"
PF2_SETS = [REPO / "docs/test/pf2_paraphrases.csv", REPO / "docs/test/results/pf2_rerun_2026-09-21.csv"]
VEC_CACHE = DATA / "evidence_study_vectors.parquet"      # 舊模型的題目向量（以原文為鍵）
OUT_CSV = DATA / f"evidence_study_eval{TAG}.csv"
REPORT = REPO / "docs/test/results" / f"evidence_confidence{TAG}_{date.today().isoformat()}.md"
PROTOTYPES = DATA / f"claim_prototypes{TAG}.npz"

THRESHOLD = float(settings.SIMILARITY_THRESHOLD)        # 實測校準值；換模型時先看 embedding_calibration.py 的報告
# 舊模型的分段沿用 2026-09-24 報告；新模型的相似度分布不同，分段放寬
BINS = ([0.0, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 1.01] if LEGACY
        else [0.0, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90, 1.01])
RISK = {"SCAM", "MISINFO"}
_CACHE = None


def new_model_cache():
    """新模型的本機向量快取（scripts/embed_cache.py）。"""
    global _CACHE
    if _CACHE is None:
        from embed_cache import EmbedCache
        _CACHE = EmbedCache(MODEL, dim=int(settings.VECTOR_DIMENSION))
    return _CACHE


def unit(matrix: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return matrix / norms


def degrees(cos: float) -> float:
    return float(np.degrees(np.arccos(np.clip(cos, -1.0, 1.0))))


def vectors_for(texts: list) -> np.ndarray:
    """題目向量（有快取就用快取；只為新文字呼叫 embedding）。"""
    if not LEGACY:
        cache = new_model_cache()
        cache.ensure(texts, label="題目：")
        missing = [i for i, t in enumerate(texts) if cache.known(t) is None]
        if missing:
            raise SystemExit(f"{len(missing)} 題算不出向量（第一題是第 {missing[0]} 題），先檢查 embedding 設定")
        return np.stack([cache.known(t) for t in texts])
    cache = pd.read_parquet(VEC_CACHE) if VEC_CACHE.exists() else pd.DataFrame(columns=["text", "vector"])
    known = dict(zip(cache["text"], cache["vector"]))
    missing = [t for t in dict.fromkeys(texts) if t not in known]
    for start in range(0, len(missing), 64):
        chunk = missing[start:start + 64]
        got, _ = embed_batch(chunk)
        known.update(zip(chunk, got))
    if missing:
        pd.DataFrame({"text": list(known), "vector": [np.asarray(v, dtype=np.float32) for v in known.values()]}) \
            .to_parquet(VEC_CACHE, index=False)
        log(f"embedded {len(missing)} new question texts")
    return np.stack([np.asarray(known[t], dtype=np.float32) for t in texts])


def load_pf2_pairs() -> pd.DataFrame:
    frames = []
    for path in PF2_SETS:
        if not path.exists():
            continue
        df = pd.read_csv(path, encoding="utf-8-sig")
        orig = "original" if "original" in df.columns else "知識庫原文"
        para = "paraphrase" if "paraphrase" in df.columns else "改寫句"
        frames.append(pd.DataFrame({"set": path.stem, "original": df[orig].astype(str),
                                    "paraphrase": df[para].astype(str)}))
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=["set", "original", "paraphrase"])


def kmeans_centroids(matrix: np.ndarray, k: int, seed: int = 7) -> tuple:
    from sklearn.cluster import KMeans

    model = KMeans(n_clusters=k, n_init=3, random_state=seed).fit(matrix)
    return unit(model.cluster_centers_.astype(np.float32)), model.labels_


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--k", type=int, default=40, help="number of risk prototypes (claim clusters)")
    parser.add_argument("--k-safe", type=int, default=12, help="number of verified-true prototypes")
    parser.add_argument("--threshold", type=float, default=None, help="semantic cache threshold to report against")
    args = parser.parse_args()
    global THRESHOLD
    if args.threshold is not None:
        THRESHOLD = float(args.threshold)
    show_text = LEGACY          # 新模型的報告不放訊息原文（AGENTS.md 第 2 節）

    corpus = pd.read_parquet(CORPUS)
    if not LEGACY:
        # 語料改用新模型的向量（文字和當初入庫時一樣，embed_batch 會截到前 2000 字）
        cache = new_model_cache()
        cache.ensure(corpus["text"].astype(str).tolist(), label="語料：")
        corpus["vector"] = [cache.known(t) for t in corpus["text"].astype(str)]
    corpus = corpus[corpus["vector"].map(lambda v: v is not None and not isinstance(v, float))].reset_index(drop=True)
    kb = corpus[corpus["use"] == "kb"].reset_index(drop=True)
    safe = corpus[corpus["label"] == "SAFE"].reset_index(drop=True)
    K = unit(np.stack(kb["vector"].to_numpy()).astype(np.float32))
    S = unit(np.stack(safe["vector"].to_numpy()).astype(np.float32))
    log(f"corpus with vectors: kb={len(kb)} safe(analysis)={len(safe)}")

    ev = pd.read_csv(EVAL, encoding="utf-8-sig")
    E = unit(vectors_for(ev["content"].astype(str).tolist()))
    pf2 = load_pf2_pairs()
    P_orig = unit(vectors_for(pf2["original"].tolist())) if len(pf2) else np.zeros((0, K.shape[1]), np.float32)
    P_para = unit(vectors_for(pf2["paraphrase"].tolist())) if len(pf2) else np.zeros((0, K.shape[1]), np.float32)

    # ── 1. 最近鄰（可入庫列） ──
    sims = E @ K.T
    top = np.argsort(-sims, axis=1)[:, :10]
    ev["nn_sim"] = sims[np.arange(len(ev)), top[:, 0]]
    ev["nn_deg"] = ev["nn_sim"].map(degrees)
    ev["nn_label"] = kb["label"].to_numpy()[top[:, 0]]
    ev["nn_source"] = kb["source"].to_numpy()[top[:, 0]]
    ev["nn_url"] = kb["url"].to_numpy()[top[:, 0]]
    ev["nn_text"] = kb["text"].str.slice(0, 120).to_numpy()[top[:, 0]]
    ev["gold_risk"] = ev["gold_label"].isin(RISK)

    # ── 4. 話術原型與正常訊息原型 ──
    C_risk, risk_assign = kmeans_centroids(K, args.k)
    C_safe, _ = kmeans_centroids(S, min(args.k_safe, len(S)))
    ev["proto_risk_sim"] = (E @ C_risk.T).max(axis=1)
    ev["proto_safe_sim"] = (E @ C_safe.T).max(axis=1)
    ev["proto_margin"] = ev["proto_risk_sim"] - ev["proto_safe_sim"]
    ev["proto_pred_risk"] = ev["proto_margin"] > 0
    # kNN 投票（可入庫列＋已證實為真的列，取前 10 名、以相似度加權）
    all_vecs = np.vstack([K, S])
    all_risk = np.concatenate([np.ones(len(K), bool), np.zeros(len(S), bool)])
    all_sims = E @ all_vecs.T
    knn = np.argsort(-all_sims, axis=1)[:, :10]
    w = np.take_along_axis(all_sims, knn, axis=1)
    ev["knn_risk_share"] = (w * all_risk[knn]).sum(axis=1) / w.sum(axis=1)
    ev["knn_pred_risk"] = ev["knn_risk_share"] > 0.5

    ev.to_csv(OUT_CSV, index=False, encoding="utf-8-sig")
    scam_share = np.array([(kb["label"].to_numpy()[risk_assign == c] == "SCAM").mean() for c in range(C_risk.shape[0])],
                          dtype=np.float32)
    np.savez_compressed(PROTOTYPES, risk=C_risk.astype(np.float32), safe=C_safe.astype(np.float32),
                        risk_scam_share=scam_share, built=np.array(date.today().isoformat()), model=np.array(MODEL))

    def quote(value, n):
        """報告裡的訊息文字：舊模型照舊放前 n 字；新模型不放原文。"""
        if not show_text:
            return "（不放原文）"
        return str(value)[:n].replace("|", "／").replace("\n", " ")

    # ── 報告 ──
    dim = K.shape[1]
    lines = [f"# 證據信心研究（{MODEL}，{date.today().isoformat()}）", "",
             "由 `code/backend/scripts/evidence_confidence_study.py` 產生；語料來自 `scripts/ingest_factchecks.py`。",
             f"相似度為 cosine（{MODEL}，{dim} 維），夾角 = arccos(相似度)。", "",
             "## 語料", "",
             "| 來源 | 標記 | 用途 | 筆數 |", "|------|------|------|------|"]
    for (src, lab, use), n in corpus.groupby(["source", "label", "use"]).size().items():
        lines.append(f"| {src} | {lab} | {'可入庫' if use == 'kb' else '只供分析'} | {n:,} |")

    t0, t1, t2 = THRESHOLD, round(THRESHOLD - 0.05, 2), round(THRESHOLD - 0.10, 2)
    lines += ["", "## 1. 誤命中檢查：評測 150 題對可入庫列的最近相似度", "",
              f"語意快取門檻 {THRESHOLD}（夾角 {degrees(THRESHOLD):.1f}°）。可入庫列全是詐騙或假訊息，"
              "所以**安全題的最近鄰 ≥ 門檻，就代表入庫後這題會被語意快取誤判**。", "",
              f"| 正確答案 | 題數 | 最近鄰相似度 中位數 | ≥ {t0} | {t1}～{t0} | {t2}～{t1} |",
              "|----------|------|---------------------|--------|------------|------------|"]
    for lab in ["SCAM", "MISINFO", "SAFE"]:
        g = ev[ev["gold_label"] == lab]
        lines.append(f"| {lab} | {len(g)} | {g.nn_sim.median():.3f} | {(g.nn_sim >= t0).sum()} | "
                     f"{((g.nn_sim >= t1) & (g.nn_sim < t0)).sum()} | {((g.nn_sim >= t2) & (g.nn_sim < t1)).sum()} |")
    risky_hits = ev[(ev.nn_sim >= THRESHOLD)]
    lines += ["", f"≥ 門檻的題目共 {len(risky_hits)} 題：", "",
              "| 題號 | 正確答案 | 相似度 | 夾角 | 題目（前 40 字） | 最近鄰（前 60 字） | 最近鄰網址 |",
              "|------|----------|--------|------|------------------|--------------------|------------|"]
    for _, r in risky_hits.sort_values("nn_sim", ascending=False).iterrows():
        lines.append(f"| {r.id} | {r.gold_label} | {r.nn_sim:.3f} | {r.nn_deg:.1f}° | {quote(r.content, 40)} | "
                     f"{quote(r.nn_text, 60)} | {r.nn_url} |")

    if len(pf2):
        same = (P_orig * P_para).sum(axis=1)
        lines += ["", "## 2. 同一則謠言的改寫句夾角（PF-2 題組）", "",
                  f"| 題組 | 句數 | 相似度 中位數 | 最小 | 最大 | ≥ {t0} |", "|------|------|------|------|------|------|"]
        for name, g in pf2.assign(sim=same).groupby("set"):
            lines.append(f"| {name} | {len(g)} | {g.sim.median():.3f} | {g.sim.min():.3f} | {g.sim.max():.3f} | "
                         f"{(g.sim >= t0).sum()} |")

    lines += ["", "## 3. 夾角分段校準：最近鄰相似度 → 題目真的有風險的比例", "",
              "評測題庫三類各 50 題，基準比例為 66.7%（100／150）。", "",
              "| 相似度區間 | 夾角 | 題數 | 真的有風險 | 比例 |", "|------------|------|------|------------|------|"]
    cut = pd.cut(ev["nn_sim"], BINS, right=False)
    for interval, g in ev.groupby(cut, observed=True):
        lo, hi = interval.left, min(interval.right, 1.0)
        lines.append(f"| {lo:.2f}～{hi:.2f} | {degrees(hi):.0f}°～{degrees(lo):.0f}° | {len(g)} | "
                     f"{int(g.gold_risk.sum())} | {g.gold_risk.mean():.0%} |")

    def acc_table(pred_col: str) -> list:
        rows = ["| 正確答案 | 題數 | 判為有風險 | 判對 |", "|----------|------|------------|------|"]
        for lab in ["SCAM", "MISINFO", "SAFE"]:
            g = ev[ev["gold_label"] == lab]
            right = (g[pred_col] == g["gold_risk"]).sum()
            rows.append(f"| {lab} | {len(g)} | {int(g[pred_col].sum())} | {right}／{len(g)} |")
        overall = (ev[pred_col] == ev["gold_risk"]).mean()
        rows.append(f"| 全部 | {len(ev)} | {int(ev[pred_col].sum())} | {overall:.1%} |")
        return rows

    lines += ["", f"## 4. 話術類型（規定集）：{args.k} 個風險原型、{C_safe.shape[0]} 個正常訊息原型", "",
              "判斷規則：離最近的風險原型比離最近的正常原型更近（差距 > 0）就判為有風險。", ""]
    lines += acc_table("proto_pred_risk")
    lines += ["", "差距分段（差距越大越像已知話術）：", "",
              "| 差距區間 | 題數 | 真的有風險 | 比例 |", "|----------|------|------------|------|"]
    mcut = pd.cut(ev["proto_margin"], [-1, -0.05, 0, 0.05, 0.10, 0.15, 1], right=False)
    for interval, g in ev.groupby(mcut, observed=True):
        lines.append(f"| {interval.left:+.2f}～{interval.right:+.2f} | {len(g)} | {int(g.gold_risk.sum())} | "
                     f"{g.gold_risk.mean():.0%} |")
    lines += ["", "對照：kNN 投票（最近 10 筆，含已證實為真的列，以相似度加權，風險權重 > 0.5 判為有風險）", ""]
    lines += acc_table("knn_pred_risk")

    lines += ["", "## 風險原型一覽（每群筆數與代表句）", "",
              "| 群 | 筆數 | 詐騙 | 代表句（離中心最近，前 50 字） | 代表句網址 |",
              "|----|------|------|------------------------------|------------|"]
    for c in range(C_risk.shape[0]):
        members = np.where(risk_assign == c)[0]
        center_sims = K[members] @ C_risk[c]
        rep = kb.iloc[members[int(np.argmax(center_sims))]]
        scam = int((kb["label"].to_numpy()[members] == "SCAM").sum())
        lines.append(f"| {c} | {len(members)} | {scam} | {quote(rep.text, 50)} | {rep.url} |")

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    log(f"report: {REPORT}")
    log(f"per-question csv: {OUT_CSV}")
    log(f"prototypes: {PROTOTYPES}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
