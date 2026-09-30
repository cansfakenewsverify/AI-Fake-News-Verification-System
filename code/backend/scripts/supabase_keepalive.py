r"""
用 Supabase 的 pg_cron＋pg_net 每 5 分鐘呼叫一次 Render 的 /health，讓免費主機不休眠（2026-10-01）。

為什麼：Render 免費方案 15 分鐘沒有流量就休眠，睡著時雲端的 Threads 機器人不會檢查提及；GitHub Actions 的
keepalive 實際上每 2～5 小時才跑一次。pg_cron 在資料庫裡準時執行，pg_net 從資料庫發 HTTP 請求。
Render 免費方案每月 750 小時，一個服務整月不睡約 720～744 小時，在額度內。

    .\venv\Scripts\python scripts\supabase_keepalive.py            # 目前狀態（排程是否存在、最近幾次結果）
    .\venv\Scripts\python scripts\supabase_keepalive.py --apply    # 啟用擴充並建立／更新排程
    .\venv\Scripts\python scripts\supabase_keepalive.py --remove   # 刪除排程

會改正式資料庫的設定（啟用 pg_cron、pg_net 擴充與一個排程），要負責人同意才加 --apply。
需要 .env 的 SUPABASE_DB_URL。不印連線字串；主控台只印 ASCII。
"""
import argparse
import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
os.chdir(BACKEND)

JOB_NAME = "render-keepalive"
SCHEDULE = "*/5 * * * *"
DEFAULT_URL = "https://fakenewsverify-api.onrender.com/health"


def log(msg: str) -> None:
    print(msg.encode("ascii", "replace").decode("ascii"), flush=True)


def _status(conn) -> None:
    has_cron = conn.exec_driver_sql("SELECT 1 FROM pg_extension WHERE extname = 'pg_cron'").first() is not None
    has_net = conn.exec_driver_sql("SELECT 1 FROM pg_extension WHERE extname = 'pg_net'").first() is not None
    log(f"extensions: pg_cron={'yes' if has_cron else 'no'} pg_net={'yes' if has_net else 'no'}")
    if not has_cron:
        return
    rows = conn.exec_driver_sql(
        "SELECT jobid, schedule, active, command FROM cron.job WHERE jobname = %s", (JOB_NAME,)
    ).all()
    if not rows:
        log(f"job {JOB_NAME}: not scheduled")
        return
    for jobid, schedule, active, command in rows:
        log(f"job {JOB_NAME}: id={jobid} schedule='{schedule}' active={active}")
        runs = conn.exec_driver_sql(
            "SELECT status, start_time FROM cron.job_run_details WHERE jobid = %s ORDER BY start_time DESC LIMIT 3",
            (jobid,),
        ).all()
        for status, start in runs:
            log(f"  run {start:%Y-%m-%d %H:%M:%S} {status}")
    if has_net:
        responses = conn.exec_driver_sql(
            "SELECT status_code, created FROM net._http_response ORDER BY created DESC LIMIT 3"
        ).all()
        for code, created in responses:
            log(f"  http {code} at {created:%Y-%m-%d %H:%M:%S}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="enable pg_cron/pg_net and schedule the job")
    ap.add_argument("--remove", action="store_true", help="unschedule the job")
    ap.add_argument("--url", default=DEFAULT_URL)
    args = ap.parse_args(argv)

    from app.config import settings
    from app.database_sql import build_pg_engine

    if not (settings.SUPABASE_DB_URL or "").strip():
        log("SUPABASE_DB_URL is not set in .env")
        return 2
    if not args.url.startswith("https://") or "'" in args.url:
        log("--url must start with https:// and must not contain quotes")
        return 2
    engine = build_pg_engine().execution_options(isolation_level="AUTOCOMMIT")
    try:
        with engine.connect() as conn:
            if args.remove:
                conn.exec_driver_sql("SELECT cron.unschedule(%s)", (JOB_NAME,))
                log(f"job {JOB_NAME} removed")
            elif args.apply:
                # Supabase 文件的建議寫法：pg_cron 放 pg_catalog、pg_net 放 extensions
                conn.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS pg_cron WITH SCHEMA pg_catalog")
                conn.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS pg_net WITH SCHEMA extensions")
                command = f"SELECT net.http_get(url := '{args.url}', timeout_milliseconds := 30000)"
                conn.exec_driver_sql("SELECT cron.schedule(%s, %s, %s)", (JOB_NAME, SCHEDULE, command))
                log(f"job {JOB_NAME} scheduled: every 5 minutes -> {args.url}")
            _status(conn)
    finally:
        engine.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(main())
