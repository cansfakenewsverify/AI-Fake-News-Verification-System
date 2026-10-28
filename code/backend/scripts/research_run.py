r"""
研究批次一鍵執行（在負責人電腦上，用本機 .env；步驟說明見 docs/test/研究批次_本機執行.md）。

  confidence  信心程度驗證：抓資料（沒有或超過 3 天就重抓）→ 每個 embedding 先試跑 50 筆、推估花費不超過上限才全部算完
              → 分析出報告
  benchmark   模型比較：凍結題庫（第一次）→ 每個模型先試跑 50 題、推估花費不超過上限才全跑 → 報告
  update      每三天更新一次資料：重抓查核機構的新資料，為新文字補算向量（已經算過的 embedding 都補；3 天內更新過就略過）
  all         confidence ＋ benchmark

加 --commit：把結果（docs/test/results/，不含訊息原文）commit 並推到研究分支；目前不在研究分支就不 commit。
額度護欄都在底層（research_common.Budget）：開始前與每 100 題讀 /me/usage、保留 USD 3、台灣時間週日不跑花錢的步驟。
中斷了重跑同一個指令會接著做（向量與模型的逐題結果都會保留）。

    .\venv\Scripts\python scripts\research_run.py confidence --commit
    .\venv\Scripts\python scripts\research_run.py benchmark --commit
    .\venv\Scripts\python scripts\research_run.py update --commit
"""
import argparse
import subprocess
import sys
import time
from argparse import Namespace
from pathlib import Path
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pandas as pd  # noqa: E402

import confidence_validation as cv  # noqa: E402
import model_benchmark as mb  # noqa: E402
import research_common as rc  # noqa: E402

BRANCH = "claude/github-project-relevance-gunvht"
REFRESH_DAYS = 3
# embedding：全部算完的上限（USD）；試跑推估超過就不全跑
EMBED_CAPS = {"text-embedding-3-small": 0.5, "text-embedding-3-large": 2.0, "bge-m3:latest": 0.0}
# 模型比較的模型清單：模型/推理強度/api[/最多幾題]（模型名稱可能有冒號，所以用 / 分隔）
DEFAULT_MODELS = ",".join([
    "gpt-5.6-luna/medium/responses",        # 正式站現用（基準）
    "gpt-6-luna/high/responses",            # 閘道建議
    "gpt-6-luna/medium/responses",
    "gpt-oss-120b/medium/chat",             # 學校算力池，不花 OpenAI 額度
    "gemma-4-26b-a4b-it/none/chat",
    "nemotron-3.5-bolt-74b-a9b/none/chat",
    "nemotron-3-super-120b-a12b/none/chat",
    "gpt-oss:20b/low/chat/500",             # 閘道本地 Ollama，每題 10～90 秒，只抽 500 題
])


def corpus_age_days() -> Optional[float]:
    if not rc.CORPUS.exists():
        return None
    return (time.time() - rc.CORPUS.stat().st_mtime) / 86400


def ensure_corpus(refresh_days: float, force: bool = False) -> bool:
    """語料沒有或超過 refresh_days 天就重抓（重抓會忽略舊的抓取快取）。→ 這次有沒有抓。"""
    age = corpus_age_days()
    if age is not None and age < refresh_days and not force:
        rc.log(f"[run] corpus is {age:.1f} days old (< {refresh_days}); not fetching again")
        return False
    cv.cmd_fetch(Namespace(since=cv.WEEKLY_SINCE, refresh=age is not None, cofacts_max=9000))
    return True


def embedding_complete(model: str) -> Tuple[int, int]:
    """(還沒有向量的文字數, 需要的文字數)。"""
    wanted = cv.texts_to_embed(rc.load_corpus(), pd.read_parquet(cv.QUESTIONS))
    store = rc.EmbeddingStore(model)
    return sum(1 for h, _ in wanted if h not in store), len(wanted)


