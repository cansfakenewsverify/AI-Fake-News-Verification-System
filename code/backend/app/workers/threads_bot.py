"""
Threads 查核機器人 — 輪詢 mentions → 三層快取＋AI 分析 → 自動回覆（spec §7.4、§7.5）。

單則 mention 處理 handle_mention()（spec §7.5）：
  1. resolve_target() 決定要查的對象與種類：
     - replied_to.id 是機器人自己發過的回覆（threads_replies.jsonl 的 reply_id）→ self（零 API 成本）
     - 讀原貼文（get_post）：作者是機器人 → self；去 @ 後 ≥8 字 → text；
       IMAGE／VIDEO／CAROUSEL_ALBUM 且文字 <8 字 → media_only；其餘文字太短 → too_short；
       HTTP 4xx（429 除外）→ unreadable；429／5xx／連線失敗 → transient（不標記，下輪重試）
     - 沒有 replied_to：用 mention 本文，≥8 字 → text，否則 too_short
     - text 去掉網址後 <8 字且含 http(s) → input_type="url"（走 FR-02）
     永不以 media_type == "TEXT" 判斷；絕不把「@bot 幫我查」這種請求句送進 AI。
  2. self → 只標記；media_only／unreadable／too_short → 回固定文案、標記、寫 jsonl。
  3. text → 建任務 → process_analysis_task_async → AI 不可用（fallback）→ 不回覆、不標記（下輪補回）
     → format_verdict_reply → reply_to → 成功才標記。

防重複回覆：reply_to 成功後「先」原子寫 state（replied_ids），再寫 jsonl／任務欄位；
中途 crash 只可能漏記 jsonl，不會讓同一則 mention 在下輪再被回覆。

輪詢 run_threads_poll()（spec §7.4）：
  - mode off 或 client 不可用 → {"started": False}；token 過期（invalid_reason）同時寫 state.last_error
  - backoff_until 未到 → {"skipped": "backoff"}
  - 互斥：模組級 asyncio.Lock（同行程）＋ data/threads_poll.lock（跨行程，O_CREAT|O_EXCL，
    內容 pid／時間；超過 15 分鐘視為殘留可接手）；被佔用 → 丟 PollInProgress（API 對應 409）
  - since = max(last_since − 120, 1688540400)；mentions 依 timestamp 升冪逐則處理
  - 本地上限：本輪「經 AI 的判定回覆」≥ THREADS_MAX_REPLIES_PER_POLL，或當日判定回覆
    ≥ THREADS_MAX_REPLIES_PER_DAY → 停止本輪（固定文案回覆不經 AI，不計入，同 §7.5 只在判定路徑累加 daily）
  - 游標：全部處理完 → last_since = max(timestamp)（無 mention → now）；有 mention 留待下輪
    （AI 不可用、暫時錯誤、上限截斷）→ 停在最早那則之前，否則下輪的 since 會把它永久跳過

日誌一律走 logging（logger 名 threads_bot）；貼文／回覆文字以 repr() 記錄並把 cp950
無法編碼的字元（🔴🟡🟢 等 emoji）跳脫，避免 Windows 主控台 UnicodeEncodeError（CLAUDE.md §7）。
"""
from __future__ import annotations

import asyncio
import inspect
import json
import logging
import os
import re
import secrets
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Set, Tuple, Union

from app.config import settings
from app.services import threads_state
from app.services.store_factory import get_task_store
from app.services.task_store import TaskStore
from app.services.threads_reply import (
    format_verdict_reply,
    reply_cannot_read,
    reply_media_only,
    reply_too_short,
)
from app.services.threads_service import ThreadsApiError, get_threads_client
from app.services.threads_sim import _to_epoch
from app.utils.verdict import frame_of, is_fallback

logger = logging.getLogger("threads_bot")

PathLike = Union[str, Path]

MIN_TEXT_LEN = 8
# 正向清單（spec §7.5、FR-09 驗收 5）：只有這三種才算「只有圖片或影片」
MEDIA_TYPES = ("IMAGE", "VIDEO", "CAROUSEL_ALBUM")
PREVIEW_MAX = 200

