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
  * reply_to：回覆對象 id 等於該 mention 的 id（逐則 mention）；在兩段式發佈的**第一步**
    （create_reply_container）觸發，"create_container" 為同義寫法
  * container_status／publish：兩段式發佈的第二、三步（get_container_status／publish_container）
  * get_post：**以貼文為單位**。get_post(media_id) 只拿得到貼文 id、不知道是哪則 mention 在查，
    所以 mention 上的 get_post 注入等於「該 mention 的 replied_to.id（或 mention 自身 id）這則貼文
    讀不到」——**其他回覆同一貼文的 mention 也會一起 403**。要讓某則貼文讀不到，建議改在
    posts 項目上直接放 "_sim_error": {"on": "get_post", "http": 403}（語意明確）；
    要模擬「同一貼文、只有一則 mention 讀不到」，請讓那則 mention 指向另一個 post id。
  * 選用鍵："body"（回應內容，例如含 THREADS_API__LINK_LIMIT_EXCEEDED 的字串）、
    "if_text_contains"（只有送出的文字含該子字串時才觸發；模擬「連結超限、去掉來源行重送就成功」）
- 兩段式發佈（spec 7.6；T-12）：create_reply_container → get_container_status → publish_container，
  container 存在 data/threads_sim/containers.json（sim 每輪重建客戶端，pending_publish 要跨輪補發，
  所以 container 必須落檔）。預設第一次查狀態就 FINISHED（不增加 sim 回覆延遲）。
  mention 可帶 "_sim_container": {"statuses": ["IN_PROGRESS", "FINISHED"], "error_message": "..."}
  （或直接給狀態陣列）：**建立 container 當下**把狀態序列複製進該 container，之後每查一次前進一格、
  用完停在最後一格；所以改 mentions.json 只影響之後新建的 container。publish_container 只接受
  最近一次查到 FINISHED 的 container（模擬真 API；過早 publish 回 HTTP 400），已發佈的 container
  狀態為 PUBLISHED、再 publish 回 HTTP 400 且不重複寫 replies.jsonl。
