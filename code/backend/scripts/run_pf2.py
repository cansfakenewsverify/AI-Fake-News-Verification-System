"""PF-2 重測：對組員審定的 20 筆改寫句量測語意快取命中率（票 O-11）。

用法（先在另一個視窗啟動本機後端，預設埠 8030）：
    .\\venv\\Scripts\\python scripts\\run_pf2.py --base http://127.0.0.1:8030

依測試計畫書 PF-2：對 20 筆改寫版謠言以 POST /api/analyze/sync 送出，
`cache_layer=vector` 的比例需達 70%（14／20）。

依測試計畫書 §4.3 與中止規則：本測試會寫入資料，執行前先備份
knowledge_base.parquet、tasks.parquet、factcheck.db 並記錄 SHA-256，
且同一時間不與其他寫入程序並行。

輸出：
    docs/test/results/pf2_rerun_<日期>.csv   逐句結果（含 cache_layer 與延遲）
    docs/test/perf_log.csv                   追加 result_id／origin／cache_layer／elapsed_ms
    主控台摘要                                命中率與各層分佈

Windows 主控台是 cp950，本檔只印 ASCII 與中文，不使用符號字元。
"""
import argparse
import csv
import datetime
import hashlib
import io
import json
import os
import shutil
import sys
import time
import unicodedata
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)
REPO = os.path.dirname(os.path.dirname(BACKEND))
WORKSHEET = os.path.join(REPO, "docs", "test", "pf2_worksheet.csv")
RESULTS_DIR = os.path.join(REPO, "docs", "test", "results")
PERF_LOG = os.path.join(REPO, "docs", "test", "perf_log.csv")
DATA = os.path.join(BACKEND, "data")
BACKUP_FILES = ["knowledge_base.parquet", "tasks.parquet", "factcheck.db"]


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def backup(stamp):
    """Copy the three data files aside and record their digests (test plan 4.3)."""
    out = {}
    for name in BACKUP_FILES:
        src = os.path.join(DATA, name)
        if not os.path.exists(src):
            out[name] = None
            continue
        dst = os.path.join(DATA, f"{name}.bak-pf2-{stamp}")
        shutil.copyfile(src, dst)
        out[name] = {"backup": os.path.basename(dst), "sha256_before": sha256(src)}
    return out


def post_sync(base, content, timeout):
    body = json.dumps({"content": content}).encode("utf-8")
    req = urllib.request.Request(
        f"{base}/api/analyze/sync", data=body,
        headers={"Content-Type": "application/json"}, method="POST")
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            payload = json.loads(r.read().decode("utf-8"))
            status = r.status
    except urllib.error.HTTPError as e:
        payload = json.loads(e.read().decode("utf-8") or "{}")
        status = e.code
    return status, payload, round((time.perf_counter() - t0) * 1000)