SINCE_OVERLAP_SECONDS = 120      # 重疊 2 分鐘，避免時鐘偏差漏件
SINCE_FLOOR = 1688540400         # Threads API since 官方下限
LOCK_FILENAME = "threads_poll.lock"
LOCK_STALE_SECONDS = 15 * 60     # 超過視為殘留鎖（行程被砍沒釋放），可強制接手

# 同行程互斥（排程與 POST /api/threads/poll 共用）；只做非阻塞檢查＋立即取得，不排隊等待
_POLL_LOCK = asyncio.Lock()

KIND_SELF = "self"
KIND_TEXT = "text"
KIND_MEDIA_ONLY = "media_only"
KIND_UNREADABLE = "unreadable"
KIND_TOO_SHORT = "too_short"
KIND_TRANSIENT = "transient"      # 讀原貼文遇 429／5xx／連線失敗：不標記，下輪重試

OUT_REPLIED = "replied"           # 已回覆判定（走過 AI 管線）
OUT_FIXED_REPLY = "fixed_reply"   # 已回覆固定文案（不經 AI）
OUT_SELF = "self"                 # 自我貼文：標記、不回覆
OUT_AI_UNAVAILABLE = "ai_unavailable"
OUT_DEFERRED = "deferred"         # 本輪 AI 已不可用，其餘文字 mention 留待下輪
OUT_ERROR = "error"               # 未標記，下輪重試

_FIXED_REPLIES = {
    KIND_MEDIA_ONLY: reply_media_only,
    KIND_UNREADABLE: reply_cannot_read,
    KIND_TOO_SHORT: reply_too_short,
}

# @帳號：Threads handle 只有英數、底線、句點；前面不可緊接英數（避免吃掉 email），連同其後一個空白一起去掉
_MENTION_RE = re.compile(r"(?<![A-Za-z0-9_.])@[A-Za-z0-9_][A-Za-z0-9_.]*[ \t]?")
# 只收 ASCII 網址字元：中文與全形標點會自然截斷網址
_URL_RE = re.compile(r"https?://[A-Za-z0-9\-._~:/?#\[\]@!$&'()*+,;=%]+", re.IGNORECASE)
_URL_TRAILING = ".,;:!?"

# Windows 主控台（cp950）無法編碼的字元以 \\U 形式跳脫
_LOG_CODEC = "cp950"


def _esc(value: Any) -> str:
    return repr(value).encode(_LOG_CODEC, "backslashreplace").decode(_LOG_CODEC)


def _load_state() -> dict:
    """舊 import 相容（app/api/threads.py）；新程式請用 app.services.threads_state.load_state。"""
    return threads_state.load_state()


def strip_mentions(text: Any) -> str:
    """去掉 @帳號 標記，留下真正要查核的文字（只去 handle 與其後一個空白，保留原文換行）。"""
    return _MENTION_RE.sub("", str(text or "")).strip()


def _input_of(text: str) -> Tuple[str, str]:
    """spec §7.5 第 3 步：去網址後 <8 字且含 http(s) → ("url", 第一個網址)，否則 ("text", text)。"""
    match = _URL_RE.search(text)
    if match:
        rest = " ".join(_URL_RE.sub(" ", text).split())
        if len(rest) < MIN_TEXT_LEN:
            url = match.group(0).rstrip(_URL_TRAILING)
            scheme, _, remainder = url.partition("://")
            return "url", f"{scheme.lower()}://{remainder}"
    return "text", text


def _replied_to_id(mention: Dict[str, Any]) -> Optional[str]:
    """replied_to 可能是 {"id": ...}（Graph API／webhook 形狀）或純值。"""
    rt = mention.get("replied_to")
    if isinstance(rt, dict):
        rt = rt.get("id")
    return str(rt) if rt not in (None, "") else None