def ensure_embeddings(model: str, cap: Optional[float] = None, trial_first: bool = True) -> bool:
    """先試跑 50 筆（從來沒算過時），推估全部的花費不超過上限才全部算完。→ 是否已經全部有向量。"""
    cap = EMBED_CAPS.get(model, 0.5) if cap is None else cap
    missing, total = embedding_complete(model)
    if missing == 0:
        return True
    store_size = len(rc.EmbeddingStore(model))
    if trial_first and store_size == 0:
        cv.cmd_embed(Namespace(model=model, limit=rc.TRIAL_ITEMS, max_usd=min(cap, 0.05) or 0.05, batch=50,
                               latency_probe=0))
        est = rc.read_status(f"embed_{rc.EMBED_MODELS[model]['slug']}").get("estimated_remaining_usd")
        if rc.EMBED_MODELS[model]["usd_per_m"] > 0 and (est is None or est > cap):
            rc.step_summary(f"## `{model}` 沒有全部算完\n\n試跑推估剩下的要 USD {est}，超過上限 USD {cap}。"
                            "要算就加大上限再跑一次（`--embed-cap`）。")
            return False
    cv.cmd_embed(Namespace(model=model, limit=0, max_usd=max(cap, 0.01), batch=50, latency_probe=20))
    return embedding_complete(model)[0] == 0


def run_confidence(args) -> None:
    ensure_corpus(args.refresh_days, args.refetch)
    ready = []
    for model in [m.strip() for m in args.embed_models.split(",") if m.strip()]:
        if ensure_embeddings(model, args.embed_cap):
            ready.append(model)
    if rc.DEFAULT_EMBED not in ready:
        rc.step_summary("## 信心驗證沒有分析\n\n`text-embedding-3-small` 的向量還沒算完（分群要用它）。")
        return
    cv.cmd_analyze(Namespace(models=",".join(ready), group_model=rc.DEFAULT_EMBED, since_note=cv.WEEKLY_SINCE))


def parse_models(spec: str) -> List[Dict[str, object]]:
    out = []
    for part in [p.strip() for p in spec.split(",") if p.strip()]:
        bits = part.split("/")
        if len(bits) < 3:
            raise SystemExit(f"bad model spec {part!r}: use model/effort/api[/max_items]")
        out.append({"model": bits[0], "effort": bits[1], "api": bits[2],
                    "max_items": int(bits[3]) if len(bits) > 3 and bits[3] else None})
    return out


def answered(model: str, effort: str) -> int:
    df = mb.load_results(mb.RUNS / f"{mb.slug(model, effort)}.csv")
    return int(df["error"].eq("").sum()) if not df.empty else 0


def run_benchmark(args) -> None:
    if not mb.ITEMS.exists():
        ensure_corpus(args.refresh_days, False)
        if not ensure_embeddings(rc.DEFAULT_EMBED, args.embed_cap):
            rc.step_summary("## 模型比較沒有開始\n\n凍結題庫要 `text-embedding-3-small` 的向量（去重用），還沒算完。")
            return
        mb.cmd_freeze(Namespace(risky=mb.N_RISKY, safe=mb.N_SAFE, force=False))
    elif not rc.CORPUS.exists():
        ensure_corpus(args.refresh_days, False)
    items = len(pd.read_csv(mb.ITEMS))
    from app.services.ai_service import gateway_models

    listed = gateway_models()
    for spec in parse_models(args.models):
        model, effort, api = spec["model"], spec["effort"], spec["api"]
        target = min(spec["max_items"] or items, items)
        if listed is not None and model not in listed:
            rc.step_summary(f"## 模型比較：`{model}` 略過\n\n閘道的模型清單（/models）沒有這個模型。")
            continue
        done = answered(model, effort)
        if done >= target:
            rc.log(f"[run] {model} {effort}: already answered {done}/{target}")
            continue
        free = model in mb.FREE_MODELS
        if done == 0:
            mb.cmd_run(Namespace(model=model, effort=effort, api=api, limit=rc.TRIAL_ITEMS, max_usd=0.3,
                                 max_minutes=args.max_minutes))
            done = answered(model, effort)
            if done == 0:
                rc.step_summary(f"## 模型比較：`{model}` {effort} 試跑沒有任何回答，略過（看上面的錯誤）")
                continue
            est = rc.read_status(f"benchmark_{mb.slug(model, effort)}").get("usd_per_item")
            rest = None if est is None else est * (target - done)
            if not free and (rest is None or rest > args.model_cap):
                rc.step_summary(f"## 模型比較：`{model}` {effort} 只做了試跑\n\n推估剩下 {target - done} 題要 USD {rest}，"
                                f"超過每個模型的上限 USD {args.model_cap}（`--model-cap`）。")
                continue
        mb.cmd_run(Namespace(model=model, effort=effort, api=api, limit=target - done,
                             max_usd=args.model_cap, max_minutes=args.max_minutes))
    mb.cmd_report(Namespace())


