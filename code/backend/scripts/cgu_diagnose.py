r"""
CGU 閘道診斷：分辨「金鑰被重置」「金鑰被擋」「embedding 被擋」「閘道故障」（2026-11-02 正式站 embedding 一直回 HTTP 403 時寫的）。

只讀本機 .env 的金鑰，不印出金鑰本身；閘道回的錯誤訊息會印出來（裡面若出現金鑰就換成 ***）。
花費：一次 embedding＋一次很短的判讀，合計不到 USD 0.001。

    .\venv\Scripts\python scripts\cgu_diagnose.py

看結果：
- 401：金鑰被重置或打錯 → 到閘道頁面複製新金鑰，換掉本機 .env 與 Render 的 CGU_API_KEY、EMBED_API_KEY（四個地方）
- 403：閘道拒絕這把金鑰做這件事 → 看下面印出的閘道訊息；本機正常、只有正式站 403 時，多半是 Render 的 EMBED_API_KEY 和這裡不同
- 402／429：額度用完／太頻繁 → 等額度重置或晚點再試
- 逾時、5xx：閘道本身的問題 → 晚點再試
"""
import os
import sys
from pathlib import Path

os.environ.setdefault("STORAGE_BACKEND", "local")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import requests  # noqa: E402

from app.config import settings  # noqa: E402

HINTS = {
    401: "金鑰被重置或打錯：到 https://air.cgu.edu.tw/workspace4/LLMAPI/index.php 複製新金鑰，換掉四個地方",
    402: "額度用完：等週四重置",
    403: "閘道拒絕：看上面的閘道訊息",
    404: "閘道沒有這個模型",
    429: "請求太頻繁：晚點再試",
}


def say(msg: str) -> None:
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        enc = getattr(sys.stdout, "encoding", None) or "ascii"
        print(msg.encode(enc, "replace").decode(enc, "replace"), flush=True)


def gateway_message(r: requests.Response, secrets) -> str:
    """閘道回的錯誤訊息（JSON 的 error.message 或原文前 300 字），金鑰換成 ***。"""
    try:
        body = r.json()
        err = body.get("error") if isinstance(body, dict) else None
        text = (err.get("message") if isinstance(err, dict) else err) or body.get("detail") or body.get("message") or str(body)
    except ValueError:
        text = r.text
    text = str(text)[:300]
    for s in secrets:
        if s:
            text = text.replace(s, "***")
    return text.replace("\n", " ")


def check(name: str, method: str, url: str, key: str, secrets, json_body=None) -> int:
    try:
        r = requests.request(method, url, headers={"Authorization": f"Bearer {key}"}, json=json_body, timeout=60)
    except requests.RequestException as exc:
        say(f"- {name}：連不上（{type(exc).__name__}）")
        return 0
    if r.ok:
        say(f"- {name}：正常（HTTP {r.status_code}）")
    else:
        say(f"- {name}：HTTP {r.status_code}；閘道訊息：{gateway_message(r, secrets)}")
        if r.status_code in HINTS:
            say(f"  → {HINTS[r.status_code]}")
    return r.status_code


def main() -> int:
    base = (settings.CGU_BASE_URL or "").rstrip("/")
    embed_base = (settings.EMBED_RELAY_URL or base).rstrip("/")
    cgu = (settings.CGU_API_KEY or "").strip()
    emb = (settings.EMBED_API_KEY or "").strip()
    secrets = [cgu, emb]
    say("CGU 閘道診斷（只讀本機 .env，不印金鑰）")
    say(f"- CGU_API_KEY：{'有' if cgu else '沒有'}；EMBED_API_KEY：{'有' if emb else '沒有（embedding 用 CGU_API_KEY）'}"
        + (f"；兩把{'相同' if emb == cgu else '不同'}" if cgu and emb else ""))
    if not cgu:
        say("沒有 CGU_API_KEY，無法診斷")
        return 1
    check("模型清單 /models（不花錢）", "GET", f"{base}/models", cgu, secrets)
    try:
        usage = requests.get(f"{base}/me/usage", headers={"Authorization": f"Bearer {cgu}"}, timeout=30)
        pool = (usage.json() or {}).get("openai") or {} if usage.ok else {}
        say(f"- 額度 /me/usage：HTTP {usage.status_code}" + (
            f"；本週已用 USD {pool.get('cost_usd')}、剩 USD {pool.get('remaining_usd')}（額度 {pool.get('quota_usd')}）" if pool else ""))
    except (requests.RequestException, ValueError) as exc:
        say(f"- 額度 /me/usage：讀不到（{type(exc).__name__}）")
    body = {"model": settings.EMBED_MODEL, "input": "CGU embedding test"}
    check(f"embedding（{settings.EMBED_MODEL}，CGU_API_KEY）", "POST", f"{embed_base}/embeddings", cgu, secrets, body)
    if emb and emb != cgu:
        check(f"embedding（{settings.EMBED_MODEL}，EMBED_API_KEY）", "POST", f"{embed_base}/embeddings", emb, secrets, body)
    check(f"判讀（{settings.CGU_MODEL}，很短的一句）", "POST", f"{base}/responses", cgu, secrets,
          {"model": settings.CGU_MODEL, "input": "Reply with the single word OK.", "max_output_tokens": 200})
    return 0


if __name__ == "__main__":
    sys.exit(main())