def _bot_handle(value: Optional[str] = None) -> str:
    raw = settings.BOT_HANDLE if value is None else value
    return str(raw or "").strip().lstrip("@").lower()


def _post_ref(post: Dict[str, Any], fallback_id: Optional[str] = None) -> Dict[str, Any]:
    return {
        "id": str(post.get("id") or fallback_id or "") or None,
        "username": post.get("username"),
        "permalink": post.get("permalink"),
        "media_type": post.get("media_type"),
        "text": post.get("text") or "",
    }


async def resolve_target(
    client: Any,
    m: Dict[str, Any],
    *,
    own_ids: Optional[Set[str]] = None,
    data_dir: Optional[PathLike] = None,
    bot_handle: Optional[str] = None,
) -> Tuple[str, Optional[str], str, Dict[str, Any]]:
    """回傳 (kind, text, input_type, target_post)；text 只有 kind == "text" 時非 None
    （input_type == "url" 時 text 為網址本身）。target_post 描述「被查核的貼文」。"""
    bot = _bot_handle(bot_handle)
    parent_id = _replied_to_id(m)

    if parent_id:
        if own_ids is None:
            own_ids = await asyncio.to_thread(threads_state.own_reply_ids, data_dir)
        if parent_id in own_ids:
            # 第一道自我判斷：有人回覆機器人自己的判定貼文再 @ 它（不打 API）
            return KIND_SELF, None, "text", {"id": parent_id}
        try:
            post = await asyncio.to_thread(client.get_post, parent_id)
        except ThreadsApiError as e:
            status = e.status
            # 以 HTTP 狀態碼分流（spec §7.10）；error.code 只記 log
            logger.warning(
                "get_post failed mention=%s post=%s status=%s body=%s",
                _esc(m.get("id")), _esc(parent_id), status, _esc(e.body),
            )
            if isinstance(status, int) and 400 <= status < 500 and status != 429:
                return KIND_UNREADABLE, None, "text", {"id": parent_id}
            return KIND_TRANSIENT, None, "text", {"id": parent_id}
        except Exception as e:  # 連線／解析失敗等非 API 錯誤：當作暫時性，下輪重試
            logger.warning(
                "get_post error mention=%s post=%s: %s", _esc(m.get("id")), _esc(parent_id), _esc(e),
            )
            return KIND_TRANSIENT, None, "text", {"id": parent_id}

        post = post if isinstance(post, dict) else {}
        target = _post_ref(post, parent_id)
        if bot and str(post.get("username") or "").lower() == bot:
            # 第二道自我判斷：原貼文作者是機器人
            return KIND_SELF, None, "text", target
        text = strip_mentions(post.get("text"))
        if len(text) >= MIN_TEXT_LEN:
            input_type, data = _input_of(text)
            return KIND_TEXT, data, input_type, target
        if str(post.get("media_type") or "").upper() in MEDIA_TYPES:
            return KIND_MEDIA_ONLY, None, "text", target
        # 原貼文可讀但沒有可用文字：不退回用 mention 本文（那通常只是「@bot 幫我查」）
        return KIND_TOO_SHORT, None, "text", target

    target = _post_ref(m)
    text = strip_mentions(m.get("text"))
    if len(text) >= MIN_TEXT_LEN:
        input_type, data = _input_of(text)
        return KIND_TEXT, data, input_type, target
    return KIND_TOO_SHORT, None, "text", target


