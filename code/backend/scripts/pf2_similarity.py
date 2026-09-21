"""PF-2 診斷：算出每一句改寫句與知識庫的實際相似度（唯讀，不寫入任何資料）。

用法（從 code/backend）：
    .\\venv\\Scripts\\python scripts\\pf2_similarity.py

PF-2 只回報「命中／未命中」，看不出差多少。本腳本用與 `PandasStore.find_similar_by_vector`
完全相同的算法——只比對 `verified=True` 且維度相符的列、cosine similarity、取最高分——
算出每一句的最高相似度與對應的知識庫原文，讓未通過的原因可以逐句檢視。

與量測的差別：本腳本**不呼叫判讀模型、不寫入知識庫、不累加命中次數**，
只呼叫 embedding 取得查詢向量（每句一次，成本極低）。因此可以重複執行，
不會影響 PF-2 的重測結果。

輸出 docs/test/results/pf2_similarity_<日期>.csv 與主控台摘要。
Windows 主控台是 cp950，本檔只印 ASCII 與中文。
"""
import csv
import datetime
import io
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)
REPO = os.path.dirname(os.path.dirname(BACKEND))
sys.path.insert(0, BACKEND)

from app.config import settings                      # noqa: E402
from app.services.vector_service import VectorService  # noqa: E402

WORKSHEET = os.path.join(REPO, "docs", "test", "pf2_worksheet.csv")
KB = os.path.join(BACKEND, "data", "knowledge_base.parquet")
RESULTS = os.path.join(REPO, "docs", "test", "results")
COL = "你的改寫句（請填）"


def verified_matrix(df, dim):
    """與 find_similar_by_vector 相同的取樣：只收 verified 且維度相符的列。"""
    mask = df["verified"].fillna(False).astype(bool) if "verified" in df.columns \
        else pd.Series(False, index=df.index)
    sub = df[df["content_vector"].notna() & mask]
    idx, rows = [], []
    for i, v in sub["content_vector"].items():
        a = np.asarray(v, dtype=np.float32)
        if a.shape == (dim,):
            idx.append(i)
            rows.append(a)
    return idx, (np.stack(rows) if rows else np.empty((0, dim), dtype=np.float32))


def main():
    threshold = settings.SIMILARITY_THRESHOLD
    df = pd.read_parquet(KB)
    rows = list(csv.DictReader(io.open(WORKSHEET, encoding="utf-8-sig")))
    vs = VectorService()

    first = vs.vectorize_content(rows[0][COL].strip())
    if not first:
        sys.exit("取不到 embedding，請確認金鑰與網路")
    dim = len(first)
    idx, matrix = verified_matrix(df, dim)
    if matrix.size == 0:
        sys.exit("知識庫沒有可比對的已證實向量")
    norms = np.linalg.norm(matrix, axis=1)
    print(f"門檻 {threshold}；可比對的已證實列 {len(idx)} 筆，維度 {dim}")

    out = []
    for n, r in enumerate(rows):
        text = r[COL].strip()
        q = np.asarray(first if n == 0 else vs.vectorize_content(text), dtype=np.float32)
        qn = np.linalg.norm(q)
        scores = (matrix @ q) / (norms * qn)
        order = np.argsort(scores)[::-1]
        best, second = order[0], order[1]
        best_row = df.loc[idx[best]]
        hit_expected = bool(scores[best] >= threshold)
        # 這一列原本要對上的那一筆，排在第幾名
        target_rank = ""
        target_score = ""
        for rank, k in enumerate(order, 1):
            if str(df.loc[idx[k], "id"]) == r["kb_id"]:
                target_rank, target_score = rank, round(float(scores[k]), 4)
                break
        out.append({
            "編號": r["編號"],
            "改寫句": text,
            "應對上的原文": r["知識庫原文"],
            "與應對上那筆的相似度": target_score,
            "該筆的名次": target_rank,
            "全庫最高相似度": round(float(scores[best]), 4),
            "最高的是哪一筆": str(best_row.get("raw_content", ""))[:60],
            "第二高": round(float(scores[second]), 4),
            "門檻": threshold,
            "預期命中": "是" if hit_expected else "否",
            "差距": round(threshold - float(scores[best]), 4) if not hit_expected else 0,
        })
        mark = "命中" if hit_expected else f"未命中，差 {threshold - float(scores[best]):.3f}"
        print(f"{r['編號']:>2}  最高 {float(scores[best]):.4f}  {mark}   {text[:30]}")

    os.makedirs(RESULTS, exist_ok=True)
    path = os.path.join(RESULTS, f"pf2_similarity_{datetime.date.today().isoformat()}.csv")
    with io.open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0].keys()))
        w.writeheader()
        w.writerows(out)

    hits = [o for o in out if o["預期命中"] == "是"]
    near = [o for o in out if o["預期命中"] == "否" and o["差距"] <= 0.05]
    print()
    print(f"預期命中 {len(hits)}／{len(out)}；未命中中有 {len(near)} 句差距在 0.05 以內")
    print(f"逐句相似度：{os.path.relpath(path, REPO)}")


main()
