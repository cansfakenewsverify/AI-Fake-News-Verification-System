"""
Threads 模擬模式（THREADS_MODE=sim，spec 7.9）— FakeThreadsService。

用本機 JSON 檔取代真 Threads Graph API，讓機器人閉環在「無網路、無 token」下
也能跑（demo 保險兼離線測試）。其餘流程（管線、模板、去重、狀態）與 live 相同。

- 讀：data/threads_sim/mentions.json（形狀鏡射 Graph API，見
  scripts/threads_sim_mentions.example.json）
- 寫：data/threads_sim/replies.jsonl，每行 {"ts","mention_id","reply_id","result_id","text"}
  （只放 reply_to 的回覆；publish_text 的機器人自發貼文另寫 posts.jsonl，不佔 sim_reply_{n} 編號）
  （共用 data/threads_replies.jsonl 由 threads_bot 經 threads_state 寫，不在這裡）
- 錯誤注入：mention 物件可帶 "_sim_error": {"on": "get_post"|"get_mentions"|"reply_to", "http": 403}，
  觸發時丟 ThreadsApiError(status=http)，以 HTTP 狀態碼分流（spec 7.10）。
  * get_mentions：since 過濾後仍在清單中的 mention 帶此注入 → 整次讀取失敗
  * reply_to：回覆對象 id 等於該 mention 的 id（逐則 mention）
  * get_post：**以貼文為單位**。get_post(media_id) 只拿得到貼文 id、不知道是哪則 mention 在查，
    所以 mention 上的 get_post 注入等於「該 mention 的 replied_to.id（或 mention 自身 id）這則貼文
    讀不到」——**其他回覆同一貼文的 mention 也會一起 403**。要讓某則貼文讀不到，建議改在
    posts 項目上直接放 "_sim_error": {"on": "get_post", "http": 403}（語意明確）；
    要模擬「同一貼文、只有一則 mention 讀不到」，請讓那則 mention 指向另一個 post id。
"""
import copy
import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from app.services.threads_service import ThreadsApiError

SIM_DIR = Path("data") / "threads_sim"
MENTIONS_PATH = SIM_DIR / "mentions.json"

_WRITE_LOCK = threading.Lock()


def _to_epoch(value: Any) -> Optional[float]:
    """把 unix 秒數或 Graph API 時間字串（2026-09-14T08:00:00+0000）轉成 epoch 秒。"""
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip()
    try:
        return float(s)
    except ValueError:
        pass
    s = s.replace("Z", "+00:00")
    # +0000 → +00:00（Python 3.10 以前的 fromisoformat 不吃無冒號時區）
    if len(s) >= 5 and s[-5] in "+-" and s[-4:].isdigit():
        s = f"{s[:-2]}:{s[-2:]}"
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


def _replied_to_id(mention: Dict[str, Any]) -> Optional[str]:
    rt = mention.get("replied_to")
    if isinstance(rt, dict):
        rt = rt.get("id")
    return str(rt) if rt else None