class PollContext:
    """一輪輪詢共用的狀態（state 為記憶體中的權威版本，每則處理完即原子寫檔）。"""

    def __init__(
        self,
        client: Any,
        state: dict,
        mode: str,
        data_dir: Optional[PathLike] = None,
        task_store: Optional[TaskStore] = None,
        own_ids: Optional[Set[str]] = None,
    ):
        self.client = client
        self.state = state
        self.mode = mode
        self.origin = "threads_sim" if mode == "sim" else "threads"
        self.data_dir = data_dir
        if not task_store:
            if data_dir is None and settings.use_supabase:
                # 雲端資料層：任務與處理器（pandas_task_processor）寫同一個 Postgres tasks 表
                task_store = get_task_store()
            else:
                task_store = TaskStore(data_dir=str(data_dir) if data_dir is not None else "data")
        self.task_store = task_store
        self.bot_handle = _bot_handle()
        self.own_ids: Set[str] = set(own_ids or ())
        self.replied: Set[str] = {str(x) for x in state.get("replied_ids") or []}
        self.analyzed_replies = 0          # 本輪走過 AI 並已回覆的則數
        self.analysis_blocked = False      # 本輪已遇 AI 不可用：其餘文字 mention 不再送 AI
        self.last_error: Optional[str] = None
        try:
            self._reply_takes_result_id = "result_id" in inspect.signature(client.reply_to).parameters
        except (TypeError, ValueError):
            self._reply_takes_result_id = False

    async def mark(self, mention_id: str, *, analyzed: bool = False) -> None:
        """標記已處理並立即原子寫 state；analyzed=True 時計入每日回覆數。"""
        if mention_id not in self.replied:
            self.replied.add(mention_id)
            self.state.setdefault("replied_ids", []).append(mention_id)
        if analyzed:
            daily = _daily(self.state)
            daily["replies"] = int(daily.get("replies") or 0) + 1
            self.analyzed_replies += 1
        await asyncio.to_thread(threads_state.save_state, self.state, self.data_dir)


def _daily(state: dict) -> dict:
    """當日（Asia/Taipei）計數；跨日自動歸零。"""
    today = threads_state.taipei_today()
    daily = state.get("daily")
    if not isinstance(daily, dict) or daily.get("date") != today:
        daily = state["daily"] = {"date": today, "replies": 0}
    return daily


def _sort_key(m: Dict[str, Any]) -> float:
    ts = _to_epoch(m.get("timestamp"))
    return ts if ts is not None else float("inf")


def _result_url(task_id: str) -> str:
    base = (settings.PUBLIC_BASE_URL or "").strip().rstrip("/")
    return f"{base}/r/{task_id}"


def _preview(text: Any) -> str:
    return str(text or "").strip()[:PREVIEW_MAX]


async def _send_reply(ctx: PollContext, mention_id: str, text: str, result_id: Optional[str]) -> Optional[str]:
    kwargs = {"result_id": result_id} if ctx._reply_takes_result_id else {}
    try:
        reply_id = await asyncio.to_thread(ctx.client.reply_to, mention_id, text, **kwargs)
    except ThreadsApiError as e:
        logger.warning(
            "reply_to failed mention=%s status=%s body=%s", _esc(mention_id), e.status, _esc(e.body),
        )
        return None
    except Exception as e:
        logger.warning("reply_to error mention=%s: %s", _esc(mention_id), _esc(e))
        return None
    if not reply_id:
        logger.warning("reply_to returned no id mention=%s", _esc(mention_id))
        return None
    logger.info("replied mention=%s reply_id=%s text=%s", _esc(mention_id), _esc(reply_id), _esc(text))
    return str(reply_id)


async def _record_reply(
    ctx: PollContext, mention_id: str, target: Dict[str, Any], reply_id: str, reply_text: str,
    result: Optional[Dict[str, Any]] = None, result_id: Optional[str] = None, frame_type: str = "yellow",
) -> None:
    """寫 threads_replies.jsonl（失敗只記 log：state 已先寫，不會造成重複回覆）。"""
    ctx.own_ids.add(reply_id)
    row = {
        "mention_id": mention_id,
        "mode": ctx.mode,
        "result_id": result_id,
        "frame_type": frame_type,
        "risk_type": (result or {}).get("risk_type"),
        "username": target.get("username"),
        "source_text_preview": _preview(target.get("text")) if target.get("text") is not None else None,
        "reply_text": reply_text,
        "reply_id": reply_id,
        "permalink": target.get("permalink"),
    }
    try:
        await asyncio.to_thread(threads_state.append_reply_record, row, ctx.data_dir)
    except Exception as e:
        logger.error("append_reply_record failed mention=%s: %s", _esc(mention_id), _esc(e))


