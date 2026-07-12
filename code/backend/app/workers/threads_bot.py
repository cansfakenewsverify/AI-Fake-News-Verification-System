"""
Threads 查核機器人 — 輪詢 mentions → 三層快取+AI 分析 → 自動回覆。

流程（模式 2）：
  1. 有人在 Threads 上「回覆一則可疑貼文並 @機器人」（或直接 @機器人 貼可疑文字）
  2. run_threads_poll() 抓 mentions：
     - mention 是「回覆」→ 抓被回覆的原貼文文字來查核
     - mention 是獨立貼文 → 查核 mention 本身的文字（去掉 @標記）
  3. 走與 /api/analyze/sync 完全相同的三層快取 + AI 管線
  4. 回覆紅黃綠判定 + 查核來源（<=500 字）

防呆：
  - 已回覆過的 mention id 存 data/threads_state.json，不重複回
  - 不回自己的貼文（避免自我循環）
  - AI 額度用盡的 fallback 結果「不回覆、不記錄」→ 額度恢復後下一輪自動補回
"""
import asyncio
import json
import re
from pathlib import Path
from typing import Optional

from app.config import settings
from app.services.threads_service import ThreadsService, format_verdict_reply
from app.services.task_store import TaskStore

STATE_PATH = Path("data") / "threads_state.json"
_STATE_MAX_IDS = 500      # 只保留最近 N 筆已回覆 id，避免檔案無限長大
_MIN_TEXT_LEN = 8         # 太短的內容無法判斷特徵，直接跳過
_MENTION_RE = re.compile(r"@\w[\w.]*")


def _load_state() -> dict:
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"replied_ids": []}


def _save_state(state: dict) -> None:
    state["replied_ids"] = state.get("replied_ids", [])[-_STATE_MAX_IDS:]
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(
        json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8"
    )


def _is_fallback(result: dict) -> bool:
    """AI 額度用盡/掛掉時的占位結果，不能拿去回覆別人。"""
    return (result or {}).get("summary", "").startswith("AI 分析暫時無法使用")


def _strip_mentions(text: str) -> str:
    """去掉 @帳號 標記，留下真正要查核的文字。"""
    return _MENTION_RE.sub("", text or "").strip()


async def _resolve_target_text(svc: ThreadsService, mention: dict) -> Optional[str]:
    """決定要查核的文字：優先抓「被回覆的原貼文」，否則用 mention 本身。"""
    replied_to = mention.get("replied_to") or {}
    parent_id = replied_to.get("id") if isinstance(replied_to, dict) else replied_to
    if parent_id:
        try:
            parent = await asyncio.to_thread(svc.get_post, str(parent_id))
            text = _strip_mentions(parent.get("text", ""))
            if len(text) >= _MIN_TEXT_LEN:
                return text
        except Exception as e:
            print(f"[ThreadsBot] 抓原貼文 {parent_id} 失敗: {e}")
    text = _strip_mentions(mention.get("text", ""))
    return text if len(text) >= _MIN_TEXT_LEN else None


async def run_threads_poll() -> dict:
    """
    輪詢一次 mentions 並回覆。由排程（ENABLE_THREADS_BOT=true）或
    POST /api/threads/poll 手動觸發。回傳統計 dict 方便 API 顯示。
    """
    stats = {"checked": 0, "replied": 0, "skipped": 0, "errors": 0}
    svc = ThreadsService()
    if not svc.available:
        print("[ThreadsBot] 未設定 THREADS_ACCESS_TOKEN / THREADS_USER_ID，跳過")
        return stats

    try:
        me = await asyncio.to_thread(svc.get_profile)
        bot_username = (me.get("username") or "").lower()
        mentions = await asyncio.to_thread(svc.get_mentions)
    except Exception as e:
        print(f"[ThreadsBot] 讀取 mentions 失敗（token 過期或權限不足？）: {e}")
        stats["errors"] += 1
        return stats

    state = _load_state()
    replied_ids = set(state.get("replied_ids", []))
    task_store = TaskStore()

    # 延遲 import，避免 app 啟動時就載入整條分析管線
    from app.workers.pandas_task_processor import process_analysis_task_async

    for m in mentions:
        mid = str(m.get("id") or "")
        if not mid or mid in replied_ids:
            continue
        if (m.get("username") or "").lower() == bot_username:
            continue  # 自己的貼文不回，避免自我循環
        stats["checked"] += 1

        text = await _resolve_target_text(svc, m)
        if not text:
            replied_ids.add(mid)   # 沒有可查核文字，標記掉避免每輪重看
            stats["skipped"] += 1
            continue

        try:
            task_id = task_store.create_task("threads_mention", text)
            result = await process_analysis_task_async(task_id, text, "text")
        except Exception as e:
            print(f"[ThreadsBot] 分析失敗 mention={mid}: {e}")
            stats["errors"] += 1
            continue

        if _is_fallback(result):
            # AI 暫時無法使用：不回覆也不標記，額度恢復後下一輪自動補回
            print(f"[ThreadsBot] AI 暫時無法使用，mention={mid} 留待下輪")
            stats["skipped"] += 1
            continue

        reply_text = format_verdict_reply(result)
        try:
            reply_id = await asyncio.to_thread(svc.reply_to, mid, reply_text)
            if reply_id:
                replied_ids.add(mid)
                stats["replied"] += 1
                print(f"[ThreadsBot] 已回覆 mention={mid} -> {result.get('risk_type')}")
            else:
                stats["errors"] += 1
        except Exception as e:
            print(f"[ThreadsBot] 回覆失敗 mention={mid}: {e}")
            stats["errors"] += 1

    state["replied_ids"] = list(replied_ids)
    _save_state(state)
    print(f"[ThreadsBot] 本輪完成: {stats}")
    return stats
