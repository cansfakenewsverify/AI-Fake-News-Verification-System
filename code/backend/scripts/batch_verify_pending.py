"""
批次查證已知消息：抓一輪 RSS 熱門 → 反覆 AI 分析 PENDING 記錄，直到
清空 / 達預算護欄 / 達回合上限。設計成可長跑、可中斷、可重跑（冪等）。

用法：
    venv\\Scripts\\python scripts\\batch_verify_pending.py                 # 完整：抓 RSS + 清 PENDING
    venv\\Scripts\\python scripts\\batch_verify_pending.py --skip-fetch    # 只清既有 PENDING
    venv\\Scripts\\python scripts\\batch_verify_pending.py --budget-cap 18 --max-rounds 30

護欄：
- 每回合前查 CGU /me/usage，累計花費超過 --budget-cap（美元）就停
- 高量任務關閉 web_search（省 3~7 倍，可用 --web-search 打開）
- AI 額度用盡（fallback）時 retry 會自動跳過，不會把錯誤結果寫進資料庫
"""
import argparse
import asyncio
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests

from app.config import settings


def cgu_cost_usd() -> float:
    """目前 CGU openai 池累計花費（查不到時回 -1，不擋跑）。"""
    key = (settings.CGU_API_KEY or "").strip()
    base = (settings.CGU_BASE_URL or "").rstrip("/")
    if not key:
        return -1.0
    try:
        r = requests.get(f"{base}/me/usage",
                         headers={"Authorization": f"Bearer {key}"}, timeout=20)
        r.raise_for_status()
        return float(r.json().get("openai", {}).get("cost_usd", -1.0))
    except Exception:
        return -1.0


def pending_count() -> int:
    from sqlalchemy import or_
    from app.database_sql import SessionLocal, init_sql_db
    from app.models.fact_check_record import FactCheckRecord
    init_sql_db()
    db = SessionLocal()
    try:
        return db.query(FactCheckRecord).filter(
            FactCheckRecord.is_trending == True,  # noqa: E712
            or_(
                FactCheckRecord.risk_type.is_(None),
                FactCheckRecord.risk_type.in_(["PENDING", "UNKNOWN"]),
            ),
        ).count()
    finally:
        db.close()


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-fetch", action="store_true", help="不抓新 RSS，只清既有 PENDING")
    ap.add_argument("--budget-cap", type=float, default=18.0,
                    help="CGU 累計花費護欄（美元），超過就停（預設 18，保留 2 美元餘裕）")
    ap.add_argument("--max-rounds", type=int, default=30, help="retry 回合上限")
    ap.add_argument("--web-search", action="store_true", help="打開 web_search（貴 3~7 倍）")
    args = ap.parse_args()

    if not args.web_search:
        settings.USE_WEB_SEARCH = False   # 高量任務預設關（只影響本行程）
        print("[batch] web_search 已關閉（高量任務省點數）")

    from app.services.news_fetcher import run_trending_fetch, retry_pending_records

    start_cost = cgu_cost_usd()
    print(f"[batch] 起始 CGU 花費: ${start_cost:.4f}" if start_cost >= 0
          else "[batch] 無法查詢用量（照跑，僅少了預算護欄）")

    if not args.skip_fetch:
        print("[batch] === 抓取 RSS 熱門（MyGoPen/TFC/GoogleNews/Cofacts）===")
        await run_trending_fetch()   # 內含一輪 retry_pending

    for rnd in range(1, args.max_rounds + 1):
        n = pending_count()
        cost = cgu_cost_usd()
        cost_s = f"${cost:.4f}" if cost >= 0 else "n/a"
        print(f"[batch] round {rnd}: pending={n}, cgu_cost={cost_s}")
        if n == 0:
            print("[batch] PENDING 已清空，收工")
            break
        if cost >= 0 and cost > args.budget_cap:
            print(f"[batch] 已達預算護欄 ${args.budget_cap}，停止")
            break
        ok = await retry_pending_records()
        if ok == 0 and pending_count() >= n:
            # 整輪零進展（多半是 AI 暫時無法使用）→ 停止，別空轉
            print("[batch] 本輪零進展，停止（AI 額度恢復後可重跑）")
            break
        time.sleep(2)
    else:
        print(f"[batch] 達回合上限 {args.max_rounds}，停止")

    end_cost = cgu_cost_usd()
    if start_cost >= 0 and end_cost >= 0:
        print(f"[batch] 本次花費: ${end_cost - start_cost:.4f}（累計 ${end_cost:.4f}）")
    print(f"[batch] 結束 pending={pending_count()}")


if __name__ == "__main__":
    asyncio.run(main())
