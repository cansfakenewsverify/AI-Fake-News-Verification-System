r"""
學校新的向量服務（Mercury，2026-11-05 負責人轉來的範例）能不能直接接上：只讀、不改任何設定。

在負責人電腦的 code\backend 執行，貼上 Mercury 的金鑰（畫面不會顯示）：

    .\venv\Scripts\python scripts\mercury_check.py

做的事：
1. GET {base}/models：列出 Mercury 有哪些模型。
2. 對每個看起來是 embedding 的模型（名稱含 embed、bge），送一段測試文字，印出狀態碼與向量維度。
3. 最後一行說結論：
   - 有 text-embedding-3-small（1536 維）：只要把 EMBED_RELAY_URL 與 EMBED_API_KEY 換成 Mercury 的，知識庫的向量都不用重算。
   - 只有 bge-m3 這類（1024 維）：要重算整個知識庫的向量、重新校準相似度門檻（0.75 是 text-embedding-3-small 量出來的）。
金鑰不印出來；也可以先設環境變數 MERCURY_API_KEY 再執行。每次測試只送幾個字，幾乎不花額度。
只用標準函式庫。Windows 主控台是 cp950，所以只印中英文。
"""
import argparse
import getpass
import json
import os
import sys
import urllib.error
import urllib.request

DEFAULT_BASE = "https://air.cgu.edu.tw/mercuryapi/v1"
CURRENT_MODEL = "text-embedding-3-small"
CURRENT_DIM = 1536


def say(msg: str) -> None:
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        enc = getattr(sys.stdout, "encoding", None) or "ascii"
        print(msg.encode(enc, "replace").decode(enc, "replace"), flush=True)


def call(method: str, url: str, key: str, body: dict = None, timeout: int = 30):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {key}")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as e:
        text = e.read().decode("utf-8", "replace")
        try:
            return e.code, json.loads(text)
        except ValueError:
            return e.code, {"raw": text[:300]}
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        return 0, {"error": str(e)[:300]}


def redact(obj, key: str) -> str:
    text = json.dumps(obj, ensure_ascii=False)[:300]
    return text.replace(key, "***") if key else text


def is_embedding(model_id: str) -> bool:
    m = model_id.lower()
    return "embed" in m or "bge" in m


def main() -> int:
    ap = argparse.ArgumentParser(description="Check whether the school's Mercury embedding service can replace the old one (read-only).")
    ap.add_argument("--base", default=DEFAULT_BASE, help=f"default {DEFAULT_BASE}")
    ap.add_argument("--model", action="append", default=[], help="also try this model name (repeatable)")
    args = ap.parse_args()
    base = args.base.rstrip("/")

    key = (os.environ.get("MERCURY_API_KEY") or "").strip() or getpass.getpass("貼上 Mercury 金鑰（不會顯示），按 Enter：").strip()
    if not key:
        say("沒有金鑰，結束。")
        return 2

    say(f"== 1. 模型清單 GET {base}/models")
    code, body = call("GET", f"{base}/models", key)
    ids = []
    if code == 200:
        ids = sorted({m.get("id") for m in body.get("data", []) if isinstance(m, dict) and m.get("id")})
        say(f"   http 200，{len(ids)} 個模型：{', '.join(ids) if ids else '(空)'}")
    else:
        say(f"   http {code}：{redact(body, key)}")
        say("   讀不到模型清單，下面直接試常見的模型名稱。")

    candidates = [m for m in ids if is_embedding(m)]
    for m in [CURRENT_MODEL, "bge-m3", *args.model]:
        if m not in candidates:
            candidates.append(m)

    say(f"== 2. 每個 embedding 模型送一段測試文字 POST {base}/embeddings")
    ok = {}
    for m in candidates:
        code, body = call("POST", f"{base}/embeddings", key, {"model": m, "input": ["測試：冷水煮蛋營養會流失嗎"]})
        if code == 200 and body.get("data"):
            dim = len(body["data"][0].get("embedding") or [])
            ok[m] = dim
            say(f"   {m}: http 200，{dim} 維")
        else:
            say(f"   {m}: http {code}：{redact(body, key)}")

    say("== 3. 結論")
    if ok.get(CURRENT_MODEL) == CURRENT_DIM:
        say(f"   Mercury 有 {CURRENT_MODEL}（{CURRENT_DIM} 維）：只要把 EMBED_RELAY_URL 換成 {base}、EMBED_API_KEY 換成 Mercury 金鑰，")
        say("   知識庫的向量都不用重算。把這段結果截圖給 Claude。")
        return 0
    if ok:
        dims = "、".join(f"{m} {d} 維" for m, d in ok.items())
        say(f"   Mercury 沒有 {CURRENT_MODEL}，可用的是：{dims}。")
        say("   換過去要重算整個知識庫的向量、重新校準相似度門檻。把這段結果截圖給 Claude。")
        return 0
    say("   沒有任何 embedding 模型可用（金鑰、網址或權限不對）。把這段結果截圖給 Claude。")
    return 1


if __name__ == "__main__":
    sys.exit(main())
