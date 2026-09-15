"""
確保 code/backend/.env 有非空的 ADMIN_TOKEN（spec §5.6）。

start.bat / start.sh 每次啟動都會呼叫：
- 已有非空值：不動
- 有 `ADMIN_TOKEN=` 空行：填入 32 字亂數
- 沒有這一行：在檔尾加上
token 本體永遠不印出。

    python scripts/ensure_admin_token.py [path/to/.env]
"""
import re
import secrets
import sys
from pathlib import Path

LINE_RE = re.compile(r"(?m)^ADMIN_TOKEN=[ \t]*(\S*)[ \t]*(\r?)$")


def ensure(path: Path) -> str:
    if not path.exists():
        return "missing_env"
    with path.open(encoding="utf-8", newline="") as f:  # 保留原本的 CRLF／LF
        text = f.read()
    m = LINE_RE.search(text)
    if m and m.group(1):
        return "kept"
    token = secrets.token_hex(16)
    if m:
        text = text[: m.start()] + f"ADMIN_TOKEN={token}{m.group(2)}" + text[m.end():]
        result = "filled"
    else:
        newline = "\r\n" if "\r\n" in text else "\n"
        if text and not text.endswith(("\n", "\r\n")):
            text += newline
        text += f"ADMIN_TOKEN={token}{newline}"
        result = "appended"
    with path.open("w", encoding="utf-8", newline="") as f:
        f.write(text)
    return result


def main() -> None:
    default = Path(__file__).resolve().parents[1] / ".env"
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else default
    result = ensure(path)
    messages = {
        "kept": "[Setup] ADMIN_TOKEN already set",
        "filled": "[Setup] ADMIN_TOKEN generated in .env (32 chars, not shown)",
        "appended": "[Setup] ADMIN_TOKEN added to .env (32 chars, not shown)",
        "missing_env": "[Setup] .env not found, ADMIN_TOKEN skipped",
    }
    print(messages[result])


if __name__ == "__main__":
    main()
