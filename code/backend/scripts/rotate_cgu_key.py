r"""
學校重置 CGU 金鑰時，一行換好（2026-10-29、11-01 兩次被強制重置，2026-11-03 舊金鑰被刪除，之後所有請求回 401／403）。

在負責人電腦的 code\backend 執行，貼上新金鑰（畫面不會顯示）：

    .\venv\Scripts\python scripts\rotate_cgu_key.py

做的事（任何一步失敗就停，前面沒做完的不會留半套）：
1. 先用新金鑰試一次模型清單與很短的判讀（不到 USD 0.001）；不通就停，什麼都不改。
   embedding 也試一次，但學校 2026-11-03 起關閉 embedding，不通只提醒、不擋（查證走關鍵字備援）。
2. 本機 .env：CGU_API_KEY 換成新金鑰；EMBED_API_KEY 清空。EMBED_API_KEY 空的時候程式一律用 CGU_API_KEY
   （ai_service.generate_embedding、factcheck_corpus.embed_batch），以後只要換一把。
3. Render：.env 有 RENDER_API_KEY 時，用 Render API 把服務 fakenewsverify-api 的 CGU_API_KEY 換新、刪掉 EMBED_API_KEY、
   重新部署。沒有 RENDER_API_KEY 就印出手動步驟（Render → Environment）。
金鑰本身不印出來；閘道或 Render 回的訊息裡出現金鑰就換成 ***。
"""
import argparse
import getpass
import os
import re
import sys
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

BACKEND = Path(__file__).resolve().parents[1]
ENV_FILE = BACKEND / ".env"
CGU_BASE = "https://air.cgu.edu.tw/cgullmapi/v1"
RENDER_API = "https://api.render.com/v1"
SERVICE_NAME = "fakenewsverify-api"
GATEWAY_PAGE = "https://air.cgu.edu.tw/mercuryapi/me"
CHECK_MODEL = "gpt-5.6-luna"

import requests  # noqa: E402


def say(msg: str) -> None:
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        enc = getattr(sys.stdout, "encoding", None) or "ascii"
        print(msg.encode(enc, "replace").decode(enc, "replace"), flush=True)


def redact(text: str, secrets: List[str]) -> str:
    for s in secrets:
        if s:
            text = text.replace(s, "***")
    return text.replace("\n", " ")[:300]


def read_env(path: Path) -> Dict[str, str]:
    """只讀 KEY=VALUE（去掉引號）；給程式用，不印出。"""
    values = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        m = re.match(r"\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$", line)
        if m and not line.lstrip().startswith("#"):
            values[m.group(1)] = m.group(2).strip().strip('"').strip("'")
    return values


def rewrite_env(text: str, new_key: str) -> str:
    """CGU_API_KEY 換成新金鑰（沒有這行就加）；EMBED_API_KEY 清空。其他行原樣保留。"""
    lines = text.splitlines(keepends=True)
    found = False
    for i, line in enumerate(lines):
        end = "\n" if line.endswith("\n") else ""
        if re.match(r"\s*CGU_API_KEY\s*=", line):
            lines[i] = f"CGU_API_KEY={new_key}{end}"
            found = True
        elif re.match(r"\s*EMBED_API_KEY\s*=", line):
            lines[i] = f"EMBED_API_KEY={end}"
    if not found:
        if lines and not lines[-1].endswith("\n"):
            lines[-1] += "\n"
        lines.append(f"CGU_API_KEY={new_key}\n")
    return "".join(lines)


def check_key(base: str, key: str, http=requests, model: str = CHECK_MODEL) -> Tuple[bool, str]:
    """新金鑰能不能讀模型清單、做一次判讀。→ (通不通, 說明)。embedding 不通只寫進說明，不算金鑰不能用。"""
    headers = {"Authorization": f"Bearer {key}"}
    try:
        r = http.get(f"{base}/models", headers=headers, timeout=30)
        if r.status_code != 200:
            return False, f"模型清單 HTTP {r.status_code}：{redact(r.text, [key])}"
        r = http.post(f"{base}/responses", headers=headers, timeout=90,
                      json={"model": model, "input": "只回一個字：好", "max_output_tokens": 32})
        if r.status_code != 200:
            return False, f"判讀 HTTP {r.status_code}：{redact(r.text, [key])}"
        r = http.post(f"{base}/embeddings", headers=headers, timeout=60,
                      json={"model": "text-embedding-3-small", "input": "key rotation test"})
    except requests.RequestException as exc:
        return False, f"連不上 CGU 閘道（{type(exc).__name__}）"
    if r.status_code != 200:
        return True, f"模型清單與判讀都正常；embedding HTTP {r.status_code}，不影響換金鑰，查證走關鍵字備援"
    return True, "模型清單、判讀與 embedding 都正常"