def run_update(args) -> None:
    """每三天更新一次：重抓查核機構的新資料，為新文字補算向量（只補已經算過的 embedding；花費只有新文字的份）。"""
    if not ensure_corpus(args.refresh_days, args.refetch):
        return
    for model in rc.EMBED_MODELS:
        if len(rc.EmbeddingStore(model)) == 0:
            continue
        ensure_embeddings(model, max(EMBED_CAPS.get(model, 0.1) / 5, 0.05), trial_first=False)
    rc.update_status("update", {"corpus_age_days": 0, "embeddings": {m: len(rc.EmbeddingStore(m)) for m in rc.EMBED_MODELS}})


def git(*cmd: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *cmd], cwd=rc.REPO, capture_output=True, text=True, encoding="utf-8")


def commit_results(what: str) -> None:
    """結果 commit 回研究分支（只有 docs/test/results/；不在研究分支就不做）。"""
    branch = git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    if branch != BRANCH:
        rc.log(f"[run] not on {BRANCH} (on {branch!r}); results are not committed")
        return
    git("add", "docs/test/results")
    if git("diff", "--cached", "--quiet", "--", "docs/test/results").returncode == 0:
        rc.log("[run] nothing new to commit")
        return
    done = git("commit", "-m", f"研究批次 {what}（research_run.py，負責人電腦）", "--", "docs/test/results")
    if done.returncode != 0:
        rc.log("[run] git commit failed: " + done.stderr.strip()[:300])
        return
    for _ in range(3):
        if git("push", "origin", BRANCH).returncode == 0:
            rc.log("[run] results pushed")
            return
        git("pull", "--no-rebase", "origin", BRANCH)
    rc.log("[run] git push failed; run `git push` yourself")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("what", choices=["confidence", "benchmark", "update", "all"])
    parser.add_argument("--commit", action="store_true", help="commit and push docs/test/results to the research branch")
    parser.add_argument("--refresh-days", type=float, default=REFRESH_DAYS)
    parser.add_argument("--refetch", action="store_true", help="fetch the fact-check data again even if it is fresh")
    parser.add_argument("--embed-models", default=rc.DEFAULT_EMBED,
                        help="comma-separated; e.g. text-embedding-3-small,bge-m3:latest,text-embedding-3-large")
    parser.add_argument("--embed-cap", type=float, default=None, help="USD cap per embedding model (default per model)")
    parser.add_argument("--models", default=DEFAULT_MODELS, help="model/effort/api[/max_items], comma-separated")
    parser.add_argument("--model-cap", type=float, default=4.0, help="USD cap per benchmark model")
    parser.add_argument("--max-minutes", type=float, default=320, help="time limit per benchmark model run")
    args = parser.parse_args()
    if args.what in ("confidence", "all"):
        run_confidence(args)
    if args.what in ("benchmark", "all"):
        run_benchmark(args)
    if args.what == "update":
        run_update(args)
    if args.commit:
        commit_results(args.what)
    return 0


if __name__ == "__main__":
    sys.exit(main())
