"""
清洗審閱輔助：用 CGU 閘道的本地模型 gpt-oss:20b（不花 OpenAI 額度）判斷每筆資料是不是「可查核的主張」。

用途：D-05 審閱前先把「徵才公告、一般新聞報導、標題碎片」這類不是謠言/詐騙訊息本身的資料挑出來，
負責人只需要看被標為 is_claim=false 的列，而不是逐筆看全部 300 筆。

- 只讀 knowledge_base.parquet 與 factcheck.db，不寫回任何資料檔
- 結果寫到 data/llm_second_opinion.csv（UTF-8，gitignored），可中斷後重跑（已判斷的 id 會跳過）
- 本地模型很慢（每筆 10–90 秒），請在背景跑

    venv\\Scripts\\python scripts\\llm_second_opinion.py [--limit N] [--workers 2]
"""
import argparse
import csv
import json
import re
import sqlite3
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd
import requests

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
from app.config import settings  # noqa: E402

DATA = BACKEND / "data"
OUT = DATA / "llm_second_opinion.csv"
MODEL = "gpt-oss:20b"
FIELDS = ["store", "id", "text", "source_url", "risk_type", "is_claim", "kind", "reason", "sec", "error"]

PROMPT = (
    "你是台灣事實查核資料清理助手。判斷下面這筆資料是否為「可查核的主張」："
    "也就是網路上流傳、可以判定真假的說法，或詐騙訊息本身。"
    "以下都不算可查核的主張：徵才或活動公告、一般新聞報導（民調、政策說明、事件報導，而不是謠言本身）、"
    "查核機構自身的消息、只有標題碎片或問候語。"
    "只回一行 JSON，不要其他文字："
    '{"is_claim": true 或 false, "kind": "謠言|詐騙訊息|新聞報導|公告徵才|碎片|其他", "reason": "一句繁體中文"}\n'
    "資料：「{text}」\n來源網址：{url}"
)


def load_rows():
    rows = []
    kb = pd.read_parquet(DATA / "knowledge_base.parquet")
    for r in kb.itertuples(index=False):
        rows.append({"store": "kb", "id": str(r.id), "text": str(r.raw_content or "")[:400],
                     "source_url": str(r.source_url or ""), "risk_type": str(r.risk_type or "")})
    con = sqlite3.connect(DATA / "factcheck.db")
    try:
        for rid, url, title, risk in con.execute(
                "select id, source_url, news_title, risk_type from fact_check_records"):
            rows.append({"store": "trending", "id": str(rid), "text": str(title or "")[:400],
                         "source_url": str(url or ""), "risk_type": str(risk or "")})
    finally:
        con.close()
    return rows


def judge(row):
    key = (settings.CGU_API_KEY or "").strip()
    base = (settings.CGU_BASE_URL or "").rstrip("/")
    body = {
        "model": MODEL,
        "messages": [{"role": "user", "content": PROMPT.replace("{text}", row["text"]).replace("{url}", row["source_url"] or "（無）")}],
        "max_tokens": 800,
        "reasoning_effort": "low",
    }
    t = time.time()
    out = dict(row, is_claim="", kind="", reason="", sec="", error="")
    try:
        r = requests.post(f"{base}/chat/completions", headers={"Authorization": f"Bearer {key}"},
                          json=body, timeout=240)
        out["sec"] = round(time.time() - t, 1)
        if not r.ok:
            out["error"] = f"HTTP {r.status_code}"
            return out
        content = (r.json().get("choices") or [{}])[0].get("message", {}).get("content") or ""
        m = re.search(r"\{.*\}", content, re.S)
        if not m:
            out["error"] = "no_json"
            return out
        data = json.loads(m.group(0))
        out["is_claim"] = str(bool(data.get("is_claim"))).lower()
        out["kind"] = str(data.get("kind") or "")
        out["reason"] = str(data.get("reason") or "")[:200]
    except Exception as e:  # 網路或解析錯誤：記錄後下次重跑會再試
        out["sec"] = round(time.time() - t, 1)
        out["error"] = type(e).__name__
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=2)
    args = ap.parse_args()

    done = set()
    if OUT.exists():
        with OUT.open(encoding="utf-8", newline="") as f:
            for rec in csv.DictReader(f):
                if not rec.get("error"):
                    done.add((rec["store"], rec["id"]))
    todo = [r for r in load_rows() if (r["store"], r["id"]) not in done]
    if args.limit:
        todo = todo[: args.limit]
    print(f"[second-opinion] todo={len(todo)} done={len(done)} model={MODEL}")

    new_file = not OUT.exists()
    with OUT.open("a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if new_file:
            w.writeheader()
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = [pool.submit(judge, r) for r in todo]
            for i, fut in enumerate(as_completed(futures), 1):
                rec = fut.result()
                w.writerow(rec)
                f.flush()
                if i % 10 == 0 or i == len(todo):
                    print(f"[second-opinion] {i}/{len(todo)}")
    print(f"[second-opinion] wrote {OUT}")


if __name__ == "__main__":
    main()