def update_render(render_key: str, new_key: str, service_id: Optional[str] = None, http=requests) -> List[str]:
    """Render API：CGU_API_KEY 換新、刪 EMBED_API_KEY、重新部署。→ 每一步的結果；失敗時丟 RuntimeError。"""
    headers = {"Authorization": f"Bearer {render_key}", "Accept": "application/json"}
    secrets = [render_key, new_key]
    done = []
    if not service_id:
        r = http.get(f"{RENDER_API}/services", headers=headers, params={"name": SERVICE_NAME, "limit": 20}, timeout=30)
        if r.status_code != 200:
            raise RuntimeError(f"找服務 HTTP {r.status_code}：{redact(r.text, secrets)}")
        matches = [(item.get("service") or item) for item in r.json()]
        matches = [s for s in matches if s.get("name") == SERVICE_NAME]
        if len(matches) != 1:
            raise RuntimeError(f"找到 {len(matches)} 個名為 {SERVICE_NAME} 的服務")
        service_id = matches[0]["id"]
    base = f"{RENDER_API}/services/{service_id}"
    r = http.put(f"{base}/env-vars/CGU_API_KEY", headers=headers, json={"value": new_key}, timeout=30)
    if r.status_code not in (200, 201):
        raise RuntimeError(f"更新 CGU_API_KEY HTTP {r.status_code}：{redact(r.text, secrets)}")
    done.append("Render 的 CGU_API_KEY 已換成新金鑰")
    r = http.delete(f"{base}/env-vars/EMBED_API_KEY", headers=headers, timeout=30)
    if r.status_code in (200, 204):
        done.append("Render 的 EMBED_API_KEY 已刪除（之後用 CGU_API_KEY）")
    elif r.status_code == 404:
        done.append("Render 本來就沒有 EMBED_API_KEY")
    else:
        raise RuntimeError(f"刪除 EMBED_API_KEY HTTP {r.status_code}：{redact(r.text, secrets)}")
    r = http.post(f"{base}/deploys", headers=headers, json={}, timeout=30)
    if r.status_code not in (200, 201, 202):
        raise RuntimeError(f"重新部署 HTTP {r.status_code}：{redact(r.text, secrets)}")
    done.append("Render 已開始重新部署（約 3 分鐘）")
    return done


MANUAL_RENDER = [
    "Render 要手動改（一次一步）：",
    "1. 打開 https://dashboard.render.com → 點服務 fakenewsverify-api → 左邊 Environment",
    "2. CGU_API_KEY 那一列按編輯，貼上新金鑰",
    "3. 有 EMBED_API_KEY 那一列的話，按垃圾桶刪掉（之後程式用 CGU_API_KEY）",
    "4. 按 Save and deploy，等約 3 分鐘",
    "（想以後連這步都免：在 Render 的 Account Settings → API Keys 建一把，貼進 .env 的 RENDER_API_KEY=，下次這支程式會自動改）",
]


def main(argv: Optional[List[str]] = None, ask: Callable[[str], str] = getpass.getpass, http=requests,
         env_file: Path = ENV_FILE) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--skip-render", action="store_true", help="only update the local .env")
    args = parser.parse_args(argv)
    if not env_file.exists():
        say(f"找不到 {env_file}：先照 code/backend/README.md 建立 .env")
        return 1
    env = read_env(env_file)
    base = (env.get("CGU_BASE_URL") or CGU_BASE).rstrip("/")
    say(f"到 {GATEWAY_PAGE} 複製新的金鑰。")
    new_key = ask("貼上新的 CGU 金鑰後按 Enter（畫面不會顯示）：").strip()
    if not new_key:
        say("沒有貼上金鑰，什麼都沒改")
        return 1
    ok, detail = check_key(base, new_key, http, env.get("CGU_MODEL") or CHECK_MODEL)
    say(f"1. 試新金鑰：{detail}")
    if not ok:
        say("新金鑰不能用，什麼都沒改。確認複製的是閘道頁面上最新的那一把。")
        return 1
    text = env_file.read_text(encoding="utf-8")
    tmp = env_file.with_name(".env.rotate.local")   # 符合 .gitignore 的 .env.*.local，萬一沒換成功也不會被 commit
    tmp.write_text(rewrite_env(text, new_key), encoding="utf-8")
    os.replace(tmp, env_file)
    say("2. 本機 .env：CGU_API_KEY 已換新，EMBED_API_KEY 已清空（之後只要換 CGU_API_KEY 一把）。本機後端有開的話要重開。")
    if args.skip_render:
        say("3. 略過 Render（--skip-render）")
        return 0
    render_key = env.get("RENDER_API_KEY", "")
    if not render_key:
        say("3. .env 沒有 RENDER_API_KEY，Render 要手動改：")
        for line in MANUAL_RENDER[1:]:
            say("   " + line)
        return 0
    try:
        for line in update_render(render_key, new_key, env.get("RENDER_SERVICE_ID") or None, http):
            say(f"3. {line}")
    except (RuntimeError, requests.RequestException) as exc:
        say(f"3. Render 沒改成功：{exc if isinstance(exc, RuntimeError) else type(exc).__name__}")
        for line in MANUAL_RENDER:
            say("   " + line)
        return 1
    say("完成。約 3 分鐘後打開 https://fakenewsverify.vercel.app 查一則沒查過的訊息，不再出現「AI 分析暫時無法使用」就是好了。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