async def handle_mention(ctx: PollContext, m: Dict[str, Any]) -> str:
    """處理單則 mention（spec §7.5），回傳 OUT_* 結果。reply_to 之前的錯誤一律吞下並回 OUT_ERROR
    （未標記、下輪重試）；reply_to 成功後寫 state 失敗則往外拋，讓整輪中止以免繼續回覆卻記不住。"""
    started = time.perf_counter()
    mention_id = str(m.get("id") or "")
    kind, text, input_type, target = await resolve_target(
        ctx.client, m, own_ids=ctx.own_ids, data_dir=ctx.data_dir, bot_handle=ctx.bot_handle,
    )
    result_id: Optional[str] = None
    cache_layer: Optional[str] = None

    if kind == KIND_SELF:
        await ctx.mark(mention_id)
        outcome = OUT_SELF
    elif kind == KIND_TRANSIENT:
        outcome = OUT_ERROR
    elif kind in _FIXED_REPLIES:
        reply_text = _FIXED_REPLIES[kind]()
        reply_id = await _send_reply(ctx, mention_id, reply_text, None)
        if reply_id:
            await ctx.mark(mention_id)
            await _record_reply(ctx, mention_id, target, reply_id, reply_text)
            outcome = OUT_FIXED_REPLY
        else:
            outcome = OUT_ERROR
    elif ctx.analysis_blocked:
        outcome = OUT_DEFERRED
    else:
        outcome, result_id, cache_layer = await _analyze_and_reply(ctx, mention_id, text or "", input_type, target)

    logger.info("mention %s", json.dumps({
        "mention_id": mention_id,
        "kind": kind,
        "outcome": outcome,
        "result_id": result_id,
        "cache_layer": cache_layer,
        "elapsed_ms": int((time.perf_counter() - started) * 1000),
    }, ensure_ascii=True))
    return outcome


async def _analyze_and_reply(
    ctx: PollContext, mention_id: str, text: str, input_type: str, target: Dict[str, Any],
) -> Tuple[str, Optional[str], Optional[str]]:
    # 延遲 import：app 啟動時不載入整條分析管線；測試以 monkeypatch 取代 process_analysis_task_async
    from app.workers import pandas_task_processor as proc

    platform_post = {
        "platform": "threads",
        "post_id": target.get("id"),
        "permalink": target.get("permalink"),
        "username": target.get("username"),
    }
    try:
        task_id = await asyncio.to_thread(
            ctx.task_store.create_task, "threads_mention", text,
            input_type=input_type, origin=ctx.origin,
            threads_mention_id=mention_id, platform_post=platform_post,
        )
    except Exception as e:
        logger.error("create_task failed mention=%s: %s", _esc(mention_id), _esc(e))
        return OUT_ERROR, None, None

    try:
        result = await proc.process_analysis_task_async(task_id, text, input_type)
    except Exception as e:
        logger.error("analysis failed mention=%s task=%s: %s", _esc(mention_id), task_id, _esc(e))
        return OUT_ERROR, task_id, None

    cache_layer = result.get("cache_layer") if isinstance(result, dict) else None
    if is_fallback(result):
        # FR-09 驗收 4：AI 不可用 → 不回覆、不標記，下輪補回；本輪其餘文字 mention 也不再送 AI
        ctx.analysis_blocked = True
        ctx.last_error = "ai_unavailable"
        logger.warning("AI unavailable, mention=%s left for next poll (task=%s)", _esc(mention_id), task_id)
        return OUT_AI_UNAVAILABLE, task_id, cache_layer

    try:
        reply_text = format_verdict_reply(result, _result_url(task_id))
    except Exception as e:
        logger.error("format_verdict_reply failed mention=%s: %s", _esc(mention_id), _esc(e))
        return OUT_ERROR, task_id, cache_layer

    reply_id = await _send_reply(ctx, mention_id, reply_text, task_id)
    if not reply_id:
        return OUT_ERROR, task_id, cache_layer

    await ctx.mark(mention_id, analyzed=True)
    frame_type = result.get("frame_type") or frame_of(result)[0]
    await _record_reply(ctx, mention_id, target, reply_id, reply_text, result, task_id, frame_type)
    try:
        await asyncio.to_thread(ctx.task_store.update_task, task_id, threads_reply_id=reply_id)
    except Exception as e:
        logger.error("update_task threads_reply_id failed task=%s: %s", task_id, _esc(e))
    return OUT_REPLIED, task_id, cache_layer


