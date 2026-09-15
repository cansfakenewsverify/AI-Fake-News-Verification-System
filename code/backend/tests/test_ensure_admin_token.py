import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "ensure_admin_token.py"
spec = importlib.util.spec_from_file_location("ensure_admin_token", SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def _token_line(text):
    return [line for line in text.splitlines() if line.startswith("ADMIN_TOKEN=")]


def test_fills_empty_line_and_keeps_other_lines(tmp_path):
    env = tmp_path / ".env"
    env.write_text("AI_PROVIDER=cgu\r\nADMIN_TOKEN=\r\nDEMO_MODE=false\r\n", encoding="utf-8", newline="")
    assert mod.ensure(env) == "filled"
    raw = env.read_bytes().decode("utf-8")
    lines = _token_line(raw)
    assert len(lines) == 1 and len(lines[0].split("=", 1)[1]) == 32
    assert "AI_PROVIDER=cgu\r\n" in raw and raw.endswith("DEMO_MODE=false\r\n")


def test_appends_when_missing(tmp_path):
    env = tmp_path / ".env"
    env.write_text("AI_PROVIDER=cgu", encoding="utf-8")
    assert mod.ensure(env) == "appended"
    lines = _token_line(env.read_text(encoding="utf-8"))
    assert len(lines) == 1 and len(lines[0].split("=", 1)[1]) == 32


def test_keeps_existing_token_and_is_idempotent(tmp_path):
    env = tmp_path / ".env"
    env.write_text("ADMIN_TOKEN=abc123\n", encoding="utf-8")
    assert mod.ensure(env) == "kept"
    assert env.read_text(encoding="utf-8") == "ADMIN_TOKEN=abc123\n"
    env2 = tmp_path / "second.env"
    env2.write_text("X=1\n", encoding="utf-8")
    mod.ensure(env2)
    first = env2.read_text(encoding="utf-8")
    assert mod.ensure(env2) == "kept"
    assert env2.read_text(encoding="utf-8") == first


def test_missing_env_file(tmp_path):
    assert mod.ensure(tmp_path / "nope.env") == "missing_env"
