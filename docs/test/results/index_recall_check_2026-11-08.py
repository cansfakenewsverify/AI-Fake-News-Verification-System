"""半精度 HNSW 索引 vs 全表掃描：抽樣比對最近的已證實列是否相同（只讀）。"""
import sys
import time
from pathlib import Path

BACKEND = Path(r"C:\Users\user\Desktop\AI-Fake-News-Verification-System\code\backend")
sys.path.insert(0, str(BACKEND))

from scripts.create_vector_index import _connect, _column_dim  # noqa: E402

THRESHOLD = 0.84
OUT = Path(sys.argv[1])

conn = _connect()
conn.execute("SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY")
dim = _column_dim(conn)
half = f"CAST(content_vector AS halfvec({dim}))"

samples = []
for verified in (False, True):
    rows = conn.execute(
        "SELECT id, CAST(content_vector AS text) FROM knowledge_base"
        f" WHERE {'' if verified else 'NOT '}verified AND content_vector IS NOT NULL ORDER BY random() LIMIT 40"
    ).fetchall()
    samples += [(verified, r[0], r[1]) for r in rows]

base = "FROM knowledge_base WHERE verified AND content_vector IS NOT NULL"
exact_sql = (f"SELECT id, 1 - (content_vector <=> CAST(%s AS vector)) {base}"
             " ORDER BY content_vector <=> CAST(%s AS vector), seq LIMIT 3")
index_sql = (f"SELECT id, 1 - (content_vector <=> CAST(%s AS vector)) {base}"
             f" ORDER BY {half} <=> CAST(%s AS halfvec({dim})), seq LIMIT 3")

lines, same_top, same_decision, t_exact, t_index, max_gap = [], 0, 0, 0.0, 0.0, 0.0
for verified, qid, vec in samples:
    t0 = time.perf_counter()
    exact = [r for r in conn.execute(exact_sql, (vec, vec)).fetchall() if r[0] != qid][:1]
    t1 = time.perf_counter()
    index = [r for r in conn.execute(index_sql, (vec, vec)).fetchall() if r[0] != qid][:1]
    t2 = time.perf_counter()
    t_exact += t1 - t0
    t_index += t2 - t1
    e_id, e_sim = (exact[0][0], float(exact[0][1])) if exact else (None, 0.0)
    i_id, i_sim = (index[0][0], float(index[0][1])) if index else (None, 0.0)
    same = e_id == i_id or abs(e_sim - i_sim) < 1e-9
    same_top += same
    decision = (e_sim >= THRESHOLD) == (i_sim >= THRESHOLD) and (e_sim < THRESHOLD or same)
    same_decision += decision
    max_gap = max(max_gap, e_sim - i_sim)
    if not same:
        lines.append(f"不同 {'已證實' if verified else '未證實'} 查詢 {qid}: 全表 {e_id} {e_sim:.4f} / 索引 {i_id} {i_sim:.4f}")

n = len(samples)
summary = [
    f"樣本 {n} 筆（未證實 {sum(1 for s in samples if not s[0])}、已證實 {sum(1 for s in samples if s[0])}；已證實的查詢排除自己）",
    f"最近一筆相同：{same_top}/{n}",
    f"0.84 門檻判斷相同：{same_decision}/{n}",
    f"索引找到的比全表最近的相似度最多低 {max_gap:.4f}",
    f"平均耗時：全表 {t_exact / n * 1000:.0f} ms、索引 {t_index / n * 1000:.0f} ms",
]
OUT.write_text("\n".join(summary + lines) + "\n", encoding="utf-8")
print("done")
