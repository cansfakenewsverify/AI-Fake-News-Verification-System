"""
研究批次的環境檢查（GitHub Actions `research-env-check` 用；只用標準函式庫，不必 pip install，不花額度）。

信心程度驗證與模型比較（docs/test/信心程度驗證計畫.md、docs/test/模型比較計畫.md）要在 GitHub 的機器上跑：
雲端 session 沒有金鑰、也連不到 CGU 與查核網站（AGENTS.md 第 2 節）。開跑前先確認：

1. repository secret CGU_API_KEY 有沒有設（只印「有／沒有」，不印值）
2. 連不連得到 CGU 閘道與三個查核來源（有 HTTP 回應就算連得到，401／403 代表連得到、只是沒授權）
3. CGU /me/usage：本週已用、額度、剩餘，以及扣掉保留額（USD 3，留給網站使用者）後還能花多少
4. CGU /models：閘道目前列出的模型（不花額度）
5. 今天（台灣時間）適不適合跑花錢的批次：週日有每週評測，避開

結果印在 log，也寫進 GitHub 的執行摘要（$GITHUB_STEP_SUMMARY）。
金鑰沒設或有網域連不到時結束碼為 1（workflow 變紅）。

    python scripts/research_env_check.py
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

CGU_BASE = os.environ.get("CGU_BASE_URL", "").strip().rstrip("/") or "https://air.cgu.edu.tw/cgullmapi/v1"
RESERVE_USD = 3.0
TZ_TAIPEI = timezone(timedelta(hours=8))
WEEKDAYS = "一二三四五六日"
UA = {"User-Agent": "fakenewsverify-research/1.0 (+https://fakenewsverify.vercel.app)"}

# (名稱, 方法, 網址, POST 內容)：每個網域打一個最輕的請求
PROBES = [
    ("air.cgu.edu.tw", "GET", f"{CGU_BASE}/models", None),
    ("www.mygopen.com", "GET", "https://www.mygopen.com/feeds/posts/summary?alt=json&max-results=1", None),
    ("tfc-taiwan.org.tw", "GET", "https://tfc-taiwan.org.tw/wp-json/wp/v2/fact-check-reports?per_page=1&_fields=id", None),
    ("api.cofacts.tw", "POST", "https://api.cofacts.tw/graphql",
     {"query": "{ ListArticles(first: 1) { totalCount } }"}),
    ("cofacts.tw", "GET", "https://cofacts.tw/", None),
]


def request(method: str, url: str, body=None, headers=None, timeout: float = 25.0):
    """→ (HTTP 狀態碼或 None, 回應內容 bytes, 秒數, 錯誤說明)。HTTP 錯誤碼也算有回應。"""
    data = json.dumps(body).encode("utf-8") if body is not None else None
    h = {**UA, **(headers or {})}
    if data is not None:
        h["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=h, method=method)
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read(), time.monotonic() - t0, ""
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read() or b"", time.monotonic() - t0, ""
    except Exception as exc:  # 逾時、DNS、連線被拒
        return None, b"", time.monotonic() - t0, type(exc).__name__


def numbers_only(obj):
    """/me/usage 只留數字欄位（不印帳號名稱之類的文字）。"""
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            kept = numbers_only(v)
            if kept is not None and kept != {}:
                out[k] = kept
        return out
    if isinstance(obj, bool):
        return None
    if isinstance(obj, (int, float)):
        return obj
    return None


def main() -> int:
    lines = ["## 研究批次環境檢查", ""]
    problems = []
    now = datetime.now(TZ_TAIPEI)

    key = os.environ.get("CGU_API_KEY", "").strip()
    lines.append(f"- repository secret `CGU_API_KEY`：{'有' if key else '**沒有**'}")
    if not key:
        problems.append("CGU_API_KEY 沒有設")

    lines += ["", "### 連線", "", "| 網域 | 結果 | HTTP | 秒數 |", "|---|---|---:|---:|"]
    for name, method, url, body in PROBES:
        status, _, sec, err = request(method, url, body)
        ok = status is not None
        lines.append(f"| {name} | {'連得到' if ok else '**連不到**'} | {status or err} | {sec:.1f} |")
        if not ok:
            problems.append(f"{name} 連不到（{err}）")

    usage = None
    if key:
        auth = {"Authorization": f"Bearer {key}"}
        status, raw, _, err = request("GET", f"{CGU_BASE}/me/usage", headers=auth)
        lines += ["", "### CGU 額度（/me/usage）", ""]
        if status == 200:
            usage = numbers_only(json.loads(raw.decode("utf-8")))
            pool = usage.get("openai") or {}
            remaining = pool.get("remaining_usd")
            lines.append(f"- OpenAI 額度：本週已用 USD {pool.get('cost_usd', '?')}，額度 USD {pool.get('quota_usd', '?')}，"
                         f"剩 USD {remaining if remaining is not None else '?'}")
            if isinstance(remaining, (int, float)):
                lines.append(f"- 扣掉保留額 USD {RESERVE_USD:.0f}（留給網站使用者）後可用：USD {max(remaining - RESERVE_USD, 0):.2f}")
            others = {k: v for k, v in usage.items() if k != "openai"}
            if others:
                lines.append(f"- 其他額度（只列數字欄位）：`{json.dumps(others, ensure_ascii=False)}`")
        else:
            lines.append(f"- 讀不到（HTTP {status or err}）")
            problems.append(f"/me/usage 讀不到（HTTP {status or err}）")

        status, raw, _, err = request("GET", f"{CGU_BASE}/models", headers=auth)
        lines += ["", "### CGU 模型清單（/models）", ""]
        if status == 200:
            data = json.loads(raw.decode("utf-8"))
            items = data.get("data") if isinstance(data, dict) else data
            ids = sorted(str(m.get("id") if isinstance(m, dict) else m) for m in (items or []))
            lines.append(f"- 共 {len(ids)} 個：" + "、".join(f"`{i}`" for i in ids))
        else:
            lines.append(f"- 讀不到（HTTP {status or err}）")

    weekday = WEEKDAYS[now.weekday()]
    lines += ["", "### 今天", "",
              f"- 台灣時間 {now:%Y-%m-%d %H:%M}（星期{weekday}）"]
    if now.weekday() == 6:
        lines.append("- 週日有每週評測（21:17）：**今天不跑花錢的批次**")
    elif now.weekday() in (2, 3):
        lines.append("- 額度在週四重置（台灣時間週四 03:00～週五 03:00 之間）：花錢的批次等剩餘額度回到滿額再跑")
    else:
        lines.append("- 可以跑花錢的批次（照 AGENTS.md 第 4 節：先試跑 50 題、保留 USD 3）")

    lines += ["", "結論：" + ("全部正常" if not problems else "；".join(problems))]
    text = "\n".join(lines) + "\n"
    print(text, flush=True)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write(text)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
