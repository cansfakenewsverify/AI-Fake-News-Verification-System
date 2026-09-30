r"""
把 Threads 機器人的狀態從負責人電腦搬到 Supabase，讓機器人改在雲端（Render）執行（2026-10-01）。

搬的東西（app/services/threads_pg.py 的兩張表）：
  data/threads_state.json   → threads_kv 'state'（已回覆 id、since 游標、backoff、pending_publish、failed…）
  data/threads_replies.jsonl → threads_replies（同一個 mention_id 只記一次，可重跑）
  data/threads_token.json   → threads_kv 'token'（60 天 token；雲端剩不到 10 天會自動續期）

預設 dry-run：只印本機與雲端的筆數、token 是否存在與到期日；--apply 才寫。
雲端已經有狀態時不覆蓋（雲端的可能比本機新），除非加 --force。
授權 90 天到期、重跑 scripts\threads_auth.py 之後，用 --token-only --apply 只上傳新 token。

    .\venv\Scripts\python scripts\threads_cloud_setup.py
    .\venv\Scripts\python scripts\threads_cloud_setup.py --apply
    .\venv\Scripts\python scripts\threads_cloud_setup.py --token-only --apply

**搬之前先停掉本機的 live 機器人**：搬完之後本機若還以檔案狀態跑 live，會跟雲端重複回覆。
之後要在本機跑 live，設 STORAGE_BACKEND=supabase，就會和雲端共用同一份狀態與輪詢鎖。
需要 .env 的 SUPABASE_DB_URL（STORAGE_BACKEND 不必是 supabase）。不印 token、不印連線字串；主控台只印 ASCII。
"""
import argparse
import json
import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
os.chdir(BACKEND)


def log(msg: str) -> None:
    print(msg.encode("ascii", "replace").decode("ascii"), flush=True)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="actually write to Supabase (default: dry-run)")
    ap.add_argument("--force", action="store_true", help="overwrite an existing cloud state")
    ap.add_argument("--token-only", action="store_true", help="only upload data/threads_token.json")
    ap.add_argument("--data-dir", default="data")
    args = ap.parse_args(argv)

    from app.config import settings
    from app.services import threads_state
    from app.services.threads_pg import ThreadsPgStore
    from app.services.threads_service import load_token_file

    if not (settings.SUPABASE_DB_URL or "").strip():
        log("SUPABASE_DB_URL is not set in .env")
        return 2
    data_dir = Path(args.data_dir)
    local_state = threads_state.load_state(data_dir)
    local_replies = threads_state.read_reply_records(None, data_dir)[::-1]     # 舊到新
    token = load_token_file(data_dir / "threads_token.json")
    pg = ThreadsPgStore()
    cloud_state = pg.get("state")
    cloud_token = pg.get("token")
    cloud_replies = pg.replies()

    log(f"local : replied_ids={len(local_state.get('replied_ids') or [])} last_since={local_state.get('last_since')} "
        f"pending_publish={len(local_state.get('pending_publish') or {})} reply_records={len(local_replies)} "
        f"token={'yes, expires ' + str(token.get('expires_at')) if token else 'no'}")
    log(f"cloud : state={'yes' if cloud_state is not None else 'no'} reply_records={len(cloud_replies)} "
        f"token={'yes, expires ' + str(cloud_token.get('expires_at')) if isinstance(cloud_token, dict) else 'no'}")

    if not args.apply:
        log("dry-run: nothing written (add --apply)")
        return 0
    if args.token_only:
        if not token:
            log("no data/threads_token.json to upload (run scripts\\threads_auth.py first)")
            return 1
        pg.put("token", token)
        log(f"token uploaded (user_id={token.get('user_id')}, expires {token.get('expires_at')})")
        return 0
    if cloud_state is not None and not args.force:
        log("cloud state already exists: not overwritten (use --force only if the local copy is newer)")
        return 1
    if not token:
        log("no data/threads_token.json: run scripts\\threads_auth.py first")
        return 1
    added = sum(1 for row in local_replies if pg.append_reply({f: row.get(f) for f in threads_state.REPLY_RECORD_FIELDS}))
    pg.put("token", token)
    pg.put("state", local_state)     # 最後寫狀態：雲端機器人看到 state 才開始輪詢
    log(f"uploaded: state (replied_ids={len(local_state.get('replied_ids') or [])}), "
        f"reply_records +{added}, token (expires {token.get('expires_at')})")
    log("next: keep the local live bot stopped; deploy with THREADS_MODE=live on Render")
    return 0


if __name__ == "__main__":
    sys.exit(main())
