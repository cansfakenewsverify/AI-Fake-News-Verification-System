"""
Threads OAuth token 取得／續期（spec 7.3 第 1、2 點；T-03）。

用法（在 code\\backend 目錄執行）：
    venv\\Scripts\\python scripts\\threads_auth.py              # 授權：印授權 URL → 貼回 code → 換 60 天長效 token
    venv\\Scripts\\python scripts\\threads_auth.py --refresh    # 續期：token 取得滿 24 小時後才可執行

需要 .env：THREADS_APP_ID、THREADS_APP_SECRET（Threads use case 頁的 Threads App ID／Secret，
不是 Meta App ID）、PUBLIC_BASE_URL（redirect_uri = {PUBLIC_BASE_URL}/oauth/callback）。

結果寫到 data/threads_token.json（gitignored；temp 檔 + os.replace 原子寫入）：
    {access_token, obtained_at, expires_at, authorized_at, user_id}
主控台只印 user_id、expires_at、token_days_left；絕不印 token（cp950：不放 emoji）。

結束碼：0 成功；1 設定缺漏、HTTP／網路錯誤、或 --refresh 時 obtained_at 缺漏/無法解析（token_age_unknown，
不續期；請重新授權）（皆不寫檔）；2 token_too_young（--refresh 未滿 24h）。
回應缺 expires_in 時以 60 天計。
"""
import argparse
import json
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Optional
from urllib.parse import parse_qs, quote, urlencode, urlparse

import requests

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.config import settings  # noqa: E402
from app.services.threads_service import _days_left, _parse_iso, redact_token  # noqa: E402

AUTHORIZE_URL = "https://threads.com/oauth/authorize"
SHORT_TOKEN_URL = "https://graph.threads.com/oauth/access_token"
LONG_TOKEN_URL = "https://graph.threads.net/access_token"
REFRESH_URL = "https://graph.threads.net/refresh_access_token"
SCOPES = "threads_basic,threads_content_publish,threads_manage_replies,threads_manage_mentions"
DEFAULT_TOKEN_PATH = BACKEND_DIR / "data" / "threads_token.json"
MIN_REFRESH_AGE = timedelta(hours=24)
DEFAULT_EXPIRES_IN = 60 * 86400  # 回應缺 expires_in 時以長效 token 的 60 天計（避免 expires_at=now 使 bot 誤判失效）
HTTP_TIMEOUT = 30

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_TOO_YOUNG = 2


class AuthError(Exception):
    """交換／續期失敗（訊息已遮蔽 token）。"""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds")


def redirect_uri(public_base_url: str) -> str:
    return f"{public_base_url.rstrip('/')}/oauth/callback"


def build_authorize_url(app_id: str, public_base_url: str) -> str:
    query = urlencode(
        {
            "client_id": app_id,
            "redirect_uri": redirect_uri(public_base_url),
            "scope": SCOPES,
            "response_type": "code",
        },
        quote_via=quote,
        safe=":/,",
    )
    return f"{AUTHORIZE_URL}?{query}"


def clean_code(raw: str) -> str:
    """去掉空白與 Threads 附加的尾端 #_；貼整段 callback 網址時自動取出 code。"""
    s = (raw or "").strip()
    if "code=" in s:
        found = parse_qs(urlparse(s).query).get("code") or parse_qs(s.split("?", 1)[-1]).get("code")
        if found:
            s = found[0].strip()
    if s.endswith("#_"):
        s = s[:-2]
    return s.rstrip("#").strip()


def _call(method: str, url: str, *, params=None, data=None, secrets=()) -> Dict[str, Any]:
    try:
        if method == "GET":
            r = requests.get(url, params=params, timeout=HTTP_TIMEOUT)
        else:
            r = requests.post(url, data=data, timeout=HTTP_TIMEOUT)
    except requests.RequestException as e:
        msg = f"{type(e).__name__}: {e}"
        for s in secrets:
            msg = redact_token(msg, s)
        raise AuthError(redact_token(msg)) from None
    status = getattr(r, "status_code", 0)
    if status is None or status >= 400:
        body = str(getattr(r, "text", "") or "")
        for s in secrets:
            body = redact_token(body, s)
        body = redact_token(body)[:300]  # 先整段遮蔽再截斷，避免 secret 跨截斷點殘留前半段
        raise AuthError(f"HTTP {status}: {body}")
    try:
        payload = r.json()
    except ValueError:
        raise AuthError(f"HTTP {status}: response is not JSON") from None
    if not isinstance(payload, dict) or not payload.get("access_token"):
        raise AuthError(f"HTTP {status}: response missing access_token")
    return payload


def _expires_in(payload: Dict[str, Any]) -> int:
    try:
        v = int(payload.get("expires_in"))
    except (TypeError, ValueError):
        return DEFAULT_EXPIRES_IN
    return v if v > 0 else DEFAULT_EXPIRES_IN