# ── 輪詢互斥（spec §7.4、§9 可靠性：單實例）──────────────────────────────
class PollInProgress(RuntimeError):
    """另一輪輪詢進行中（同行程 asyncio.Lock 或跨行程 threads_poll.lock 被佔用）；API 對應 409。"""

    code = "poll_in_progress"


def lock_path(data_dir: Optional[PathLike] = None) -> Path:
    return (Path(data_dir) if data_dir is not None else threads_state.DATA_DIR) / LOCK_FILENAME


def _read_lock(path: Path) -> Optional[dict]:
    try:
        info = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return info if isinstance(info, dict) else None


def _lock_age_seconds(path: Path) -> Optional[float]:
    """鎖檔年齡：優先讀內容的 created_at，讀不到（半寫、損毀）用檔案 mtime；檔案不存在 → None。"""
    now = time.time()
    info = _read_lock(path)
    created = (info or {}).get("created_at")
    if isinstance(created, (int, float)) and not isinstance(created, bool):
        return now - float(created)
    try:
        return now - path.stat().st_mtime
    except OSError:
        return None


def _acquire_file_lock(path: Path) -> str:
    """O_CREAT|O_EXCL 建鎖檔並寫入 pid／時間／token；被佔用且未逾 15 分鐘 → PollInProgress。回傳 token。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    token = f"{os.getpid()}-{secrets.token_hex(8)}"
    for attempt in range(2):
        try:
            fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            age = _lock_age_seconds(path)
            if attempt == 0 and (age is None or age > LOCK_STALE_SECONDS):
                if age is not None:
                    logger.warning("stale poll lock (%ds old) taken over: %s", int(age), _esc(str(path)))
                    try:
                        os.unlink(path)
                    except FileNotFoundError:
                        pass
                    except OSError as e:
                        raise PollInProgress(f"stale poll lock could not be removed: {e}") from None
                continue   # 殘留鎖已移除（或剛好被釋放）→ 再試一次
            raise PollInProgress("poll_in_progress") from None
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump({
                    "pid": os.getpid(),
                    "token": token,
                    "created_at": time.time(),
                    "created_iso": datetime.now(timezone.utc).isoformat(),
                }, fh)
        except BaseException:
            try:
                os.unlink(path)
            except OSError:
                pass
            raise
        return token
    raise PollInProgress("poll_in_progress")


def _release_file_lock(path: Path, token: str) -> None:
    """只刪自己的鎖（token 相符）；Windows 上防毒／同步軟體短暫佔用時重試幾次。"""
    info = _read_lock(path)
    if not info or info.get("token") != token:
        if path.exists():
            logger.warning("poll lock not released (owned by another poller): %s", _esc(str(path)))
        return
    for attempt in range(5):
        try:
            os.unlink(path)
            return
        except FileNotFoundError:
            return
        except PermissionError:
            time.sleep(0.05 * (attempt + 1))
    logger.error("poll lock could not be removed: %s", _esc(str(path)))


def poll_in_progress(data_dir: Optional[PathLike] = None) -> bool:
    """唯讀檢查是否有一輪正在跑（供 API 在排背景工作前回 409）。"""
    if _POLL_LOCK.locked():
        return True
    path = lock_path(data_dir)
    if not path.exists():
        return False
    age = _lock_age_seconds(path)
    return age is not None and age <= LOCK_STALE_SECONDS


# ── 輪詢一輪（spec §7.4）─────────────────────────────────────────────
def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _is_bot_author(ctx: PollContext, m: Dict[str, Any]) -> bool:
    return bool(ctx.bot_handle) and str(m.get("username") or "").lower() == ctx.bot_handle


def _mentions_error(status: Optional[int]) -> str:
    """mentions 端點失敗的 last_error（spec §7.10；backoff 另由 T-13 處理）。"""
    if status == 401:
        return "token_invalid"
    if status in (403, 404):
        return "permission_denied"
    return "mentions_failed"


def _record_client_error(data_dir: Optional[PathLike], error: str) -> None:
    state = threads_state.load_state(data_dir)
    if state.get("last_error") != error:
        state["last_error"] = error
        threads_state.save_state(state, data_dir)


def _next_since(mentions: list, ctx: PollContext, prev_since: int, now: int) -> int:
    """全部處理完 → max(timestamp)（不倒退；無 mention → now）。
    還有 mention 留待下輪（未標記、非機器人自己發的）→ 停在最早那則之前 1 秒，
    否則下輪 since = last_since − 120 會把它永久跳過；留待下輪的若沒有時間戳 → 游標不動。"""
    all_ts, pending_ts = [], []
    for m in mentions:
        ts = _to_epoch(m.get("timestamp"))
        if ts is not None:
            all_ts.append(ts)
        mention_id = str(m.get("id") or "")
        if not mention_id or mention_id in ctx.replied or _is_bot_author(ctx, m):
            continue
        if ts is None:
            return prev_since
        pending_ts.append(ts)
    if pending_ts:
        return int(min(pending_ts)) - 1
    if all_ts:
        return max(prev_since, int(max(all_ts)))
    return max(prev_since, now)


async def _finish_poll(state: dict, stats: dict, data_dir: Optional[PathLike], mode: str,
                       last_error: Optional[str], stopped: Optional[str] = None) -> dict:
    state["last_poll_at"] = datetime.now(timezone.utc).isoformat()
    state["last_stats"] = dict(stats)
    state["last_error"] = last_error
    await asyncio.to_thread(threads_state.save_state, state, data_dir)
    logger.info(
        "threads poll done mode=%s since_next=%s stopped=%s stats=%s last_error=%s",
        mode, state.get("last_since"), stopped, json.dumps(stats), last_error,
    )
    return {"started": True, **stats, "stopped": stopped}


async def _poll_once(client: Any, mode: str, data_dir: Optional[PathLike]) -> dict:
    stats = {"checked": 0, "replied": 0, "skipped": 0, "errors": 0}
    # 取得鎖之後才讀：拿到的是上一輪寫完的權威 state
    state = await asyncio.to_thread(threads_state.load_state, data_dir)
    prev_since = _as_int(state.get("last_since"))
    since = max(prev_since - SINCE_OVERLAP_SECONDS, SINCE_FLOOR)
    now = int(time.time())

    try:
        raw = await asyncio.to_thread(client.get_mentions, since)
    except ThreadsApiError as e:
        logger.error("get_mentions failed since=%s status=%s body=%s", since, e.status, _esc(e.body))
        stats["errors"] += 1
        return await _finish_poll(state, stats, data_dir, mode, _mentions_error(e.status))
    except Exception as e:
        logger.error("get_mentions error since=%s: %s", since, _esc(e))
        stats["errors"] += 1
        return await _finish_poll(state, stats, data_dir, mode, "mentions_failed")

    mentions = [m for m in raw or [] if isinstance(m, dict)]
    mentions.sort(key=_sort_key)
    state["last_error"] = None   # mentions 讀取成功：清掉上一輪的錯誤（本輪遇到新狀況會再設）
    own_ids = await asyncio.to_thread(threads_state.own_reply_ids, data_dir)
    ctx = PollContext(client, state, mode, data_dir=data_dir, own_ids=own_ids)
    max_per_poll = _as_int(settings.THREADS_MAX_REPLIES_PER_POLL)
    max_per_day = _as_int(settings.THREADS_MAX_REPLIES_PER_DAY)
    stopped: Optional[str] = None
    seen: Set[str] = set()

    for m in mentions:
        mention_id = str(m.get("id") or "")
        if not mention_id or mention_id in ctx.replied or mention_id in seen:
            continue   # 已處理過，或同一輪清單內重複出現（分頁重疊）
        seen.add(mention_id)
        if _is_bot_author(ctx, m):
            stats["checked"] += 1
            stats["skipped"] += 1
            continue
        if ctx.analyzed_replies >= max_per_poll:
            stopped = "per_poll_cap"
            break
        if _as_int(_daily(state).get("replies")) >= max_per_day:
            stopped = "daily_cap"
            break
        stats["checked"] += 1
        outcome = await handle_mention(ctx, m)
        if outcome in (OUT_REPLIED, OUT_FIXED_REPLY):
            stats["replied"] += 1
        elif outcome == OUT_ERROR:
            stats["errors"] += 1
        else:
            stats["skipped"] += 1

    if stopped:
        logger.info(
            "threads poll stopped early: %s (analyzed_replies=%s/%s, daily=%s/%s)",
            stopped, ctx.analyzed_replies, max_per_poll, _daily(state).get("replies"), max_per_day,
        )
    state["last_since"] = _next_since(mentions, ctx, prev_since, now)
    return await _finish_poll(state, stats, data_dir, mode, ctx.last_error, stopped)


async def run_threads_poll(client: Any = None, data_dir: Optional[PathLike] = None) -> dict:
    """輪詢一次 mentions 並逐則處理。由排程（THREADS_MODE=live|sim）或 POST /api/threads/poll 觸發。

    回傳 {"started": False, "reason": ...}、{"started": False, "skipped": "backoff", ...}
    或 {"started": True, checked, replied, skipped, errors, stopped}；另一輪進行中 → 丟 PollInProgress。
    """
    mode = settings.threads_mode_effective
    if mode not in ("live", "sim"):
        logger.info("threads poll skipped: mode=%s", mode)
        return {"started": False, "reason": "threads_disabled"}
    if client is None:
        client = get_threads_client()
    if client is None or not client.available:
        reason = getattr(client, "invalid_reason", None) or None
        if reason:
            # spec §7.3 第 3 點：token 過期 → last_error=token_invalid、輪詢暫停（不打 API 也要看得到）
            await asyncio.to_thread(_record_client_error, data_dir, reason)
        logger.warning("threads poll skipped: client unavailable mode=%s reason=%s", mode, reason)
        return {"started": False, "reason": reason or "client_unavailable"}

    state = await asyncio.to_thread(threads_state.load_state, data_dir)
    backoff_until = _to_epoch(state.get("backoff_until"))
    if backoff_until is not None and time.time() < backoff_until:
        logger.info("threads poll skipped: backoff until %s", _esc(state.get("backoff_until")))
        return {"started": False, "skipped": "backoff", "backoff_until": state.get("backoff_until")}

    # 檢查與取得之間沒有 await：同一 event loop 內不會有第二輪插進來
    if _POLL_LOCK.locked():
        logger.warning("poll_in_progress: another poll is running in this process")
        raise PollInProgress("poll_in_progress")
    async with _POLL_LOCK:
        path = lock_path(data_dir)
        try:
            # 刻意同步（本機小檔 O_EXCL 建立＋寫入）：若丟 to_thread 而本協程在等待時被取消，
            # 執行緒仍會建好鎖檔卻沒人釋放，會擋住之後 15 分鐘的輪詢
            token = _acquire_file_lock(path)
        except PollInProgress:
            logger.warning("poll_in_progress: lock file held by another poller: %s", _esc(str(path)))
            raise
        try:
            return await _poll_once(client, mode, data_dir)
        finally:
            await asyncio.to_thread(_release_file_lock, path, token)