class FakeThreadsService:
    """ThreadsClient 的 sim 實作。不需要 token；檔案不存在時視為沒有任何 mention。"""

    mode = "sim"
    invalid_reason: Optional[str] = None
    token_expires_at = None
    authorized_at = None
    token_days_left = None
    auth_days_left = None

    def __init__(
        self,
        mentions_path: Union[str, Path, None] = None,
        replies_path: Union[str, Path, None] = None,
        posts_path: Union[str, Path, None] = None,
    ):
        self.mentions_path = Path(mentions_path) if mentions_path is not None else MENTIONS_PATH
        self.replies_path = (
            Path(replies_path) if replies_path is not None else self.mentions_path.parent / "replies.jsonl"
        )
        # publish_text 的自發貼文（spec 7.9 的 replies.jsonl 只放回覆，故分檔）
        self.posts_path = (
            Path(posts_path) if posts_path is not None else self.mentions_path.parent / "posts.jsonl"
        )

    # ── 內部 ─────────────────────────────────────────────────────
    @property
    def available(self) -> bool:
        return True

    def _load(self) -> Dict[str, Any]:
        try:
            with open(self.mentions_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    @staticmethod
    def _raise_if(mention: Dict[str, Any], on: str) -> None:
        err = mention.get("_sim_error")
        if isinstance(err, dict) and err.get("on") == on:
            status = err.get("http")
            try:
                status = int(status)
            except (TypeError, ValueError):
                status = None
            body = err.get("body") or {"error": {"message": f"sim injected HTTP {status} on {on}"}}
            raise ThreadsApiError(status, body)

    @staticmethod
    def _count_lines(path: Path) -> int:
        try:
            with open(path, "r", encoding="utf-8") as f:
                return sum(1 for line in f if line.strip())
        except OSError:
            return 0

    def _append(self, path: Path, record: Dict[str, Any], prefix: str, id_key: str) -> str:
        """追加一行 JSON 到 path；id 為 {prefix}_{該檔第幾行}。"""
        with _WRITE_LOCK:
            path.parent.mkdir(parents=True, exist_ok=True)
            n = self._count_lines(path) + 1
            rid = f"{prefix}_{n}"
            line = {"ts": datetime.now(timezone.utc).isoformat(), **record, id_key: rid}
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(line, ensure_ascii=False) + "\n")
        return rid

    # ── ThreadsClient ────────────────────────────────────────────
    def get_profile(self) -> Dict[str, Any]:
        bot = self._load().get("bot") or {}
        return dict(bot)

    def get_mentions(self, since: Any = None, after_cursor: Optional[str] = None) -> List[Dict[str, Any]]:
        """讀 mentions.json，只回 timestamp > since 的 mention（sim 無分頁，after_cursor 忽略）。"""
        since_ts = _to_epoch(since)
        out: List[Dict[str, Any]] = []
        for m in self._load().get("mentions") or []:
            if not isinstance(m, dict):
                continue
            ts = _to_epoch(m.get("timestamp"))
            if since_ts is not None and (ts is None or ts <= since_ts):
                continue
            out.append(m)
        for m in out:
            self._raise_if(m, "get_mentions")
        return copy.deepcopy(out)

    def get_post(self, media_id: str) -> Dict[str, Any]:
        data = self._load()
        mid = str(media_id)
        post = (data.get("posts") or {}).get(mid)
        # 貼文層級注入（建議寫法，語意明確）
        if isinstance(post, dict):
            self._raise_if(post, "get_post")
        # mention 層級注入（spec 7.9 形狀）：以貼文為單位生效，見模組 docstring
        for m in data.get("mentions") or []:
            if isinstance(m, dict) and mid in (_replied_to_id(m), str(m.get("id"))):
                self._raise_if(m, "get_post")
        if not isinstance(post, dict):
            raise ThreadsApiError(404, {"error": {"message": f"sim post {mid} not found"}})
        out = copy.deepcopy(post)
        out.pop("_sim_error", None)
        return out

    def reply_to(self, media_id: str, text: str, result_id: Optional[str] = None) -> Optional[str]:
        """追加一行到 replies.jsonl，回傳 sim_reply_{n}（n 為檔內第幾行，遞增）。"""
        mid = str(media_id)
        for m in self._load().get("mentions") or []:
            if isinstance(m, dict) and str(m.get("id")) == mid:
                self._raise_if(m, "reply_to")
        return self._append(
            self.replies_path,
            {"mention_id": mid, "result_id": result_id, "text": text},
            "sim_reply",
            "reply_id",
        )

    def publish_text(self, text: str) -> Optional[str]:
        """機器人自發貼文：寫 posts.jsonl（不寫 replies.jsonl），回傳 sim_post_{n}。"""
        return self._append(self.posts_path, {"text": text}, "sim_post", "post_id")

    def get_publishing_limit(self) -> Dict[str, Any]:
        return copy.deepcopy(self._load().get("publishing_limit") or {})

    def refresh_token(self) -> Dict[str, Any]:
        """sim 沒有 token，不做事。"""
        return {"refreshed": False, "mode": "sim"}
