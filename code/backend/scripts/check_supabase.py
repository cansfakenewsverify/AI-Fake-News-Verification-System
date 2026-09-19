r"""
檢查 Supabase Postgres 連線（不會印出連線字串或密碼）。

    venv\Scripts\python scripts\check_supabase.py

讀 settings.SUPABASE_DB_URL（來自 .env 或環境變數）。印出：是否連得上、伺服器版本、
目前角色、pgvector 是否可用／已安裝、既有資料表。主控台是 cp950，只印 ASCII。
"""
import sys
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.config import settings  # noqa: E402


def main() -> int:
    url = (settings.SUPABASE_DB_URL or "").strip()
    if not url:
        print("[supabase] SUPABASE_DB_URL is empty. Add it to code/backend/.env first.")
        return 2
    if "[YOUR-PASSWORD]" in url or "YOUR-PASSWORD" in url:
        print("[supabase] SUPABASE_DB_URL still contains the [YOUR-PASSWORD] placeholder. Replace it with the database password.")
        return 2
    parsed = urlparse(url)
    print(f"[supabase] host={parsed.hostname} port={parsed.port} db={(parsed.path or '/').lstrip('/')} user_set={bool(parsed.username)} password_set={bool(parsed.password)}")
    if parsed.hostname and parsed.hostname.startswith("db.") and parsed.hostname.endswith(".supabase.co"):
        print("[supabase] note: this is the Direct connection host (IPv6 only). If it fails, use the Session pooler URI instead.")

    try:
        import psycopg
    except ImportError:
        print("[supabase] psycopg is not installed: venv/Scripts/python -m pip install \"psycopg[binary]\"")
        return 2

    try:
        with psycopg.connect(url, connect_timeout=15) as conn:
            with conn.cursor() as cur:
                cur.execute("select version(), current_user")
                version, user = cur.fetchone()
                print(f"[supabase] connected. server={version.split(',')[0]} role={user}")
                cur.execute("select default_version, installed_version from pg_available_extensions where name = 'vector'")
                row = cur.fetchone()
                if row is None:
                    print("[supabase] pgvector: NOT available on this server")
                else:
                    print(f"[supabase] pgvector: available={row[0]} installed={row[1] or 'no'}")
                cur.execute("select table_name from information_schema.tables where table_schema = 'public' order by 1")
                tables = [r[0] for r in cur.fetchall()]
                print(f"[supabase] public tables: {', '.join(tables) if tables else '(none)'}")
        return 0
    except Exception as exc:  # 不印例外全文，避免帶出連線字串
        name = type(exc).__name__
        msg = str(exc).splitlines()[0][:160] if str(exc) else ""
        if parsed.password and parsed.password in msg:
            msg = msg.replace(parsed.password, "***")
        print(f"[supabase] connection FAILED: {name}: {msg}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
