"""
Threads 機器人狀態與回覆紀錄（spec §6.4、FR-09 驗收 3、FR-10、FR-11）。

- data/threads_state.json：已回覆 id、since 游標、上次輪詢、每日計數、backoff、
  pending_publish、failed。讀取缺鍵補預設（相容舊格式 {"replied_ids":[...]}），
  寫入走同目錄 temp 檔 + os.replace 原子替換，crash 不會留下半寫的檔。
- data/threads_replies.jsonl：每則回覆一行（live/sim 共用），供 /api/threads/replies
  與 7.5「別把自己的判定貼文當謠言」的自我判斷。

backoff 相關鍵（spec §7.10；T-13）：
- backoff_until：UTC ISO 字串或 None；未到期時 run_threads_poll 整輪略過。
- backoff_n：連續 429 次數（下一次的指數）；成功一輪後歸零。
- transient_n：連續出現 5xx／逾時的輪數；滿 3 輪 → backoff 15 分鐘，成功一輪後歸零。
pending_publish（spec §7.6；T-12）：{mention_id: {container_id, created_at, reply_text, …}}，
  建好 container、publish 之前先寫入；下輪對同一 container 補發（不重跑 AI、不重建 container）。
failed：{mention_id: {count, final, reason, stage, status, at}}；final=true 為終態（不回覆、不重試、
  不進 replied_ids）。舊格式的整數值（失敗次數）讀取時相容。

所有函式都接受 data_dir，預設為模組層級 DATA_DIR（相對後端工作目錄，與其他 store 一致）。
"""
from __future__ import annotations

import copy
import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, Union

DATA_DIR = Path("data")
STATE_FILENAME = "threads_state.json"
REPLIES_FILENAME = "threads_replies.jsonl"

REPLIED_IDS_MAX = 2000
FAILED_MAX = 500                 # failed 只留最近 500 筆（游標前進後舊 mention 不會再被讀到）
BACKOFF_MAX_MINUTES = 60         # spec §7.10：429 backoff 上限（分鐘）
_BACKOFF_MAX_EXPONENT = 16       # 2^n 的 n 上限：只為避免無意義的大數，遠超過 60 分鐘上限
# 台灣無日光節約時間，固定 UTC+8（避免 Windows 缺 tzdata 時 zoneinfo 失敗）
TAIPEI_TZ = timezone(timedelta(hours=8), name="Asia/Taipei")

REPLY_RECORD_FIELDS = (
    "mention_id", "mode", "result_id", "frame_type", "risk_type", "username",
    "source_text_preview", "reply_text", "reply_id", "permalink", "replied_at",
)

_DEFAULT_STATE = {
    "replied_ids": [],
    "last_since": 0,
    "last_poll_at": None,
    "last_stats": None,
    "last_error": None,
    "daily": {"date": None, "replies": 0},
    "backoff_until": None,
    "backoff_n": 0,
    "transient_n": 0,
    "pending_publish": {},
    "failed": {},
}

PathLike = Union[str, Path]


def default_state() -> dict:
    return copy.deepcopy(_DEFAULT_STATE)


def _dir(data_dir: Optional[PathLike]) -> Path:
    return Path(data_dir) if data_dir is not None else DATA_DIR


def state_path(data_dir: Optional[PathLike] = None) -> Path:
    return _dir(data_dir) / STATE_FILENAME


def replies_path(data_dir: Optional[PathLike] = None) -> Path:
    return _dir(data_dir) / REPLIES_FILENAME


def taipei_today(now: Optional[datetime] = None) -> str:
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return now.astimezone(TAIPEI_TZ).date().isoformat()


def _roll_daily(state: dict, now: Optional[datetime] = None) -> None:
    """跨日（Asia/Taipei）自動重置每日回覆計數。"""
    today = taipei_today(now)
    daily = state.get("daily")
    if not isinstance(daily, dict) or daily.get("date") != today:
        state["daily"] = {"date": today, "replies": 0}
    else:
        daily.setdefault("replies", 0)


def _normalize(raw: object) -> dict:
    state = default_state()
    if isinstance(raw, dict):
        for key, value in raw.items():
            state[key] = value
    if not isinstance(state.get("replied_ids"), list):
        state["replied_ids"] = []
    if not isinstance(state.get("daily"), dict):
        state["daily"] = {"date": None, "replies": 0}
    else:
        state["daily"].setdefault("date", None)
        state["daily"].setdefault("replies", 0)
    for key in ("pending_publish", "failed"):
        if not isinstance(state.get(key), dict):
            state[key] = {}
    return state


def load_state(data_dir: Optional[PathLike] = None, now: Optional[datetime] = None) -> dict:
    """讀 threads_state.json；檔案不存在或損毀時回預設值，缺鍵補預設。"""
    path = state_path(data_dir)
    raw = None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raw = None
    state = _normalize(raw)
    _roll_daily(state, now)
    return state