def exchange_code(code: str, app_id: str, app_secret: str, public_base_url: str) -> Dict[str, Any]:
    """code → 短效 token（含 user_id）→ 60 天長效 token。回 {access_token, user_id, expires_in}。"""
    short = _call(
        "POST",
        SHORT_TOKEN_URL,
        data={
            "client_id": app_id,
            "client_secret": app_secret,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri(public_base_url),
            "code": code,
        },
        secrets=(app_secret, code),
    )
    short_token = str(short["access_token"])
    long = _call(
        "GET",
        LONG_TOKEN_URL,
        params={
            "grant_type": "th_exchange_token",
            "client_secret": app_secret,
            "access_token": short_token,
        },
        secrets=(app_secret, short_token),
    )
    return {
        "access_token": str(long["access_token"]),
        "user_id": str(short.get("user_id") or long.get("user_id") or ""),
        "expires_in": _expires_in(long),
    }


def read_token_file(path: Path) -> Optional[Dict[str, Any]]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def write_token_file(path: Path, data: Dict[str, Any]) -> None:
    """temp 檔 + os.replace 原子寫入。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".threads_token.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _print_summary(data: Dict[str, Any], now: datetime) -> None:
    days = _days_left(_parse_iso(data.get("expires_at")), now)
    print(f"user_id={data.get('user_id')}")
    print(f"expires_at={data.get('expires_at')}")
    print(f"token_days_left={days}")


def run_authorize(
    token_path: Path,
    input_fn: Callable[[str], str] = input,
    now: Optional[datetime] = None,
) -> int:
    app_id = (settings.THREADS_APP_ID or "").strip()
    app_secret = (settings.THREADS_APP_SECRET or "").strip()
    base = (settings.PUBLIC_BASE_URL or "").strip()
    missing = [
        k for k, v in (("THREADS_APP_ID", app_id), ("THREADS_APP_SECRET", app_secret), ("PUBLIC_BASE_URL", base)) if not v
    ]
    if missing:
        print(f"[threads_auth] missing_config: {', '.join(missing)}（請在 .env 設定）")
        return EXIT_ERROR

    print("[threads_auth] 請用機器人帳號在瀏覽器開啟以下網址並同意授權：")
    print(build_authorize_url(app_id, base))
    code = clean_code(input_fn("[threads_auth] 貼上 callback 頁顯示的 code（或整段網址）："))
    if not code:
        print("[threads_auth] empty_code")
        return EXIT_ERROR

    try:
        tok = exchange_code(code, app_id, app_secret, base)
    except AuthError as e:
        print(f"[threads_auth] exchange_failed: {e}")
        return EXIT_ERROR

    now = now or _now()
    old = read_token_file(token_path) or {}
    data = {
        "access_token": tok["access_token"],
        "obtained_at": _iso(now),
        "expires_at": _iso(now + timedelta(seconds=tok["expires_in"])),
        "authorized_at": old.get("authorized_at") or _iso(now),
        "user_id": tok["user_id"] or str(old.get("user_id") or ""),
    }
    write_token_file(token_path, data)
    print(f"[threads_auth] saved {token_path}")
    _print_summary(data, now)
    return EXIT_OK


def run_refresh(token_path: Path, now: Optional[datetime] = None) -> int:
    data = read_token_file(token_path)
    if not data or not str(data.get("access_token") or "").strip():
        print(f"[threads_auth] token_file_missing: {token_path}（請先執行授權流程）")
        return EXIT_ERROR

    now = now or _now()
    obtained = _parse_iso(data.get("obtained_at"))
    if obtained is None:
        # 取得時間未知 → 無法確認已滿 24h，拒絕續期（spec 7.3 第 2 點）；請重新跑授權流程寫入完整檔案
        print("[threads_auth] token_age_unknown: obtained_at 缺漏或格式錯誤，無法確認已滿 24 小時；請重新執行授權流程")
        return EXIT_ERROR
    if now - obtained < MIN_REFRESH_AGE:
        print("token_too_young")
        return EXIT_TOO_YOUNG

    old_token = str(data["access_token"]).strip()
    try:
        res = _call(
            "GET",
            REFRESH_URL,
            params={"grant_type": "th_refresh_token", "access_token": old_token},
            secrets=(old_token,),
        )
    except AuthError as e:
        print(f"[threads_auth] refresh_failed: {e}")
        return EXIT_ERROR

    data["access_token"] = str(res["access_token"])
    data["obtained_at"] = _iso(now)
    data["expires_at"] = _iso(now + timedelta(seconds=_expires_in(res)))
    write_token_file(token_path, data)  # authorized_at／user_id 原樣保留
    print(f"[threads_auth] refreshed {token_path}")
    _print_summary(data, now)
    return EXIT_OK


def main(argv=None, input_fn: Callable[[str], str] = input, now: Optional[datetime] = None) -> int:
    ap = argparse.ArgumentParser(description="Threads OAuth：code 換長效 token，或續期既有 token")
    ap.add_argument("--refresh", action="store_true", help="續期 data/threads_token.json 的 token（取得滿 24 小時才可）")
    ap.add_argument("--token-file", default=str(DEFAULT_TOKEN_PATH), help="token 檔路徑（預設 data/threads_token.json）")
    args = ap.parse_args(argv)
    path = Path(args.token_file)
    if args.refresh:
        return run_refresh(path, now=now)
    return run_authorize(path, input_fn=input_fn, now=now)


if __name__ == "__main__":
    sys.exit(main())