def norm(s):
    return "".join(unicodedata.normalize("NFKC", s or "").split())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8030")
    ap.add_argument("--timeout", type=float, default=120.0)
    ap.add_argument("--dry-run", action="store_true", help="只檢查題目與後端狀態，不送出")
    args = ap.parse_args()

    rows = list(csv.DictReader(io.open(WORKSHEET, encoding="utf-8-sig")))
    col = "你的改寫句（請填）"
    missing = [r["編號"] for r in rows if not r[col].strip()]
    if missing:
        sys.exit(f"工作表還有沒填的列：{', '.join(missing)}")

    try:
        with urllib.request.urlopen(f"{args.base}/api/health", timeout=20) as r:
            health = json.loads(r.read().decode("utf-8"))
    except Exception as e:
        sys.exit(f"連不上本機後端 {args.base}：{e}")
    print(f"後端 {args.base}  storage={health.get('storage_backend')}  "
          f"ai_available={health.get('ai_available')}  "
          f"daily={health.get('daily_ai_calls', {}).get('used')}/"
          f"{health.get('daily_ai_calls', {}).get('cap')}")
    if health.get("storage_backend") != "local":
        sys.exit("PF-2 規定以本機後端量測，但這個後端接的不是本機資料，已中止")
    if not health.get("ai_available"):
        sys.exit("後端回報 ai_available=false，依中止規則不執行")

    # 逐句標記字面相似度：完全相同者會命中 hash 層，不是語意層，結果須據實記錄
    for r in rows:
        import difflib
        r["_literal"] = round(difflib.SequenceMatcher(
            None, norm(r["知識庫原文"]), norm(r[col])).ratio(), 3)
    identical = [r["編號"] for r in rows if norm(r["知識庫原文"]) == norm(r[col])]
    near = [r["編號"] for r in rows if r["_literal"] >= 0.85 and r["編號"] not in identical]
    if identical:
        print(f"注意：{len(identical)} 句與原文完全相同（{', '.join(identical)}），預期命中 hash 層")
    if near:
        print(f"注意：{len(near)} 句字面相似度 0.85 以上（{', '.join(near)}）")
    if args.dry_run:
        return

    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    backups = backup(stamp)
    print("已備份資料檔：" + "、".join(
        f"{k}" for k, v in backups.items() if v) or "（無檔案可備份）")

    out_rows = []
    for i, r in enumerate(rows, 1):
        content = r[col].strip()
        status, payload, ms = post_sync(args.base, content, args.timeout)
        layer = payload.get("cache_layer")
        out_rows.append({
            "編號": r["編號"],
            "kb_id": r["kb_id"],
            "知識庫原文": r["知識庫原文"],
            "改寫句": content,
            "字面相似度": r["_literal"],
            "http": status,
            "result_id": payload.get("result_id") or payload.get("id") or "",
            "cached": payload.get("cached"),
            "cache_layer": layer if layer is not None else "",
            "risk_type": payload.get("risk_type", ""),
            "frame_label": payload.get("frame_label", ""),
            "elapsed_ms": ms,
        })
        print(f"{i:2d}/20  cache_layer={str(layer):8s}  {ms:6d} ms  HTTP {status}  {content[:28]}")

    os.makedirs(RESULTS_DIR, exist_ok=True)
    today = datetime.date.today().isoformat()
    out_csv = os.path.join(RESULTS_DIR, f"pf2_rerun_{today}.csv")
    with io.open(out_csv, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(out_rows[0].keys()))
        w.writeheader()
        w.writerows(out_rows)

    # perf_log.csv：result_id / origin / cache_layer / elapsed_ms（測試計畫書交付項目）
    new_log = not os.path.exists(PERF_LOG)
    with io.open(PERF_LOG, "a", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        if new_log:
            w.writerow(["result_id", "origin", "cache_layer", "elapsed_ms"])
        for r in out_rows:
            w.writerow([r["result_id"], "pf2", r["cache_layer"], r["elapsed_ms"]])

    counts = {}
    for r in out_rows:
        counts[r["cache_layer"] or "AI（未命中）"] = counts.get(r["cache_layer"] or "AI（未命中）", 0) + 1
    vec = counts.get("vector", 0)
    print()
    print("各層分佈：" + "、".join(f"{k} {v}" for k, v in sorted(counts.items())))
    print(f"語意快取命中 {vec}／20 = {vec / 20 * 100:.0f}%　準則 70%（14／20）　"
          f"{'通過' if vec >= 14 else '未通過'}")
    if identical:
        only_vec_eligible = [r for r in out_rows if r["編號"] not in identical]
        v2 = sum(1 for r in only_vec_eligible if r["cache_layer"] == "vector")
        print(f"（扣除與原文完全相同的 {len(identical)} 句後：{v2}／{len(only_vec_eligible)}）")
    print(f"逐句結果：{os.path.relpath(out_csv, REPO)}")
    print(f"備份：data/*.bak-pf2-{stamp}")


main()