"""
import copy
import json
import os
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from app.services.threads_service import (
    CONTAINER_ERROR,
    CONTAINER_FINISHED,
    CONTAINER_PUBLISHED,
    ThreadsApiError,
    TwoStepPublishing,
)

SIM_DIR = Path("data") / "threads_sim"
MENTIONS_PATH = SIM_DIR / "mentions.json"

CONTAINERS_MAX = 200   # containers.json 只留最近 200 個（模擬用，避免長期重播無限長大）

_WRITE_LOCK = threading.Lock()
# containers.json 的讀改寫；publish_container 會在持有它時呼叫 _append（再取 _WRITE_LOCK），順序固定、不會反向
_CONTAINERS_LOCK = threading.RLock()
# {containers.json 路徑: ((mtime_ns, size), 檔案文字)}：只在 _CONTAINERS_LOCK 內讀寫；簽章不符就重讀
_CONTAINERS_CACHE: Dict[str, Any] = {}


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


class FakeThreadsService(TwoStepPublishing):
    """ThreadsClient 的 sim 實作。不需要 token；檔案不存在時視為沒有任何 mention。
    wait_container／reply_to 的串接流程與 live 共用 TwoStepPublishing（spec 7.6）。"""

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
        containers_path: Union[str, Path, None] = None,
    ):
        self.mentions_path = Path(mentions_path) if mentions_path is not None else MENTIONS_PATH
        self.replies_path = (
            Path(replies_path) if replies_path is not None else self.mentions_path.parent / "replies.jsonl"
        )
        # publish_text 的自發貼文（spec 7.9 的 replies.jsonl 只放回覆，故分檔）
        self.posts_path = (
            Path(posts_path) if posts_path is not None else self.mentions_path.parent / "posts.jsonl"
        )
        # 兩段式發佈的 container（模擬 Threads 伺服器端的狀態；跨輪、跨實例共用）
        self.containers_path = (
            Path(containers_path) if containers_path is not None
            else self.mentions_path.parent / "containers.json"
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
    def _raise_if(mention: Optional[Dict[str, Any]], on: str, text: Optional[str] = None) -> None:
        """mention（或 post）帶 on 相符的 _sim_error 就丟 ThreadsApiError。
        if_text_contains：只有送出的 text 含該子字串才觸發（沒有 text 可比對時不觸發）。"""
        err = mention.get("_sim_error") if isinstance(mention, dict) else None
        if isinstance(err, dict) and err.get("on") == on:
            needle = err.get("if_text_contains")
            if needle and str(needle) not in str(text or ""):
                return
            status = err.get("http")
            try:
                status = int(status)
            except (TypeError, ValueError):
                status = None
            body = err.get("body") or {"error": {"message": f"sim injected HTTP {status} on {on}"}}
            raise ThreadsApiError(status, body)

    def _mention(self, mention_id: Any) -> Optional[Dict[str, Any]]:
        mid = str(mention_id)
        for m in self._load().get("mentions") or []:
            if isinstance(m, dict) and str(m.get("id")) == mid:
                return m
        return None

    # ── container 儲存（data/threads_sim/containers.json）───────────
    @staticmethod
    def _file_signature(path: Path) -> Optional[tuple]:
        try:
            st = os.stat(path)
        except OSError:
            return None
        return st.st_mtime_ns, st.st_size

    def _read_containers_text(self) -> Optional[str]:
        """讀 containers.json 的文字；檔案自上次讀寫後沒變（mtime＋大小相同）就用行程內的快取。
        一則回覆要讀這個檔 3 次，而 Windows 上「剛改過的檔再開一次」每次約 10 ms（即時掃毒），
        快取讓 sim 的兩段式發佈幾乎不增加回覆延遲；別的行程或手動改檔會改變 mtime／大小，照樣重讀。"""
        key = os.path.abspath(self.containers_path)
        signature = self._file_signature(self.containers_path)
        if signature is None:
            _CONTAINERS_CACHE.pop(key, None)
            return None
        cached = _CONTAINERS_CACHE.get(key)
        if cached is not None and cached[0] == signature:
            return cached[1]
        try:
            text = self.containers_path.read_text(encoding="utf-8")
        except OSError:
            return None
        _CONTAINERS_CACHE[key] = (signature, text)
        return text

    def _load_containers(self) -> Dict[str, Any]:
        try:
            data = json.loads(self._read_containers_text() or "")
        except ValueError:
            data = None
        if not isinstance(data, dict) or not isinstance(data.get("containers"), dict):
            data = {"seq": 0, "containers": {}}
        try:
            data["seq"] = int(data.get("seq") or 0)
        except (TypeError, ValueError):
            data["seq"] = 0
        return data

    def _save_containers(self, data: Dict[str, Any]) -> None:
        containers = data.get("containers") or {}
        if len(containers) > CONTAINERS_MAX:
            data["containers"] = dict(list(containers.items())[-CONTAINERS_MAX:])
        path = self.containers_path
        path.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps(data, ensure_ascii=False, indent=1)
        fd, tmp_name = tempfile.mkstemp(prefix=f"{path.name}.", suffix=".tmp", dir=str(path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(text)
            # 改名不會動 mtime／大小：先取 temp 檔的簽章，之後若被別的行程換掉，簽章對不上就會重讀
            signature = self._file_signature(Path(tmp_name))
            os.replace(tmp_name, path)
        except BaseException:
            _CONTAINERS_CACHE.pop(os.path.abspath(path), None)
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise
        if signature is not None:
            _CONTAINERS_CACHE[os.path.abspath(path)] = (signature, text)
        else:
            _CONTAINERS_CACHE.pop(os.path.abspath(path), None)

    @staticmethod
    def _container_statuses(mention: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """mention 的 _sim_container → {"statuses": [...], "error_message": ...}；沒有注入 → 直接 FINISHED。"""
        spec = mention.get("_sim_container") if isinstance(mention, dict) else None
        if isinstance(spec, dict):
            raw, message = spec.get("statuses"), spec.get("error_message")
        else:
            raw, message = spec, None
        statuses = [str(s).strip().upper() for s in raw if str(s).strip()] if isinstance(raw, list) else []
        return {"statuses": statuses or [CONTAINER_FINISHED], "error_message": message}

    def _get_container(self, data: Dict[str, Any], container_id: Any) -> Dict[str, Any]:
        container = data["containers"].get(str(container_id))
        if not isinstance(container, dict):
            raise ThreadsApiError(404, {"error": {"message": f"sim container {container_id} not found"}})
        return container

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

    # ── 兩段式發佈（spec 7.6）：三個原子操作，串接流程在 TwoStepPublishing ─────────
    def create_reply_container(self, media_id: str, text: str, result_id: Optional[str] = None) -> Optional[str]:
        """第一步：建立 container（寫 containers.json），回傳 sim_container_{n}。
        "reply_to"／"create_container" 的錯誤注入在這一步觸發（什麼都還沒寫）。"""
        mid = str(media_id)
        mention = self._mention(mid)
        self._raise_if(mention, "reply_to", text)
        self._raise_if(mention, "create_container", text)
        with _CONTAINERS_LOCK:
            data = self._load_containers()
            data["seq"] += 1
            container_id = f"sim_container_{data['seq']}"
            data["containers"][container_id] = {
                "mention_id": mid,
                "text": text,
                "result_id": result_id,
                "created_at": datetime.now(timezone.utc).isoformat(),
                **self._container_statuses(mention),
                "checks": 0,
                "last_status": None,
                "reply_id": None,
            }
            self._save_containers(data)
        return container_id

    def get_container_status(self, container_id: str) -> Dict[str, Any]:
        """第二步：回 {"id","status"[,"error_message"]}；每查一次，狀態序列前進一格。"""
        with _CONTAINERS_LOCK:
            data = self._load_containers()
            container = self._get_container(data, container_id)
            self._raise_if(self._mention(container.get("mention_id")), "container_status", container.get("text"))
            if container.get("reply_id"):
                return {"id": str(container_id), "status": CONTAINER_PUBLISHED}
            statuses = container.get("statuses") or [CONTAINER_FINISHED]
            checks = int(container.get("checks") or 0)
            status = str(statuses[min(checks, len(statuses) - 1)]).upper()
            container["checks"] = checks + 1
            container["last_status"] = status
            self._save_containers(data)
        out: Dict[str, Any] = {"id": str(container_id), "status": status}
        if status == CONTAINER_ERROR:
            out["error_message"] = container.get("error_message") or "sim container error"
        return out

    def publish_container(self, container_id: str) -> Optional[str]:
        """第三步：追加一行到 replies.jsonl，回傳 sim_reply_{n}（n 為檔內第幾行，遞增）。
        只接受最近一次查到 FINISHED、且尚未發佈的 container（與真 API 相同：過早或重複 publish 回 400）。"""
        with _CONTAINERS_LOCK:
            data = self._load_containers()
            container = self._get_container(data, container_id)
            self._raise_if(self._mention(container.get("mention_id")), "publish", container.get("text"))
            if container.get("reply_id"):
                raise ThreadsApiError(400, {"error": {"message": f"sim container {container_id} already published"}})
            if container.get("last_status") != CONTAINER_FINISHED:
                raise ThreadsApiError(400, {"error": {
                    "message": f"sim container {container_id} is not FINISHED (status={container.get('last_status')})",
                }})
            reply_id = self._append(
                self.replies_path,
                {"mention_id": container.get("mention_id"), "result_id": container.get("result_id"),
                 "text": container.get("text")},
                "sim_reply",
                "reply_id",
            )
            container["reply_id"] = reply_id
            self._save_containers(data)
        return reply_id

    def reply_to(self, media_id: str, text: str, result_id: Optional[str] = None) -> Optional[str]:
        """三步串接（TwoStepPublishing）；成功時追加一行到 replies.jsonl 並回傳 sim_reply_{n}。"""
        return super().reply_to(media_id, text, result_id=result_id)

    def publish_text(self, text: str) -> Optional[str]:
        """機器人自發貼文：寫 posts.jsonl（不寫 replies.jsonl），回傳 sim_post_{n}。"""
        return self._append(self.posts_path, {"text": text}, "sim_post", "post_id")

    def get_publishing_limit(self) -> Dict[str, Any]:
        return copy.deepcopy(self._load().get("publishing_limit") or {})

    def refresh_token(self) -> Dict[str, Any]:
        """sim 沒有 token，不做事。"""
        return {"refreshed": False, "mode": "sim"}
