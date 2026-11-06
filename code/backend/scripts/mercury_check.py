r"""
學校新的向量服務（Mercury，2026-11-05 負責人轉來的範例）能不能直接接上：只讀、不改任何設定。

在負責人電腦的 code\backend 執行：

    .\venv\Scripts\python scripts\mercury_check.py

金鑰從哪裡來（依序，重複的只試一次；金鑰本身不印出來，只印鍵名）：
- 環境變數 MERCURY_API_KEY；
- 本機 .env 的 EMBED_API_KEY（Mercury 金鑰和判讀的金鑰不同時，負責人把 Mercury 金鑰貼在這一格）；
- 本機 .env 的 CGU_API_KEY（判讀用的那把，順便看能不能一把金鑰兩邊都用）；
- 上面都沒有才請負責人貼上（畫面不會顯示）。

做的事：
1. GET {base}/models：列出 Mercury 有哪些模型（用第一把金鑰）。
2. 每把金鑰對每個看起來是 embedding 的模型（名稱含 embed、bge），送一段測試文字，印出狀態碼、向量維度與長度（norm）。
3. 第一把能用的金鑰再試一次批次（一次 8 段，含一段長文），印出耗時，給重算知識庫估時間用。
4. 最後一行說結論：
   - 有 text-embedding-3-small（1536 維）：只要把 EMBED_RELAY_URL 與 EMBED_API_KEY 換成 Mercury 的，知識庫的向量都不用重算。
   - 只有 bge-m3 這類（1024 維）：要重算整個知識庫的向量、重新校準相似度門檻（0.75 是 text-embedding-3-small 量出來的）。
每次測試只送幾句話；bge-m3 是學校本地模型，不計額度。
只用標準函式庫（讀 .env 時才用 app.config）。Windows 主控台是 cp950，所以只印中英文。
"""
import argparse
import getpass
import json
import math
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

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


def is_embedding(model_id: str) -> bool:
    m = model_id.lower()
    return "embed" in m or "bge" in m


def keys_from_env_file() -> list:
    """(鍵名, 金鑰)：讀 code/backend/.env（透過 app.config.settings，和後端讀的是同一份）；讀不到就回空。"""
    backend = Path(__file__).resolve().parent.parent
    if not (backend / ".env").exists():
        return []
    sys.path.insert(0, str(backend))
    cwd = os.getcwd()
    try:
        os.chdir(backend)  # pydantic 的 env_file 是相對路徑
        from app.config import settings
        return [("EMBED_API_KEY", (settings.EMBED_API_KEY or "").strip()),
                ("CGU_API_KEY", (settings.CGU_API_KEY or "").strip())]
    except Exception as e:  # noqa: BLE001 — 只是少一個金鑰來源
        say(f"   （讀不到 .env 的設定：{type(e).__name__}）")
        return []
    finally:
        os.chdir(cwd)


def collect_keys() -> list:
    found, seen = [], {}
    for name, key in [("MERCURY_API_KEY", (os.environ.get("MERCURY_API_KEY") or "").strip()), *keys_from_env_file()]:
        if not key:
            continue
        if key in seen:
            say(f"   {name} 和 {seen[key]} 是同一把，不重複試")
            continue
        seen[key] = name
        found.append((name, key))
    if not found:
        key = getpass.getpass("貼上 Mercury 金鑰（不會顯示），按 Enter：").strip()
        if key:
            found.append(("貼上的金鑰", key))
    return found


def embed(base: str, key: str, model: str, texts: list, timeout: int = 60):
    t0 = time.monotonic()
    code, body = call("POST", f"{base}/embeddings", key, {"model": model, "input": texts}, timeout=timeout)
    return code, body, time.monotonic() - t0


def main() -> int:
    ap = argparse.ArgumentParser(description="Check whether the school's Mercury embedding service can replace the old one (read-only).")
    ap.add_argument("--base", default=DEFAULT_BASE, help=f"default {DEFAULT_BASE}")
    ap.add_argument("--model", action="append", default=[], help="also try this model name (repeatable)")
    args = ap.parse_args()
    base = args.base.rstrip("/")

    say("== 0. 金鑰來源（只印鍵名）")
    keys = collect_keys()
    if not keys:
        say("沒有金鑰，結束。")
        return 2
    say(f"   要試的金鑰：{', '.join(n for n, _ in keys)}")
    all_keys = [k for _, k in keys]

    def scrub(obj) -> str:
        text = json.dumps(obj, ensure_ascii=False)[:300]
        for k in all_keys:
            text = text.replace(k, "***")
        return text

    say(f"== 1. 模型清單 GET {base}/models")
    ids = []
    for name, key in keys:
        code, body = call("GET", f"{base}/models", key)
        if code == 200:
            ids = sorted({m.get("id") for m in body.get("data", []) if isinstance(m, dict) and m.get("id")})
            say(f"   用 {name}：http 200，{len(ids)} 個模型：{', '.join(ids) if ids else '(空)'}")
            break
        say(f"   用 {name}：http {code}：{scrub(body)}")
    if not ids:
        say("   讀不到模型清單，下面直接試常見的模型名稱。")

    candidates = [m for m in ids if is_embedding(m)]
    for m in [CURRENT_MODEL, "bge-m3", *args.model]:
        if m not in candidates:
            candidates.append(m)

    say(f"== 2. 每把金鑰、每個 embedding 模型送一段測試文字 POST {base}/embeddings")
    ok = {}          # model -> dim
    working = {}     # model -> (key name, key)
    for name, key in keys:
        for m in candidates:
            code, body, secs = embed(base, key, m, ["測試：冷水煮蛋營養會流失嗎"], timeout=30)
            if code == 200 and body.get("data"):
                vec = body["data"][0].get("embedding") or []
                norm = math.sqrt(sum(x * x for x in vec)) if vec else 0.0
                ok[m] = len(vec)
                working.setdefault(m, (name, key))
                say(f"   {name} / {m}: http 200，{len(vec)} 維，norm {norm:.3f}，{secs:.1f} 秒")
            else:
                say(f"   {name} / {m}: http {code}：{scrub(body)}")

    if working:
        m = "bge-m3" if "bge-m3" in working else next(iter(working))
        name, key = working[m]
        say(f"== 3. 批次測試：{m}，一次 8 段（其中一段約 3000 字），用 {name}")
        batch = [f"測試句 {i}：網傳某某食物配某某會中毒，是真的嗎" for i in range(7)] + ["長文測試。" * 600]
        code, body, secs = embed(base, key, m, batch, timeout=120)
        if code == 200 and len(body.get("data") or []) == len(batch):
            usage = body.get("usage") or {}
            say(f"   http 200，回 {len(body['data'])} 筆，{secs:.1f} 秒；usage {scrub(usage)}")
        else:
            say(f"   http {code}，{secs:.1f} 秒：{scrub(body)}")
            say("   批次不行的話，重算知識庫要改成一次一筆（比較慢）。")

    say("== 4. 結論")
    if working:
        names = sorted({n for n, _ in working.values()})
        say(f"   能用 Mercury 向量的金鑰：{', '.join(names)}")
        if any(n == "CGU_API_KEY" for n in names):
            say("   判讀那把 CGU_API_KEY 就能用 Mercury：只要一把金鑰，EMBED_API_KEY 可以清空。")
        elif "EMBED_API_KEY" in names:
            say("   要兩把金鑰：Mercury 金鑰留在 EMBED_API_KEY，CGU_API_KEY 照舊給判讀用。")
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