def save_state(state: dict, data_dir: Optional[PathLike] = None,
               now: Optional[datetime] = None) -> None:
    """原子寫入：同目錄 temp 檔 → os.replace。失敗時原檔保持不變。"""
    state["replied_ids"] = list(state.get("replied_ids") or [])[-REPLIED_IDS_MAX:]
    failed = state.get("failed")
    if isinstance(failed, dict) and len(failed) > FAILED_MAX:
        state["failed"] = dict(list(failed.items())[-FAILED_MAX:])
    _roll_daily(state, now)

    path = state_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        # 前綴不加點：強制中斷殘留的 temp 檔仍符合 .gitignore 的 data/threads_*.json*
        prefix=f"{STATE_FILENAME}.", suffix=".tmp", dir=str(path.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(state, fh, ensure_ascii=False, indent=1)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


# ── backoff（spec §7.10；純函式，只改傳入的 state，寫檔由呼叫端 save_state 負責）──────
def _utc(now: Optional[datetime] = None) -> datetime:
    now = now or datetime.now(timezone.utc)
    return now if now.tzinfo is not None else now.replace(tzinfo=timezone.utc)


def parse_until(value: object) -> Optional[datetime]:
    """backoff_until → aware datetime。接受 UTC ISO 字串（含 Z／+0000 寫法）與 unix 秒數；
    空值、布林或無法解析 → None（視為沒有 backoff，不因壞資料讓輪詢永久停擺）。"""
    if value is None or value == "" or isinstance(value, bool):
        return None
    try:
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(float(value), tz=timezone.utc)
        s = str(value).strip()
        try:
            return datetime.fromtimestamp(float(s), tz=timezone.utc)
        except ValueError:
            pass
        s = s.replace("Z", "+00:00")
        if len(s) >= 5 and s[-5] in "+-" and s[-4:].isdigit():
            s = f"{s[:-2]}:{s[-2:]}"      # +0000 → +00:00
        dt = datetime.fromisoformat(s)
    except (ValueError, OverflowError, OSError):
        return None
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def backoff_remaining_seconds(state: dict, now: Optional[datetime] = None) -> float:
    """距離 backoff_until 還有幾秒；未設定、已到期或格式錯 → 0.0。"""
    until = parse_until(state.get("backoff_until"))
    if until is None:
        return 0.0
    return max(0.0, (until - _utc(now)).total_seconds())


def rate_limit_backoff_minutes(poll_minutes: object, n: object) -> float:
    """HTTP 429 的 backoff 長度（分鐘）= min(60, poll_interval × 2^n)；n = 先前已連續 429 的次數。"""
    try:
        base = float(poll_minutes)
    except (TypeError, ValueError):
        base = 1.0
    if not base > 0:
        base = 1.0
    try:
        exponent = int(n or 0)
    except (TypeError, ValueError):
        exponent = 0
    exponent = min(max(exponent, 0), _BACKOFF_MAX_EXPONENT)
    return float(min(BACKOFF_MAX_MINUTES, base * (2 ** exponent)))


def set_backoff(state: dict, minutes: float, now: Optional[datetime] = None) -> str:
    """backoff_until = max(仍有效的原值, now + minutes)；回傳寫入的 UTC ISO 字串。
    同一輪有多個觸發條件（例如 401 的 60 分與 transient 的 15 分）時取較晚者，不會被較短的蓋掉。"""
    now = _utc(now)
    until = now + timedelta(minutes=float(minutes))
    current = parse_until(state.get("backoff_until"))
    if current is not None and current > until:
        until = current
    state["backoff_until"] = until.astimezone(timezone.utc).isoformat()
    return state["backoff_until"]


def append_reply_record(rec: dict, data_dir: Optional[PathLike] = None) -> dict:
    """寫一行到 threads_replies.jsonl；缺欄位補 None，replied_at 缺時補現在（UTC ISO）。"""
    row = {field: rec.get(field) for field in REPLY_RECORD_FIELDS}
    if not row["replied_at"]:
        row["replied_at"] = datetime.now(timezone.utc).isoformat()
    path = replies_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    return row


def _iter_records(data_dir: Optional[PathLike]):
    path = replies_path(data_dir)
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        if isinstance(obj, dict):
            yield obj


def read_reply_records(limit: Optional[int] = 10,
                       data_dir: Optional[PathLike] = None) -> list:
    """倒序（最新在前）讀回覆紀錄；壞行略過。limit=None 或 <=0 表示全部。"""
    records = list(_iter_records(data_dir))
    records.reverse()
    if limit is not None and limit > 0:
        records = records[:limit]
    return records


def own_reply_ids(data_dir: Optional[PathLike] = None) -> set:
    """jsonl 中所有機器人自己發出的 reply_id（7.5 第一道自我判斷）。"""
    return {str(r["reply_id"]) for r in _iter_records(data_dir) if r.get("reply_id")}
