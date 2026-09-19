"""
Threads 查核機器人 — 輪詢 mentions → 三層快取＋AI 分析 → 自動回覆（spec §7.4、§7.5）。

單則 mention 處理 handle_mention()（spec §7.5）：
  1. resolve_target() 決定要查的對象與種類：
     - replied_to.id 是機器人自己發過的回覆（threads_replies.jsonl 的 reply_id）→ self（零 API 成本）
     - 讀原貼文（get_post）：作者是機器人 → self；去 @ 後 ≥8 字 → text；
       IMAGE／VIDEO／CAROUSEL_ALBUM 且文字 <8 字 → media_only；其餘文字太短 → too_short；
       HTTP 401／403／404 → unreadable；其他未列入的 4xx（400 等）→ failed；
       429／5xx／連線失敗 → transient（不標記，下輪重試；429 另設 backoff 並中止本輪）
     - 沒有 replied_to：用 mention 本文，≥8 字 → text，否則 too_short
     - text 去掉網址後 <8 字且含 http(s) → input_type="url"（走 FR-02）
     永不以 media_type == "TEXT" 判斷；絕不把「@bot 幫我查」這種請求句送進 AI。
  2. self → 只標記；media_only／unreadable／too_short → 回固定文案、標記、寫 jsonl；
     failed → 寫 state.failed（終態）、log 全文，不回覆、不重試、不進 replied_ids（spec §7.10 保守路徑）。
  3. text → 建任務 → process_analysis_task_async → AI 不可用（fallback）→ 不回覆、不標記（下輪補回）
     → format_verdict_reply → 兩段式發佈 → 成功才標記。

兩段式發佈＋狀態檢查（spec §7.6；T-12）：create_reply_container → 先原子寫
state.pending_publish[mention_id] → wait_container（每 5 秒、最多 60 秒）→ FINISHED 才 publish_container。
  - ERROR／EXPIRED：不 publish、刪 pending、failed.count += 1；第 1 次下輪重試（重建 container），
    第 2 次仍失敗 → 放棄（failed.final，不再重跑 AI）。TIMEOUT（60 秒仍 IN_PROGRESS）：同樣計一次失敗，
    但保留 pending，下輪先查同一 container。
  - publish 暫時失敗（5xx／逾時）或行程在 publish 前被砍：pending 保留，下輪開頭 _resume_pending()
    對「同一 container」補發——不重跑 AI、不重建 container；狀態已是 PUBLISHED（上輪其實發成功）→ 只補標記。

錯誤分流（spec §7.10；T-13；以 HTTP 狀態碼為主，error.code 只記 log）：
  - 429（任何端點）→ backoff_until = now + min(60, poll_interval × 2^n) 分鐘、backoff_n += 1、
    本輪中止、該 mention 不標記；成功一輪後 backoff_n 歸零、backoff_until 清空
  - 401（mentions 與發佈端點）→ last_error=token_invalid、backoff 60 分鐘、本輪中止
  - 其他未列入的 4xx → 該 mention 標 failed、不回覆、不重試；
    body 含 THREADS_API__LINK_LIMIT_EXCEEDED → 去掉「查核來源」行重送一次
  - 5xx／逾時 → 該筆不標記、下輪重試；連續 3 輪 → backoff 15 分鐘

防重複回覆：publish 成功後「先」原子寫 state（replied_ids，同時清 pending_publish），再寫 jsonl／任務欄位；
中途 crash 只可能漏記 jsonl，不會讓同一則 mention 在下輪再被回覆。

輪詢 run_threads_poll()（spec §7.4）：
  - mode off 或 client 不可用 → {"started": False}；token 過期（invalid_reason）同時寫 state.last_error
  - backoff_until 未到 → {"started": False, "skipped": "backoff", backoff_until, last_error}（不打 API、不寫 state）
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
from app.services.threads_service import (
    CONTAINER_ERROR,
    CONTAINER_EXPIRED,
    CONTAINER_FINISHED,
    CONTAINER_PUBLISHED,
    CONTAINER_TIMEOUT,
    ThreadsApiError,
    get_threads_client,
    is_link_limit_error,
)
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
KIND_FAILED = "failed"            # 讀原貼文遇未列入的 4xx（400 等）：標 failed、不回覆、不重試

OUT_REPLIED = "replied"           # 已回覆判定（走過 AI 管線）
OUT_FIXED_REPLY = "fixed_reply"   # 已回覆固定文案（不經 AI）
OUT_SELF = "self"                 # 自我貼文：標記、不回覆
OUT_AI_UNAVAILABLE = "ai_unavailable"
OUT_DEFERRED = "deferred"         # 本輪 AI 已不可用，其餘文字 mention 留待下輪
OUT_ERROR = "error"               # 未標記，下輪重試
OUT_FAILED = "failed"             # 已標 failed（終態）：未回覆、不再重試

# ── 錯誤分流（spec §7.10；以 HTTP 狀態碼為主）────────────────────────
ERR_RATE_LIMITED = "rate_limited"     # 429 → backoff、本輪中止
ERR_TOKEN_INVALID = "token_invalid"   # 401（mentions／發佈端點）→ backoff 60 分、本輪中止
ERR_CLIENT = "client_error"           # 其他未列入的 4xx → 該 mention 標 failed（保守路徑）
ERR_TRANSIENT = "transient"           # 5xx／逾時／連線失敗／拿不到狀態碼 → 不標記，下輪重試

# 讀原貼文時視為「讀不到」的狀態碼（§7.5：非 Tester、私人帳號、權限）→ reply_cannot_read
UNREADABLE_STATUSES = (401, 403, 404)

TOKEN_INVALID_BACKOFF_MINUTES = 60    # §7.10「token 失效」
TRANSIENT_BACKOFF_MINUTES = 15        # §7.10「5xx／逾時」：連續 3 輪
TRANSIENT_ROUNDS_LIMIT = 3
PUBLISH_MAX_FAILURES = 2              # §7.6：container 失敗第 1 次下輪重試一次，第 2 次放棄

LAST_ERROR_MENTION_FAILED = "mention_failed"
LAST_ERROR_TRANSIENT = "transient_error"

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


def classify_status(status: Any) -> str:
    """HTTP 狀態碼 → ERR_*（spec §7.10）。拿不到狀態碼（連線失敗、逾時、非 API 例外）視為暫時性。"""
    if isinstance(status, bool) or not isinstance(status, int):
        return ERR_TRANSIENT
    if status == 429:
        return ERR_RATE_LIMITED
    if status == 401:
        return ERR_TOKEN_INVALID
    if 400 <= status < 500:
        return ERR_CLIENT
    return ERR_TRANSIENT


def classify_api_error(exc: BaseException) -> str:
    return classify_status(getattr(exc, "status", None))


async def resolve_target(
    client: Any,
    m: Dict[str, Any],
    *,
    own_ids: Optional[Set[str]] = None,
    data_dir: Optional[PathLike] = None,
    bot_handle: Optional[str] = None,
) -> Tuple[str, Optional[str], str, Dict[str, Any]]:
    """回傳 (kind, text, input_type, target_post)；text 只有 kind == "text" 時非 None
    （input_type == "url" 時 text 為網址本身）。target_post 描述「被查核的貼文」；
    讀原貼文失敗（kind 為 transient／failed）時另帶 error_status（HTTP 狀態碼或 None），
    讓 handle_mention 依 spec §7.10 分流（429 → backoff）。"""
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
            if status in UNREADABLE_STATUSES:
                return KIND_UNREADABLE, None, "text", {"id": parent_id}
            if classify_status(status) == ERR_CLIENT:
                # 未列入的 4xx（400 等）：保守路徑，標 failed、不回覆、不重試（§7.10；不是「讀不到」）
                return KIND_FAILED, None, "text", {"id": parent_id, "error_status": status}
            return KIND_TRANSIENT, None, "text", {"id": parent_id, "error_status": status}
        except Exception as e:  # 連線／解析失敗等非 API 錯誤：當作暫時性，下輪重試
            logger.warning(
                "get_post error mention=%s post=%s: %s", _esc(m.get("id")), _esc(parent_id), _esc(e),
            )
            return KIND_TRANSIENT, None, "text", {"id": parent_id, "error_status": None}

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
        # §7.10 分流的本輪旗標；_finish_poll 依此設定／歸零 backoff
        self.rate_limited = False          # 本輪遇過 429
        self.token_invalid = False         # 本輪 mentions／發佈端點遇過 401
        self.transient = False             # 本輪遇過 5xx／逾時／連線失敗
        self.abort: Optional[str] = None   # 非 None → 本輪中止（rate_limited／token_invalid）
        self.counted: Set[str] = set()     # 本輪已計入 stats.checked 的 mention（補發＋正常流程不重複計）
        # 兩段式發佈（spec §7.6）：客戶端提供三個原子操作才走；只有 reply_to 的舊式客戶端退回單次呼叫
        self.two_step = all(
            callable(getattr(client, name, None))
            for name in ("create_reply_container", "wait_container", "publish_container")
        )
        self._reply_takes_result_id = _accepts_kwarg(getattr(client, "reply_to", None), "result_id")
        self._create_takes_result_id = _accepts_kwarg(
            getattr(client, "create_reply_container", None), "result_id",
        )

    # ── state 區塊 ───────────────────────────────────────────────
    def _bucket(self, key: str) -> dict:
        bucket = self.state.get(key)
        if not isinstance(bucket, dict):
            bucket = self.state[key] = {}
        return bucket

    async def _save(self) -> None:
        await asyncio.to_thread(threads_state.save_state, self.state, self.data_dir)

    def failed_entry(self, mention_id: str) -> dict:
        """state.failed[mention_id] 的正規化副本；相容舊格式的整數（失敗次數）。"""
        raw = self._bucket("failed").get(mention_id)
        if isinstance(raw, dict):
            entry = dict(raw)
            entry["count"] = _as_int(entry.get("count"))
            entry["final"] = bool(entry.get("final"))
            return entry
        if isinstance(raw, (int, float)) and not isinstance(raw, bool):
            return {"count": int(raw), "final": int(raw) >= PUBLISH_MAX_FAILURES}
        return {"count": 0, "final": False}

    def is_failed_final(self, mention_id: str) -> bool:
        return mention_id in self._bucket("failed") and self.failed_entry(mention_id)["final"]

    def is_done(self, mention_id: str) -> bool:
        """已回覆／已標記，或已標 failed（終態）：之後的輪次都不再處理，也不擋 since 游標。"""
        return mention_id in self.replied or self.is_failed_final(mention_id)

    # ── §7.10 分流 ───────────────────────────────────────────────
    def note_error(self, kind: str) -> None:
        """記下本輪遇到的 API 錯誤種類；429／401 會讓本輪中止（其餘 mention 留待 backoff 之後）。"""
        if kind == ERR_RATE_LIMITED:
            self.rate_limited = True
            self.abort = self.abort or ERR_RATE_LIMITED
            self.last_error = ERR_RATE_LIMITED
        elif kind == ERR_TOKEN_INVALID:
            self.token_invalid = True
            self.abort = self.abort or ERR_TOKEN_INVALID
            self.last_error = ERR_TOKEN_INVALID
        elif kind == ERR_TRANSIENT:
            self.transient = True
            self.last_error = self.last_error or LAST_ERROR_TRANSIENT

    async def mark(self, mention_id: str, *, analyzed: bool = False) -> None:
        """標記已處理並立即原子寫 state；analyzed=True 時計入每日回覆數。
        同一次寫入一併清掉該 mention 的 pending_publish 與先前的失敗計數。"""
        if mention_id not in self.replied:
            self.replied.add(mention_id)
            self.state.setdefault("replied_ids", []).append(mention_id)
        self._bucket("pending_publish").pop(mention_id, None)
        self._bucket("failed").pop(mention_id, None)
        if analyzed:
            daily = _daily(self.state)
            daily["replies"] = int(daily.get("replies") or 0) + 1
            self.analyzed_replies += 1
        await self._save()

    async def set_pending(self, mention_id: str, entry: dict) -> None:
        """container 建好、publish 之前先原子寫 state（spec §7.6）：中途失敗或被砍，下輪對同一 container 補發。"""
        self._bucket("pending_publish")[mention_id] = entry
        await self._save()

    async def drop_pending(self, mention_id: str) -> None:
        if self._bucket("pending_publish").pop(mention_id, None) is not None:
            await self._save()

    async def mark_failed(self, mention_id: str, *, stage: str, status: Any = None,
                          reason: Optional[str] = None) -> str:
        """保守路徑（spec §7.10「未知 4xx」）：標 failed（終態）、不回覆、不重試；不進 replied_ids。"""
        entry = self.failed_entry(mention_id)
        entry.update({
            "count": entry["count"] + 1,
            "final": True,
            "reason": reason or (f"http_{status}" if status is not None else "client_error"),
            "stage": stage,
            "status": status,
            "at": datetime.now(timezone.utc).isoformat(),
        })
        self._bucket("failed")[mention_id] = entry
        self._bucket("pending_publish").pop(mention_id, None)
        if not self.abort:
            self.last_error = self.last_error or LAST_ERROR_MENTION_FAILED
        await self._save()
        logger.error(
            "mention marked failed (no reply, no retry) mention=%s stage=%s status=%s reason=%s",
            _esc(mention_id), stage, status, _esc(entry["reason"]),
        )
        return OUT_FAILED

    async def publish_failed(self, mention_id: str, reason: str, *, keep_pending: bool = False) -> str:
        """container ERROR／EXPIRED／TIMEOUT（spec §7.6）：failed.count += 1、記 last_error。
        第 1 次 → 未標記、下輪重試一次（OUT_ERROR）；第 2 次 → 放棄（failed.final，OUT_FAILED），
        不再重跑 AI，也不進 replied_ids（沒有回覆過）。"""
        entry = self.failed_entry(mention_id)
        count = entry["count"] + 1
        final = count >= PUBLISH_MAX_FAILURES
        entry.update({
            "count": count, "final": final, "reason": reason, "stage": "publish",
            "status": None, "at": datetime.now(timezone.utc).isoformat(),
        })
        self._bucket("failed")[mention_id] = entry
        if final or not keep_pending:
            self._bucket("pending_publish").pop(mention_id, None)
        if not self.abort:
            # 與其他單則錯誤一致：保留本輪第一個錯誤（429／401 會中止本輪，永遠優先）
            self.last_error = self.last_error or reason
        await self._save()
        if final:
            logger.error(
                "publish gave up after %s failures mention=%s reason=%s (not replied, not retried)",
                count, _esc(mention_id), reason,
            )
            return OUT_FAILED
        logger.warning(
            "publish failed mention=%s reason=%s (failure %s/%s): retry once next poll",
            _esc(mention_id), reason, count, PUBLISH_MAX_FAILURES,
        )
        return OUT_ERROR

    async def api_error_outcome(self, exc: BaseException, mention_id: str, stage: str) -> str:
        """發佈相關 API 錯誤的共用分流：未列入的 4xx → 標 failed；429／401／暫時性 → 記旗標、不標記。"""
        kind = classify_api_error(exc)
        if kind == ERR_CLIENT:
            return await self.mark_failed(mention_id, stage=stage, status=getattr(exc, "status", None))
        self.note_error(kind)
        return OUT_ERROR


def _accepts_kwarg(func: Any, name: str) -> bool:
    if func is None:
        return False
    try:
        return name in inspect.signature(func).parameters
    except (TypeError, ValueError):
        return False


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


# ── 發佈（spec §7.6 兩段式＋狀態檢查；§7.10 分流）────────────────────────
class _LinkLimitExceeded(Exception):
    """API 回 THREADS_API__LINK_LIMIT_EXCEEDED 且還有「去掉查核來源行」的版本可重送（只重送一次）。"""


def _reply_entry(
    ctx: PollContext, text: str, target: Dict[str, Any], *,
    result: Optional[Dict[str, Any]] = None, result_id: Optional[str] = None,
    frame_type: str = "yellow", analyzed: bool = False,
) -> Dict[str, Any]:
    """一則待發佈的回覆：也是 state.pending_publish[mention_id] 的內容——下輪補發時不重跑 AI，
    所以回覆全文與 threads_replies.jsonl 要用的欄位都放在這裡。"""
    target_text = target.get("text")
    return {
        "container_id": None,
        "created_at": None,
        "mode": ctx.mode,
        "reply_text": text,
        "result_id": result_id,
        "analyzed": bool(analyzed),          # True = 經 AI 的判定回覆（計入每輪／每日上限）
        "frame_type": frame_type,
        "risk_type": (result or {}).get("risk_type"),
        "username": target.get("username"),
        "permalink": target.get("permalink"),
        "source_text_preview": _preview(target_text) if target_text is not None else None,
    }


async def _record_reply(ctx: PollContext, mention_id: str, entry: Dict[str, Any], reply_id: Optional[str]) -> None:
    """寫 threads_replies.jsonl（失敗只記 log：state 已先寫，不會造成重複回覆）。"""
    if reply_id:
        ctx.own_ids.add(reply_id)
    row = {
        "mention_id": mention_id,
        "mode": ctx.mode,
        "result_id": entry.get("result_id"),
        "frame_type": entry.get("frame_type") or "yellow",
        "risk_type": entry.get("risk_type"),
        "username": entry.get("username"),
        "source_text_preview": entry.get("source_text_preview"),
        "reply_text": entry.get("reply_text"),
        "reply_id": reply_id,
        "permalink": entry.get("permalink"),
    }
    try:
        await asyncio.to_thread(threads_state.append_reply_record, row, ctx.data_dir)
    except Exception as e:
        logger.error("append_reply_record failed mention=%s: %s", _esc(mention_id), _esc(e))


async def _complete_reply(ctx: PollContext, mention_id: str, entry: Dict[str, Any], reply_id: Optional[str]) -> str:
    """發佈成功後的記帳：「先」原子寫 state（標記＋清 pending_publish），再寫 jsonl／任務欄位。"""
    analyzed = bool(entry.get("analyzed"))
    await ctx.mark(mention_id, analyzed=analyzed)
    logger.info(
        "replied mention=%s reply_id=%s text=%s", _esc(mention_id), _esc(reply_id), _esc(entry.get("reply_text")),
    )
    await _record_reply(ctx, mention_id, entry, reply_id)
    result_id = entry.get("result_id")
    if result_id and reply_id:
        try:
            await asyncio.to_thread(ctx.task_store.update_task, result_id, threads_reply_id=reply_id)
        except Exception as e:
            logger.error("update_task threads_reply_id failed task=%s: %s", result_id, _esc(e))
    return OUT_REPLIED if analyzed else OUT_FIXED_REPLY


async def _publish_pending(
    ctx: PollContext, mention_id: str, entry: Dict[str, Any], *, allow_link_retry: bool = False,
) -> str:
    """第二、三步：wait_container → status=FINISHED 才 publish_container → 記帳。
    entry 已寫在 state.pending_publish（剛建好的 container，或上一輪留下來待補發的）。"""
    container_id = str(entry.get("container_id"))
    try:
        status = await asyncio.to_thread(ctx.client.wait_container, container_id)
    except ThreadsApiError as e:
        logger.warning(
            "container status failed mention=%s container=%s status=%s body=%s",
            _esc(mention_id), _esc(container_id), e.status, _esc(e.body),
        )
        kind = classify_api_error(e)
        if kind == ERR_CLIENT:
            # container 查不到（已被清掉或 id 無效）：視同 EXPIRED，計一次發佈失敗
            return await ctx.publish_failed(mention_id, "container_unreadable")
        ctx.note_error(kind)
        return OUT_ERROR      # pending 保留：backoff 之後／下輪對同一 container 再試
    except Exception as e:
        logger.warning("container status error mention=%s container=%s: %s",
                       _esc(mention_id), _esc(container_id), _esc(e))
        ctx.note_error(ERR_TRANSIENT)
        return OUT_ERROR

    status = str(status or "").strip().upper()
    reply_id: Optional[str] = None
    if status == CONTAINER_PUBLISHED:
        # 上一輪 publish 其實已成功（回應遺失，或寫 state 前行程被砍）：只補標記，絕不再發一次
        logger.warning(
            "container already published mention=%s container=%s: marking as replied without publishing again",
            _esc(mention_id), _esc(container_id),
        )
    elif status == CONTAINER_FINISHED:
        try:
            published = await asyncio.to_thread(ctx.client.publish_container, container_id)
        except ThreadsApiError as e:
            logger.warning(
                "publish failed mention=%s container=%s status=%s body=%s",
                _esc(mention_id), _esc(container_id), e.status, _esc(e.body),
            )
            if allow_link_retry and is_link_limit_error(e):
                await ctx.drop_pending(mention_id)
                raise _LinkLimitExceeded() from None
            kind = classify_api_error(e)
            if kind == ERR_CLIENT:
                return await ctx.mark_failed(mention_id, stage="publish", status=e.status)
            ctx.note_error(kind)
            return OUT_ERROR  # pending 保留：下輪對同一 container 補發（不重建、不重跑 AI）
        except Exception as e:
            logger.warning("publish error mention=%s container=%s: %s",
                           _esc(mention_id), _esc(container_id), _esc(e))
            ctx.note_error(ERR_TRANSIENT)
            return OUT_ERROR
        if not published:
            # 2xx 但沒有 id：不確定是否已發佈 → 保留 pending，下輪查狀態（PUBLISHED 就只補標記）
            logger.warning("publish returned no id mention=%s container=%s", _esc(mention_id), _esc(container_id))
            ctx.note_error(ERR_TRANSIENT)
            return OUT_ERROR
        reply_id = str(published)
    else:
        reason = {
            CONTAINER_ERROR: "container_error",
            CONTAINER_EXPIRED: "container_expired",
        }.get(status, "container_timeout")
        # TIMEOUT：container 可能稍後才 FINISHED → 保留 pending，下輪先查同一個；ERROR／EXPIRED 已無法發佈
        return await ctx.publish_failed(mention_id, reason, keep_pending=(status == CONTAINER_TIMEOUT))
    return await _complete_reply(ctx, mention_id, entry, reply_id)


async def _create_and_publish(
    ctx: PollContext, mention_id: str, entry: Dict[str, Any], text: str, *, allow_link_retry: bool,
) -> str:
    """第一步：建 container → publish 之前先原子寫 state.pending_publish → 交給 _publish_pending。"""
    kwargs = {"result_id": entry.get("result_id")} if ctx._create_takes_result_id else {}
    try:
        container_id = await asyncio.to_thread(ctx.client.create_reply_container, mention_id, text, **kwargs)
    except ThreadsApiError as e:
        logger.warning(
            "create container failed mention=%s status=%s body=%s", _esc(mention_id), e.status, _esc(e.body),
        )
        if allow_link_retry and is_link_limit_error(e):
            raise _LinkLimitExceeded() from None
        return await ctx.api_error_outcome(e, mention_id, "create_container")
    except Exception as e:
        logger.warning("create container error mention=%s: %s", _esc(mention_id), _esc(e))
        ctx.note_error(ERR_TRANSIENT)
        return OUT_ERROR
    if not container_id:
        logger.warning("create container returned no id mention=%s", _esc(mention_id))
        ctx.note_error(ERR_TRANSIENT)
        return OUT_ERROR
    pending = dict(
        entry, container_id=str(container_id), reply_text=text,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    await ctx.set_pending(mention_id, pending)
    return await _publish_pending(ctx, mention_id, pending, allow_link_retry=allow_link_retry)


async def _legacy_reply(
    ctx: PollContext, mention_id: str, entry: Dict[str, Any], text: str, *, allow_link_retry: bool,
) -> str:
    """只有 reply_to() 的舊式客戶端：單次呼叫（無法在 publish 前寫 pending）；錯誤分流相同。"""
    kwargs = {"result_id": entry.get("result_id")} if ctx._reply_takes_result_id else {}
    try:
        reply_id = await asyncio.to_thread(ctx.client.reply_to, mention_id, text, **kwargs)
    except ThreadsApiError as e:
        logger.warning(
            "reply_to failed mention=%s status=%s body=%s", _esc(mention_id), e.status, _esc(e.body),
        )
        if allow_link_retry and is_link_limit_error(e):
            raise _LinkLimitExceeded() from None
        return await ctx.api_error_outcome(e, mention_id, "reply_to")
    except Exception as e:
        logger.warning("reply_to error mention=%s: %s", _esc(mention_id), _esc(e))
        ctx.note_error(ERR_TRANSIENT)
        return OUT_ERROR
    if not reply_id:
        logger.warning("reply_to returned no id mention=%s", _esc(mention_id))
        return OUT_ERROR
    return await _complete_reply(ctx, mention_id, dict(entry, reply_text=text), str(reply_id))


async def _publish_reply(
    ctx: PollContext, mention_id: str, entry: Dict[str, Any], alt_text: Optional[str] = None,
) -> str:
    """送出一則回覆，回傳 OUT_*。alt_text：連結超限（§7.10）時改送的版本（不含「查核來源」行），只重送一次。"""
    text = str(entry.get("reply_text") or "")
    if alt_text == text:
        alt_text = None
    send = _create_and_publish if ctx.two_step else _legacy_reply
    try:
        return await send(ctx, mention_id, entry, text, allow_link_retry=bool(alt_text))
    except _LinkLimitExceeded:
        logger.warning(
            "link limit exceeded mention=%s: resending once without the source line", _esc(mention_id),
        )
    return await send(ctx, mention_id, entry, str(alt_text), allow_link_retry=False)


async def handle_mention(ctx: PollContext, m: Dict[str, Any]) -> str:
    """處理單則 mention（spec §7.5），回傳 OUT_* 結果。發佈之前的錯誤一律吞下：暫時性／429／401 →
    OUT_ERROR（未標記、下輪重試）；未列入的 4xx → OUT_FAILED（標 failed、不回覆、不重試）。
    發佈成功後寫 state 失敗則往外拋，讓整輪中止以免繼續回覆卻記不住。"""
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
        # 429 → backoff＋本輪中止；5xx／逾時 → 計入連續暫時性失敗（§7.10）。都不標記，下輪重試
        ctx.note_error(classify_status(target.get("error_status")))
        outcome = OUT_ERROR
    elif kind == KIND_FAILED:
        outcome = await ctx.mark_failed(mention_id, stage="get_post", status=target.get("error_status"))
    elif kind in _FIXED_REPLIES:
        entry = _reply_entry(ctx, _FIXED_REPLIES[kind](), target)
        outcome = await _publish_reply(ctx, mention_id, entry)
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
        result_url = _result_url(task_id)
        reply_text = format_verdict_reply(result, result_url)
        # §7.10「連結超限」時改送的版本：去掉「查核來源」行（結果頁連結與免責行永不截）
        alt_text = format_verdict_reply(result, result_url, without_source_line=True)
        frame_type = result.get("frame_type") or frame_of(result)[0]
    except Exception as e:
        logger.error("format_verdict_reply failed mention=%s: %s", _esc(mention_id), _esc(e))
        return OUT_ERROR, task_id, cache_layer

    entry = _reply_entry(
        ctx, reply_text, target, result=result, result_id=task_id, frame_type=frame_type, analyzed=True,
    )
    # 成功 → 先標記（計入每日回覆數）再寫 jsonl／任務的 threads_reply_id（_complete_reply）
    outcome = await _publish_reply(ctx, mention_id, entry, alt_text=alt_text)
    return outcome, task_id, cache_layer


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
    """mentions 端點失敗的 last_error（spec §7.10）；backoff 由 _update_backoff 依 ctx 旗標設定。"""
    if status == 401:
        return ERR_TOKEN_INVALID
    if status == 429:
        return ERR_RATE_LIMITED
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
        # 已標 failed（終態）的也算處理完：不回覆、不重試，不能讓它永遠擋住游標
        if not mention_id or ctx.is_done(mention_id) or _is_bot_author(ctx, m):
            continue
        if ts is None:
            return prev_since
        pending_ts.append(ts)
    if pending_ts:
        return int(min(pending_ts)) - 1
    if all_ts:
        return max(prev_since, int(max(all_ts)))
    return max(prev_since, now)


def _backoff_skip(state: dict) -> Optional[dict]:
    """backoff_until 未到 → 本輪略過的回傳值（不打 API、不寫 state）；否則 None。"""
    if threads_state.backoff_remaining_seconds(state) <= 0:
        return None
    logger.info(
        "threads poll skipped: backoff until %s (last_error=%s)",
        _esc(state.get("backoff_until")), state.get("last_error"),
    )
    return {
        "started": False, "skipped": "backoff",
        "backoff_until": state.get("backoff_until"), "last_error": state.get("last_error"),
    }


def _update_backoff(state: dict, ctx: PollContext, *, mentions_ok: bool) -> None:
    """一輪結束時依本輪旗標設定／歸零 backoff（spec §7.10）。只改 state，由 _finish_poll 一併原子寫檔。

    - 429：backoff_until = now + min(60, poll_interval × 2^n) 分鐘，n = backoff_n（連續次數），之後 n += 1
    - 401：backoff_until = now + 60 分鐘
    - 5xx／逾時：transient_n += 1；連續滿 3 輪 → backoff_until = now + 15 分鐘
    - 成功的一輪（mentions 讀取成功、沒有 429／401）→ backoff_n 歸零；沒有暫時性失敗 → transient_n 歸零
    - 本輪沒有設新的 backoff → 清掉已到期的 backoff_until（/api/threads/status 不再顯示過期時間）
    多個條件同時成立時 set_backoff 取較晚者。"""
    now = datetime.now(timezone.utc)
    backed_off = False
    if ctx.rate_limited:
        n = max(0, _as_int(state.get("backoff_n")))
        minutes = threads_state.rate_limit_backoff_minutes(settings.THREADS_POLL_MINUTES, n)
        threads_state.set_backoff(state, minutes, now)
        state["backoff_n"] = n + 1
        backed_off = True
        logger.warning(
            "threads rate limited (HTTP 429): backoff %.0f min until %s (consecutive=%s)",
            minutes, state["backoff_until"], n + 1,
        )
    elif mentions_ok and not ctx.token_invalid:
        state["backoff_n"] = 0
    if ctx.token_invalid:
        threads_state.set_backoff(state, TOKEN_INVALID_BACKOFF_MINUTES, now)
        backed_off = True
        logger.error(
            "threads token invalid (HTTP 401): backoff %s min until %s",
            TOKEN_INVALID_BACKOFF_MINUTES, state["backoff_until"],
        )
    if ctx.transient:
        rounds = max(0, _as_int(state.get("transient_n"))) + 1
        state["transient_n"] = rounds
        if rounds >= TRANSIENT_ROUNDS_LIMIT:
            threads_state.set_backoff(state, TRANSIENT_BACKOFF_MINUTES, now)
            backed_off = True
            logger.warning(
                "threads transient errors for %s consecutive polls: backoff %s min until %s",
                rounds, TRANSIENT_BACKOFF_MINUTES, state["backoff_until"],
            )
    elif not ctx.abort:
        state["transient_n"] = 0
    if not backed_off and threads_state.backoff_remaining_seconds(state, now) <= 0:
        state["backoff_until"] = None


async def _finish_poll(ctx: PollContext, stats: dict, *, mentions_ok: bool,
                       stopped: Optional[str] = None) -> dict:
    state = ctx.state
    _update_backoff(state, ctx, mentions_ok=mentions_ok)
    state["last_poll_at"] = datetime.now(timezone.utc).isoformat()
    state["last_stats"] = dict(stats)
    state["last_error"] = ctx.last_error
    await asyncio.to_thread(threads_state.save_state, state, ctx.data_dir)
    logger.info(
        "threads poll done mode=%s since_next=%s stopped=%s stats=%s last_error=%s backoff_until=%s",
        ctx.mode, state.get("last_since"), stopped, json.dumps(stats), ctx.last_error,
        _esc(state.get("backoff_until")),
    )
    return {"started": True, **stats, "stopped": stopped}


def _count_outcome(stats: dict, outcome: str) -> None:
    if outcome in (OUT_REPLIED, OUT_FIXED_REPLY):
        stats["replied"] += 1
    elif outcome in (OUT_ERROR, OUT_FAILED):
        stats["errors"] += 1
    else:
        stats["skipped"] += 1


def _cap_reached(ctx: PollContext, max_per_poll: int, max_per_day: int) -> Optional[str]:
    if ctx.analyzed_replies >= max_per_poll:
        return "per_poll_cap"
    if _as_int(_daily(ctx.state).get("replies")) >= max_per_day:
        return "daily_cap"
    return None


async def _resume_pending(ctx: PollContext, stats: dict, max_per_poll: int, max_per_day: int) -> Optional[str]:
    """每輪開頭先補發上一輪留下的 container（spec §7.6）：對「同一個」container 查狀態後 publish，
    不重跑 AI、不重建 container。ERROR／EXPIRED → 刪鍵，該 mention 回到本輪的正常流程。
    因判定回覆上限而停下時回傳 "per_poll_cap"／"daily_cap"，否則 None。"""
    pending = ctx.state.get("pending_publish")
    if not isinstance(pending, dict) or not pending:
        return None
    for mention_id, entry in list(pending.items()):
        mention_id = str(mention_id)
        if not isinstance(entry, dict) or not entry.get("container_id"):
            logger.warning("dropping malformed pending_publish entry mention=%s", _esc(mention_id))
            await ctx.drop_pending(mention_id)
            continue
        if entry.get("mode") not in (None, ctx.mode):
            continue      # 另一個模式（live／sim）留下的 container：這個客戶端查不到，切回該模式再補發
        if ctx.is_done(mention_id):
            await ctx.drop_pending(mention_id)
            continue
        if entry.get("analyzed"):
            cap = _cap_reached(ctx, max_per_poll, max_per_day)
            if cap:
                return cap    # 判定回覆已達上限：留著，之後的輪次再補發
        started = time.perf_counter()
        ctx.counted.add(mention_id)
        stats["checked"] += 1
        outcome = await _publish_pending(ctx, mention_id, entry)
        _count_outcome(stats, outcome)
        logger.info("mention %s", json.dumps({
            "mention_id": mention_id,
            "kind": "pending_publish",
            "outcome": outcome,
            "result_id": entry.get("result_id"),
            "cache_layer": None,
            "elapsed_ms": int((time.perf_counter() - started) * 1000),
        }, ensure_ascii=True))
        if ctx.abort:
            break
    return None


async def _poll_once(client: Any, mode: str, data_dir: Optional[PathLike]) -> dict:
    stats = {"checked": 0, "replied": 0, "skipped": 0, "errors": 0}
    # 取得鎖之後才讀：拿到的是上一輪寫完的權威 state
    state = await asyncio.to_thread(threads_state.load_state, data_dir)
    skip = _backoff_skip(state)
    if skip is not None:
        return skip       # 在等鎖的空檔另一個行程剛設了 backoff
    prev_since = _as_int(state.get("last_since"))
    since = max(prev_since - SINCE_OVERLAP_SECONDS, SINCE_FLOOR)
    now = int(time.time())
    own_ids = await asyncio.to_thread(threads_state.own_reply_ids, data_dir)
    ctx = PollContext(client, state, mode, data_dir=data_dir, own_ids=own_ids)
    max_per_poll = _as_int(settings.THREADS_MAX_REPLIES_PER_POLL)
    max_per_day = _as_int(settings.THREADS_MAX_REPLIES_PER_DAY)

    resume_cap = await _resume_pending(ctx, stats, max_per_poll, max_per_day)
    if ctx.abort:
        return await _finish_poll(ctx, stats, mentions_ok=False, stopped=ctx.abort)

    try:
        raw = await asyncio.to_thread(client.get_mentions, since)
    except ThreadsApiError as e:
        logger.error("get_mentions failed since=%s status=%s body=%s", since, e.status, _esc(e.body))
        stats["errors"] += 1
        ctx.note_error(classify_api_error(e))      # 429／401 → backoff；5xx／逾時 → 計入連續暫時性失敗
        ctx.last_error = _mentions_error(e.status)
        return await _finish_poll(ctx, stats, mentions_ok=False, stopped=ctx.abort)
    except Exception as e:
        logger.error("get_mentions error since=%s: %s", since, _esc(e))
        stats["errors"] += 1
        ctx.note_error(ERR_TRANSIENT)
        ctx.last_error = "mentions_failed"
        return await _finish_poll(ctx, stats, mentions_ok=False)

    mentions = [m for m in raw or [] if isinstance(m, dict)]
    mentions.sort(key=_sort_key)
    # mentions 讀取成功：清掉上一輪的錯誤，輪中逐則寫 state 時 status 不再顯示舊錯誤
    # （本輪的結果以 ctx.last_error 為準，由 _finish_poll 寫入）
    state["last_error"] = ctx.last_error
    stopped: Optional[str] = None
    seen: Set[str] = set()
    pending = ctx._bucket("pending_publish")

    for m in mentions:
        mention_id = str(m.get("id") or "")
        if not mention_id or ctx.is_done(mention_id) or mention_id in seen:
            continue   # 已處理過（已回覆或已標 failed），或同一輪清單內重複出現（分頁重疊）
        seen.add(mention_id)
        if _is_bot_author(ctx, m):
            stats["checked"] += 1
            stats["skipped"] += 1
            continue
        if mention_id in pending:
            continue   # container 仍待發佈（本輪開頭已試過、或另一模式留下的）：下輪補發，不重建、不重跑 AI
        stopped = _cap_reached(ctx, max_per_poll, max_per_day)
        if stopped:
            break
        if mention_id not in ctx.counted:
            ctx.counted.add(mention_id)
            stats["checked"] += 1
        outcome = await handle_mention(ctx, m)
        _count_outcome(stats, outcome)
        if ctx.abort:
            stopped = ctx.abort    # 429／401：其餘 mention 留待 backoff 之後
            break

    stopped = stopped or resume_cap    # 補發階段就因上限停下、之後也沒有別的 mention 可處理
    if stopped:
        logger.info(
            "threads poll stopped early: %s (analyzed_replies=%s/%s, daily=%s/%s)",
            stopped, ctx.analyzed_replies, max_per_poll, _daily(state).get("replies"), max_per_day,
        )
    state["last_since"] = _next_since(mentions, ctx, prev_since, now)
    return await _finish_poll(ctx, stats, mentions_ok=True, stopped=stopped)


async def run_threads_poll(client: Any = None, data_dir: Optional[PathLike] = None) -> dict:
    """輪詢一次 mentions 並逐則處理。由排程（THREADS_MODE=live|sim）或 POST /api/threads/poll 觸發。

    回傳 {"started": False, "reason": ...}、{"started": False, "skipped": "backoff", backoff_until, last_error}
    或 {"started": True, checked, replied, skipped, errors, stopped}；另一輪進行中 → 丟 PollInProgress。
    stopped：None｜"per_poll_cap"｜"daily_cap"｜"rate_limited"（429）｜"token_invalid"（401）。
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
    skip = _backoff_skip(state)
    if skip is not None:
        return skip

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
