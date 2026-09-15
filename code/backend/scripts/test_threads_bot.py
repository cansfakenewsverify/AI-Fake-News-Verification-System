"""
Threads 查核機器人：乾跑、憑證檢查、sim 重播與觸發一輪輪詢（T-11；spec §5.2、§7.9、FR-10）。

用法（腳本會自動切到 code\\backend，讀它的 .env 與 data\\）：
    venv\\Scripts\\python scripts\\test_threads_bot.py              乾跑：檢查設定＋產生範例回覆（data/threads_reply_sample.txt）
    venv\\Scripts\\python scripts\\test_threads_bot.py --live       有 token 時：驗證憑證＋讀 mentions 筆數
    venv\\Scripts\\python scripts\\test_threads_bot.py --reset-sim  sim 重播：清模擬回覆紀錄與輪詢游標，並離線預熱快取
    venv\\Scripts\\python scripts\\test_threads_bot.py --poll       觸發一輪輪詢並印出結果（sim 不需 Threads token；
                                                                  live 模式會真的回覆貼文、可能花 AI 點數）

--poll：讀 .env 的 ADMIN_TOKEN（不印出）→ POST {api}/api/threads/poll → 202 後每 2 秒讀
        /api/threads/status 的 last_poll_at 直到變動（最多 5 分鐘）→ 印 last_poll_stats 與本輪每則回覆：
            poll -> mention m1 -> cache hash -> sources: 1 x tier1 -> reply sim_reply_1
        --api 連不上（後端沒開）時退回在本程序內直接跑一輪 run_threads_poll()。
--reset-sim：清空 data/threads_sim/replies.jsonl、刪掉 data/threads_replies.jsonl 中 mode=sim 的行、
        從 state 的 replied_ids 移除模擬 mention id（live 的 id 保留，切回 live 才不會重複回覆）、last_since 歸零、
        移除殘留的 data/threads_poll.lock；data/threads_sim/mentions.json 不存在時從範例檔複製一份。
        離線預熱：mentions.json 中會送進 AI 的文字貼文，若知識庫「第一筆同 hash 列」不是已證實的判定，
        就從 scripts/threads_sim_seed.json 以 label_source="gold" 種入 → poll 時 L1 hash 命中、不呼叫 AI、斷網也能回覆。
        embedding 有設定時順便寫入向量（供網站「語意相似」命中）；失敗或斷網只寫 hash，不影響 sim 閉環。

主控台是 cp950：輸出只用 ASCII＋中文（無法編碼的字元自動跳脫）；回覆全文請看 data/threads_sim/replies.jsonl（UTF-8）。
"""
import argparse
import asyncio
import json
import logging
import os
import shutil
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Set, Tuple

BACKEND_DIR = Path(__file__).resolve().parent.parent
EXAMPLE_MENTIONS = BACKEND_DIR / "scripts" / "threads_sim_mentions.example.json"
SEED_PATH = BACKEND_DIR / "scripts" / "threads_sim_seed.json"

# 等同 http://localhost:8000；用 127.0.0.1 避開 Windows 先試 IPv6（::1）被拒時的約 2 秒連線延遲
DEFAULT_API = "http://127.0.0.1:8000"
POLL_INTERVAL_SECONDS = 2.0
POLL_TIMEOUT_SECONDS = 300.0
HTTP_TIMEOUT_SECONDS = 10.0
REPLIES_WINDOW = 50
STAT_KEYS = ("checked", "replied", "skipped", "errors")


def _early_workdir(argv: List[str]) -> Path:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--workdir")
    known, _ = parser.parse_known_args(argv)
    return Path(known.workdir).resolve() if known.workdir else BACKEND_DIR


if __name__ == "__main__":
    # settings 在 import 時讀「工作目錄」的 .env，data/ 也是相對路徑：先切目錄再 import app
    os.chdir(_early_workdir(sys.argv[1:]))

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import requests  # noqa: E402

from app.config import settings  # noqa: E402
from app.services import threads_state  # noqa: E402
from app.services.cache_service import CacheService  # noqa: E402
from app.services.threads_reply import (  # noqa: E402
    THREADS_TARGET_LEN,
    THREADS_TEXT_LIMIT,
    format_verdict_reply,
    reply_cannot_read,
    reply_media_only,
    reply_too_short,
    threads_len,
)
from app.services.threads_service import ThreadsApiError, ThreadsService  # noqa: E402
from app.services.threads_sim import _to_epoch  # noqa: E402
from app.utils.source_tier import tier_of  # noqa: E402
from app.utils.verdict import frame_of, is_fallback  # noqa: E402
from app.workers import threads_bot  # noqa: E402

Out = Callable[[str], None]


def say(msg: Any = "") -> None:
    """cp950 主控台安全輸出：無法編碼的字元（emoji 等）以 \\U 形式跳脫，永不 UnicodeEncodeError。"""
    stream = sys.stdout
    enc = getattr(stream, "encoding", None) or "utf-8"
    try:
        text = str(msg).encode(enc, "backslashreplace").decode(enc, "replace")
    except LookupError:
        text = str(msg).encode("ascii", "backslashreplace").decode("ascii")
    stream.write(text + "\n")
    stream.flush()


def _rel(path: Path) -> str:
    """顯示用路徑：工作目錄下的轉相對（不在畫面上露出本機絕對路徑）。"""
    p = Path(path)
    try:
        return p.resolve().relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return p.as_posix()


# ══════════════════════════════════════════════════════════════════
# 乾跑與 --live
# ══════════════════════════════════════════════════════════════════
SAMPLE_RESULT = {
    "result_id": "sample",
    "is_risk": True,
    "risk_type": "SCAM",
    "confidence_score": 0.9,
    "confidence_level": "高",
    "summary": "假冒銀行的釣魚簡訊，誘導點擊連結輸入帳號密碼。",
    "explanation": "此訊息宣稱帳戶異常要求立即點擊連結驗證，符合釣魚詐騙典型話術；"
                   "銀行不會以簡訊要求輸入帳密。",
    "verification_status": "verified",
    "sources": [{"title": "165 反詐騙", "url": "https://165.npa.gov.tw/", "tier": 1, "tier_label": "查核機構"}],
}


def dry_run(out: Out = say) -> int:
    svc = ThreadsService()
    out(f"[test] THREADS_MODE（生效）= {settings.threads_mode_effective}")
    out(f"[test] token 已設定      = {bool(svc.token)}")
    out(f"[test] user_id 已設定    = {bool(svc.user_id)}")
    out(f"[test] ADMIN_TOKEN 已設定 = {bool((settings.ADMIN_TOKEN or '').strip())}")
    out(f"[test] poll 間隔         = {settings.THREADS_POLL_MINUTES} 分鐘")

    # 驗證回覆格式（寫檔避免 cp950 印不出 emoji）；長度以 Threads 計數規則 threads_len 判斷
    reply = format_verdict_reply(SAMPLE_RESULT)
    path = Path("data") / "threads_reply_sample.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(reply, encoding="utf-8")
    n = threads_len(reply)
    out(f"[test] 範例回覆已寫入 {_rel(path)}（threads_len={n}，目標 {THREADS_TARGET_LEN}、上限 {THREADS_TEXT_LIMIT}）")
    if n > THREADS_TEXT_LIMIT:
        out("[test] 範例回覆超過 Threads 上限")
        return 1
    return 0


def live_check(out: Out = say) -> int:
    svc = ThreadsService()
    if not svc.available:
        reason = svc.invalid_reason or "未設定 THREADS_ACCESS_TOKEN / THREADS_USER_ID（或 data/threads_token.json）"
        out(f"[live] 無法 live 測試：{reason}")
        return 1
    try:
        me = svc.get_profile()
        out(f"[live] 憑證 OK：id={me.get('id')} username={me.get('username')}")
        mentions = svc.get_mentions(limit=5)
        out(f"[live] 最近 mentions：{len(mentions)} 筆")
    except Exception as e:  # ThreadsApiError 的訊息已遮蔽 token
        out(f"[live] Threads API 呼叫失敗：{e}")
        return 1
    return 0


# ══════════════════════════════════════════════════════════════════
# --reset-sim（含離線預熱）
# ══════════════════════════════════════════════════════════════════
def _pid_alive(pid: Any) -> Optional[bool]:
    """行程是否還在：True／False；判斷不了回 None。Windows 不可用 os.kill(pid, 0)（會直接結束該行程）。"""
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
        return None
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        kernel32.GetExitCodeProcess.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
        kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
        process_query_limited_information, still_active = 0x1000, 259
        handle = kernel32.OpenProcess(process_query_limited_information, False, pid)
        if not handle:
            err = ctypes.get_last_error()
            if err == 5:      # ERROR_ACCESS_DENIED：行程存在但無權查詢
                return True
            if err == 87:     # ERROR_INVALID_PARAMETER：沒有這個 pid
                return False
            return None
        try:
            code = wintypes.DWORD()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                return None
            return code.value == still_active
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return None
    return True


def clear_stale_poll_lock(lock: Path) -> Tuple[str, Optional[str]]:
    """回傳 ("none"|"removed"|"busy", 說明)。超過 15 分鐘，或寫鎖的行程已結束 → 殘留，刪除。"""
    if not lock.exists():
        return "none", None
    info = threads_bot._read_lock(lock) or {}
    age = threads_bot._lock_age_seconds(lock)
    if age is None:                       # 剛好被釋放
        return "none", None
    pid = info.get("pid")
    stale_minutes = int(threads_bot.LOCK_STALE_SECONDS // 60)
    if age > threads_bot.LOCK_STALE_SECONDS:
        reason = f"已超過 {stale_minutes} 分鐘"
    elif _pid_alive(pid) is False:
        reason = f"寫鎖的行程 pid {pid} 已結束"
    else:
        return "busy", f"pid {pid}，{int(age)} 秒前開始"
    try:
        lock.unlink()
    except FileNotFoundError:
        pass
    return "removed", reason


def ensure_mentions(mentions_path: Path, example_path: Path = EXAMPLE_MENTIONS) -> bool:
    """mentions.json 不存在時從範例檔複製；有複製回 True。"""
    if mentions_path.exists():
        return False
    mentions_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(example_path, mentions_path)
    return True


UTF8_BOM = b"\xef\xbb\xbf"


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))   # 容忍 BOM（記事本／PowerShell 存檔）
    except (OSError, ValueError):
        return None


def strip_utf8_bom(path: Path) -> bool:
    """去掉檔頭 UTF-8 BOM：後端 FakeThreadsService 以 utf-8 讀，有 BOM 會當成空檔（一則 mention 都讀不到）。"""
    try:
        raw = path.read_bytes()
    except OSError:
        return False
    if not raw.startswith(UTF8_BOM):
        return False
    _atomic_write_bytes(path, raw[len(UTF8_BOM):])
    return True


def check_mentions_file(mentions_path: Path) -> Optional[str]:
    """mentions.json 可用 → None；否則回傳問題說明（錄影前手動刪 m2／m3 時最常打錯 JSON）。"""
    try:
        data = json.loads(mentions_path.read_text(encoding="utf-8"))
    except UnicodeDecodeError:
        return "不是 UTF-8 編碼，請用 UTF-8 存檔"
    except ValueError as e:
        return f"JSON 格式錯誤（第 {getattr(e, 'lineno', '?')} 行第 {getattr(e, 'colno', '?')} 欄）"
    except OSError as e:
        return f"無法讀取（{type(e).__name__}）"
    if not isinstance(data, dict) or not isinstance(data.get("mentions"), list):
        return "缺少 mentions 陣列"
    return None


def _mention_ids_in_file(mentions_path: Path) -> Set[str]:
    data = _load_json(mentions_path)
    mentions = data.get("mentions") if isinstance(data, dict) else None
    return {str(m["id"]) for m in mentions or [] if isinstance(m, dict) and m.get("id")}


def _jsonl_rows(raw: bytes) -> Iterable[Tuple[bytes, Optional[dict]]]:
    """逐行（位元組）解析 jsonl：(原始行, dict 或 None)；空行略過，非 UTF-8／非 JSON 的行 obj=None。"""
    for line in raw.splitlines():
        if not line.strip():
            continue
        try:
            obj = json.loads(line.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            obj = None
        yield line, obj if isinstance(obj, dict) else None


def truncate_sim_replies(path: Path) -> Tuple[int, Set[str]]:
    """清空 data/threads_sim/replies.jsonl（保留空檔，編輯器開著也會跟著更新）。回傳 (原行數, mention ids)。"""
    if not path.exists():
        return 0, set()
    rows = list(_jsonl_rows(path.read_bytes()))
    ids = {str(obj["mention_id"]) for _, obj in rows if obj and obj.get("mention_id")}
    path.write_bytes(b"")
    return len(rows), ids


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    import tempfile

    fd, tmp = tempfile.mkstemp(prefix=f"{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def drop_sim_reply_records(data_dir: Path) -> Tuple[int, int, Set[str]]:
    """刪掉 threads_replies.jsonl 中 mode=sim 的行；live 與無法解析的行逐位元組原樣保留（原子寫入）。
    回傳 (刪, 留, mention ids)。"""
    path = threads_state.replies_path(data_dir)
    if not path.exists():
        return 0, 0, set()
    kept: List[bytes] = []
    removed = 0
    ids: Set[str] = set()
    for line, obj in _jsonl_rows(path.read_bytes()):
        if obj is not None and obj.get("mode") == "sim":
            removed += 1
            if obj.get("mention_id"):
                ids.add(str(obj["mention_id"]))
            continue
        kept.append(line)
    if removed:
        _atomic_write_bytes(path, b"".join(line + b"\n" for line in kept))
    return removed, len(kept), ids


def reset_state(data_dir: Path, sim_ids: Set[str]) -> Tuple[int, int]:
    """replied_ids 移除模擬 mention id（live 的保留）、last_since 歸零；failed／pending_publish 同步移除模擬 id。"""
    state = threads_state.load_state(data_dir)
    ids = [str(x) for x in state.get("replied_ids") or []]
    kept = [x for x in ids if x not in sim_ids]
    state["replied_ids"] = kept
    state["last_since"] = 0
    for key in ("failed", "pending_publish"):
        bucket = state.get(key)
        if isinstance(bucket, dict):
            state[key] = {k: v for k, v in bucket.items() if str(k) not in sim_ids}
    threads_state.save_state(state, data_dir)
    return len(ids) - len(kept), len(kept)


def load_seeds(seed_path: Path = SEED_PATH) -> Dict[str, Dict[str, Any]]:
    """{內容 hash: seed}；檔案不存在或格式錯 → {}。"""
    data = _load_json(seed_path)
    seeds: Dict[str, Dict[str, Any]] = {}
    for seed in (data.get("seeds") if isinstance(data, dict) else None) or []:
        if not isinstance(seed, dict):
            continue
        text, result = seed.get("text"), seed.get("result")
        if isinstance(text, str) and text and isinstance(result, dict):
            seeds[CacheService.generate_hash(text)] = seed
    return seeds


async def _analysis_targets(client: Any, data_dir: Path) -> List[Tuple[str, str, str]]:
    """用與 bot 相同的 resolve_target 算出「poll 時會送進 AI」的內容：[(標籤, 文字或網址, input_type)]。"""
    own_ids = await asyncio.to_thread(threads_state.own_reply_ids, data_dir)
    bot = str(settings.BOT_HANDLE or "").strip().lstrip("@").lower()
    try:
        mentions = client.get_mentions(None)
    except ThreadsApiError:
        return []
    targets: List[Tuple[str, str, str]] = []
    seen: Set[str] = set()
    for m in mentions:
        if bot and str(m.get("username") or "").lower() == bot:
            continue
        kind, text, input_type, target = await threads_bot.resolve_target(
            client, m, own_ids=own_ids, data_dir=data_dir, bot_handle=settings.BOT_HANDLE,
        )
        if kind != threads_bot.KIND_TEXT or not text:
            continue
        content_hash = CacheService.generate_hash(text)
        if content_hash in seen:
            continue
        seen.add(content_hash)
        targets.append((str(target.get("id") or m.get("id") or "?"), text, input_type))
    return targets


def _first_hash_row(df: Any, content_hash: str) -> Optional[Dict[str, Any]]:
    """與 PandasStore.find_by_hash 相同的選列規則（第一筆同 hash 列），但唯讀、不遞增 hit_count。"""
    if df is None or df.empty or "data_hash" not in df.columns:
        return None
    match = df[df["data_hash"] == content_hash]
    return None if match.empty else match.iloc[0].to_dict()


def _usable_verified(row: Optional[Dict[str, Any]]) -> bool:
    return bool(row) and bool(row.get("verified")) and not is_fallback(row.get("ai_analysis"))


def _promote_row(store: Any, row_id: str, content_hash: str) -> None:
    """新種入的列排到所有同 hash 列之前，find_by_hash（取第一筆）才會命中它。"""
    df = store.get_all_records()
    same = list(df.index[df["data_hash"] == content_hash])
    mine = list(df.index[df["id"] == row_id])
    if len(same) <= 1 or not mine or same[0] == mine[0]:
        return
    order = [i for i in df.index if i != mine[0]]
    order.insert(order.index(same[0]), mine[0])
    store._save_knowledge_base(df.loc[order].reset_index(drop=True))


def _set_vector(store: Any, row_id: str, vector: List[float]) -> None:
    df = store.get_all_records()
    idx = list(df.index[df["id"] == row_id])
    if not idx:
        return
    df["content_vector"] = df["content_vector"].astype(object)
    df.at[idx[0], "content_vector"] = list(vector)
    store._save_knowledge_base(df)


def _try_embed(embed: Optional[Callable[[str], List[float]]], text: str) -> List[float]:
    if embed is None:
        return []
    try:
        vector = embed(text)
    except Exception:
        return []
    return list(vector) if vector is not None and len(vector) else []


def prewarm(
    data_dir: Path,
    mentions_path: Path,
    seed_path: Path = SEED_PATH,
    embed: Optional[Callable[[str], List[float]]] = None,
) -> Dict[str, List[Dict[str, Any]]]:
    """離線預熱（T-11 第 4 點）。回傳 {"prewarmed": [...], "existing": [...], "missing": [...]}。"""
    from app.services.pandas_store import PandasStore
    from app.services.threads_sim import FakeThreadsService

    client = FakeThreadsService(mentions_path=mentions_path)
    # 預熱只是試算「poll 會查哪些內容」：m3 讀不到這類 threads_bot warning 留給真正的 poll 再印
    bot_logger = logging.getLogger("threads_bot")
    was_disabled, bot_logger.disabled = bot_logger.disabled, True
    try:
        targets = asyncio.run(_analysis_targets(client, data_dir))
    finally:
        bot_logger.disabled = was_disabled
    summary: Dict[str, List[Dict[str, Any]]] = {"prewarmed": [], "existing": [], "missing": []}
    if not targets:
        return summary

    seeds = load_seeds(seed_path)
    store = PandasStore(data_dir=str(data_dir))
    df = store.get_all_records()
    for label, text, input_type in targets:
        content_hash = CacheService.generate_hash(text)
        row = _first_hash_row(df, content_hash)
        if _usable_verified(row):
            vector_added = False
            # 先前斷網種入的 gold 列沒有向量：這次 embedding 可用就補上
            if row.get("label_source") == "gold" and row.get("content_vector") is None and embed is not None:
                vector = _try_embed(embed, text)
                if vector:
                    _set_vector(store, row["id"], vector)
                    df = store.get_all_records()
                    vector_added = True
            summary["existing"].append({"label": label, "row": row, "vector_added": vector_added})
            continue
        seed = seeds.get(content_hash)
        if seed is None:
            summary["missing"].append({"label": label, "text": text})
            continue
        vector = _try_embed(embed, text)
        record = store.save_record(
            data_type="URL" if input_type == "url" else "TEXT",
            raw_content=text,
            content_hash=content_hash,
            content_vector=vector or None,
            ai_result=seed["result"],
            source_url=text if input_type == "url" else None,
            label_source="gold",
            origin="threads_sim",
        )
        _promote_row(store, record["id"], content_hash)
        df = store.get_all_records()
        summary["prewarmed"].append({"label": label, "record": record, "vector": bool(vector)})
    return summary


def _tier_counts(sources: Any) -> Counter:
    counts: Counter = Counter()
    for s in sources or []:
        if not isinstance(s, dict):
            continue
        tier = s.get("tier")
        if tier not in (1, 2, 3):
            tier = tier_of(str(s.get("url") or ""), str(s.get("title") or ""), offline=True)
        if tier in (1, 2):
            counts[tier] += 1
    return counts


def sources_summary(sources: Any) -> str:
    if sources is None:
        return "sources: ?"
    counts = _tier_counts(sources)
    if not counts:
        return "sources: none"
    return "sources: " + ", ".join(f"{n} x tier{tier}" for tier, n in sorted(counts.items()))


def _report_prewarm(summary: Dict[str, List[Dict[str, Any]]], out: Out) -> None:
    out(f"[reset-sim] 離線預熱：已預熱 {len(summary['prewarmed'])} 則／已存在 {len(summary['existing'])} 則")
    for item in summary["prewarmed"]:
        rec = item["record"]
        label = frame_of({**rec["ai_analysis"], "verification_status": "rule"})[1]
        vec = "已寫入向量" if item["vector"] else "未寫入向量（embedding 未設定或連不上；hash 命中不受影響）"
        out(f"[reset-sim]   {item['label']}：已預熱（gold，{label}，{sources_summary(rec['sources'])}；{vec}）")
    for item in summary["existing"]:
        row = item["row"]
        extra = "，已補上向量" if item["vector_added"] else ""
        out(f"[reset-sim]   {item['label']}：已存在（知識庫已有已證實的同內容列，label_source={row.get('label_source')}{extra}）")
    for item in summary["missing"]:
        out(f"[reset-sim]   {item['label']}：沒有種子，poll 時會呼叫 AI"
            "（要離線重播：在 scripts/threads_sim_seed.json 加入逐字相同的 text）")


def reset_sim(
    data_dir: Optional[Path] = None,
    *,
    example_path: Path = EXAMPLE_MENTIONS,
    seed_path: Path = SEED_PATH,
    embed: Optional[Callable[[str], List[float]]] = None,
    out: Out = say,
) -> int:
    """sim 重播前的重設＋離線預熱（T-11 第 3、4 點）。
    回傳 0；輪詢正在進行中回 2、mentions.json 壞掉回 1（兩者都什麼都不改）。"""
    data_dir = Path(data_dir) if data_dir is not None else threads_state.DATA_DIR
    mentions_path = data_dir / "threads_sim" / "mentions.json"
    sim_replies = data_dir / "threads_sim" / "replies.jsonl"
    lock = threads_bot.lock_path(data_dir)

    status, detail = clear_stale_poll_lock(lock)
    if status == "busy":
        out(f"[reset-sim] 輪詢正在進行中（{detail}），請等這輪結束再重設")
        return 2
    if status == "removed":
        out(f"[reset-sim] 已移除殘留的 {_rel(lock)}（{detail}）")
    try:
        # reset 期間自己持有輪詢鎖：排程或 API 的輪詢會被擋下（409／略過），state 不會被舊資料蓋回
        token = threads_bot._acquire_file_lock(lock)
    except threads_bot.PollInProgress:
        out("[reset-sim] 輪詢剛好開始，請等這輪結束再重設")
        return 2
    try:
        if ensure_mentions(mentions_path, example_path):
            out(f"[reset-sim] {_rel(mentions_path)} 不存在，已從 scripts/{example_path.name} 複製")
        if strip_utf8_bom(mentions_path):
            out(f"[reset-sim] {_rel(mentions_path)} 開頭有 UTF-8 BOM（後端會讀不到任何 mention），已移除")
        problem = check_mentions_file(mentions_path)
        if problem:
            out(f"[reset-sim] {_rel(mentions_path)} {problem}；未做任何變更，修好後再執行"
                f"（或刪掉它，下次會從 scripts/{example_path.name} 重新複製）")
            return 1
        sim_ids = _mention_ids_in_file(mentions_path)

        n_lines, ids = truncate_sim_replies(sim_replies)
        sim_ids |= ids
        out(f"[reset-sim] 已清空 {_rel(sim_replies)}（原 {n_lines} 行）")

        removed, kept, ids = drop_sim_reply_records(data_dir)
        sim_ids |= ids
        out(f"[reset-sim] {_rel(threads_state.replies_path(data_dir))}：移除 mode=sim {removed} 行，保留其他 {kept} 行")

        dropped, kept_ids = reset_state(data_dir, sim_ids)
        out(f"[reset-sim] state：replied_ids 移除模擬 id {dropped} 個（保留 {kept_ids} 個），last_since 歸零")

        summary = prewarm(data_dir, mentions_path, seed_path, embed=embed)
    finally:
        threads_bot._release_file_lock(lock, token)

    _report_prewarm(summary, out)
    mode = settings.threads_mode_effective
    if mode != "sim":
        out(f"[reset-sim] 注意：.env 的 THREADS_MODE={mode}，後端不會讀模擬檔；請設 THREADS_MODE=sim 並重啟後端")
    else:
        out(f"[reset-sim] 完成。後端排程每 {settings.THREADS_POLL_MINUTES} 分鐘也會自動輪詢，"
            "請在那之前執行 --poll（錄影時可把 THREADS_POLL_MINUTES 調大）")
    return 0


def _default_embedder() -> Optional[Callable[[str], List[float]]]:
    """embedding 有設定才回傳（best effort；失敗時 _try_embed 回空、只寫 hash）。"""
    if not ((settings.EMBED_RELAY_URL or "").strip() and (settings.EMBED_API_KEY or settings.CGU_API_KEY or "").strip()):
        return None
    from app.services.vector_service import VectorService

    return VectorService().vectorize_content


# ══════════════════════════════════════════════════════════════════
# --poll
# ══════════════════════════════════════════════════════════════════
class BackendDown(Exception):
    """--api 連不上（後端沒開）。"""


def _call(http: Any, method: str, url: str, **kwargs) -> Tuple[int, Any]:
    try:
        resp = getattr(http, method)(url, timeout=HTTP_TIMEOUT_SECONDS, **kwargs)
    except requests.ConnectionError as e:
        raise BackendDown(str(e)) from None
    try:
        body = resp.json()
    except ValueError:
        body = None
    return resp.status_code, body


def _reply_key(rec: Dict[str, Any]) -> Tuple[Any, Any]:
    return rec.get("mention_id"), rec.get("reply_id")


def _new_records(records_newest_first: List[Dict[str, Any]], before: Set[Tuple[Any, Any]]) -> List[Dict[str, Any]]:
    """本輪新增的回覆（時間順：舊 → 新）。"""
    return [r for r in reversed(records_newest_first) if _reply_key(r) not in before]


def _fixed_kind(reply_text: Any) -> str:
    fixed = {reply_media_only(): "media_only", reply_cannot_read(): "unreadable", reply_too_short(): "too_short"}
    return fixed.get(str(reply_text or ""), "no AI")


def describe_reply(rec: Dict[str, Any], result: Optional[Dict[str, Any]] = None) -> str:
    """demo 終端機格式：poll -> mention m1 -> cache hash -> sources: 1 x tier1 -> reply sim_reply_1"""
    steps = ["poll", f"mention {rec.get('mention_id')}"]
    if rec.get("result_id"):
        if isinstance(result, dict):
            layer = result.get("cache_layer")
            steps.append(f"cache {layer}" if layer else "cache miss -> AI")
            steps.append(sources_summary(result.get("sources") or []))
        else:
            steps.extend(["cache ?", "sources: ?"])
    else:
        steps.append(f"fixed reply ({_fixed_kind(rec.get('reply_text'))})")
    steps.append(f"reply {rec.get('reply_id')}")
    return " -> ".join(steps)


def _report_poll(
    stats: Dict[str, Any],
    last_error: Optional[str],
    new_records: List[Dict[str, Any]],
    lookup: Callable[[str], Optional[Dict[str, Any]]],
    mode: Optional[str],
    out: Out,
) -> int:
    out("[poll] 本輪結果：" + " ".join(f"{k}={int((stats or {}).get(k) or 0)}" for k in STAT_KEYS))
    if last_error:
        out(f"[poll] last_error={last_error}")
    results: Dict[str, Optional[Dict[str, Any]]] = {}
    for rec in new_records:
        rid = rec.get("result_id")
        if rid and rid not in results:
            results[rid] = lookup(rid)
        out(describe_reply(rec, results.get(rid) if rid else None))
        if rid:
            out(f"       result_id={rid} frame_type={rec.get('frame_type')}")
    if new_records:
        # 最新一筆「判定回覆」（固定文案沒有 result／cache_layer）；本輪都是固定文案才退回最新一筆
        verdicts = [r for r in new_records if r.get("result_id")]
        latest = verdicts[-1] if verdicts else new_records[-1]
        rid = latest.get("result_id")
        layer = (results.get(rid) or {}).get("cache_layer") if rid else None
        label = "最新判定回覆" if rid else "最新回覆"
        out(f"[poll] {label}：result_id={rid} frame_type={latest.get('frame_type')} cache_layer={layer}")
        if mode == "sim":
            out("[poll] 回覆全文：data/threads_sim/replies.jsonl")
    else:
        out("[poll] 本輪沒有新回覆")
    out(f"[poll] replied={int((stats or {}).get('replied') or 0)}")
    return 0


def _report_not_started(code: int, body: Any, out: Out) -> int:
    body = body if isinstance(body, dict) else {}
    err = body.get("code")
    if code == 409 or err == "poll_in_progress":
        msg = "另一輪輪詢正在進行中（poll_in_progress），請等幾秒再試"
    elif code == 401:
        msg = "X-Admin-Token 與後端不符（unauthorized）：改過 .env 的 ADMIN_TOKEN 要重啟後端"
    elif code == 403:
        msg = "後端沒有設定 ADMIN_TOKEN（admin_disabled）：執行 start.bat 或 scripts\\ensure_admin_token.py 後重啟後端"
    elif err == "threads_disabled":
        msg = "後端 THREADS_MODE=off（threads_disabled）：在 .env 設 THREADS_MODE=sim 後重啟後端"
    elif err in ("threads_not_configured", "token_invalid"):
        msg = f"後端無法輪詢（{err}）：{body.get('detail') or ''}"
    else:
        msg = f"後端回 HTTP {code}（{err or body.get('detail') or ''}）"
    out(f"[poll] 沒有開始：{msg}")
    return 1


def poll_via_api(
    api: str,
    token: str,
    *,
    http: Any = requests,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
    timeout: float = POLL_TIMEOUT_SECONDS,
    interval: float = POLL_INTERVAL_SECONDS,
    out: Out = say,
) -> int:
    """POST /api/threads/poll → 輪詢 status.last_poll_at。第一個請求就連不上時丟 BackendDown（呼叫端改在本程序內跑）。"""
    base = api.rstrip("/")
    code, status = _call(http, "get", f"{base}/api/threads/status")
    try:
        if code != 200 or not isinstance(status, dict):
            out(f"[poll] 讀取 {base}/api/threads/status 失敗（HTTP {code}）")
            return 1
        mode = status.get("mode")
        before_poll_at = status.get("last_poll_at")
        _, replies = _call(http, "get", f"{base}/api/threads/replies", params={"limit": REPLIES_WINDOW})
        before = {_reply_key(r) for r in (replies or {}).get("records") or []}
        if not token:
            out("[poll] .env 沒有 ADMIN_TOKEN，無法觸發輪詢（start.bat 會自動產生；或執行 scripts\\ensure_admin_token.py 後重啟後端）")
            return 1

        out(f"[poll] 觸發一輪輪詢：{base}（THREADS_MODE={mode}）")
        code, body = _call(http, "post", f"{base}/api/threads/poll", headers={"X-Admin-Token": token})
        if code != 202:
            return _report_not_started(code, body, out)
        out(f"[poll] 202 已開始，每 {interval:g} 秒檢查 last_poll_at ...")

        deadline = clock() + timeout
        while True:
            code, status = _call(http, "get", f"{base}/api/threads/status")
            if code == 200 and isinstance(status, dict):
                if status.get("last_poll_at") != before_poll_at:
                    break
                backoff = _to_epoch(status.get("backoff_until"))
                if backoff is not None and backoff > time.time():
                    out(f"[poll] 輪詢暫停中（backoff_until={status.get('backoff_until')}），這輪不會執行")
                    return 1
            if clock() >= deadline:
                out(f"[poll] 等待逾時（{int(timeout)} 秒）：last_poll_at 沒有更新，請看後端視窗的 log")
                return 1
            sleep(interval)

        _, replies = _call(http, "get", f"{base}/api/threads/replies", params={"limit": REPLIES_WINDOW})
        new = _new_records((replies or {}).get("records") or [], before)

        def lookup(result_id: str) -> Optional[Dict[str, Any]]:
            rc, payload = _call(http, "get", f"{base}/api/result/{result_id}")
            return payload.get("result") if rc == 200 and isinstance(payload, dict) else None

        return _report_poll(status.get("last_poll_stats") or {}, status.get("last_error"), new, lookup, mode, out)
    except BackendDown as e:
        out(f"[poll] 後端連線中斷：{e}")
        return 1


def _task_result(store: Any, result_id: str) -> Optional[Dict[str, Any]]:
    task = store.get_task(result_id)
    try:
        data = json.loads((task or {}).get("result_data") or "")
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def poll_in_process(*, out: Out = say) -> int:
    """後端沒開時：在本程序內直接跑一輪（與後端共用檔案鎖，不會兩輪同時跑）。"""
    from app.services.task_store import TaskStore

    mode = settings.threads_mode_effective
    before = {_reply_key(r) for r in threads_state.read_reply_records(REPLIES_WINDOW)}
    out(f"[poll] 在本程序內直接跑一輪（THREADS_MODE={mode}）")
    try:
        res = asyncio.run(threads_bot.run_threads_poll())
    except threads_bot.PollInProgress:
        out("[poll] 沒有開始：另一輪輪詢正在進行中（poll_in_progress），請等幾秒再試")
        return 1
    if not res.get("started"):
        reason = res.get("reason") or res.get("skipped") or "unknown"
        hint = "：在 .env 設 THREADS_MODE=sim" if reason == "threads_disabled" else ""
        out(f"[poll] 沒有開始：{reason}{hint}")
        return 1
    state = threads_state.load_state()
    new = _new_records(threads_state.read_reply_records(REPLIES_WINDOW), before)
    store = TaskStore()
    return _report_poll(res, state.get("last_error"), new, lambda rid: _task_result(store, rid), mode, out)


def run_poll(api: str = DEFAULT_API, *, http: Any = requests, timeout: float = POLL_TIMEOUT_SECONDS,
             sleep: Callable[[float], None] = time.sleep, out: Out = say) -> int:
    token = (settings.ADMIN_TOKEN or "").strip()   # 只放進標頭，不印出
    try:
        return poll_via_api(api, token, http=http, timeout=timeout, sleep=sleep, out=out)
    except BackendDown:
        out(f"[poll] 後端未啟動（{api} 連不上），改在本程序內直接跑一輪")
        return poll_in_process(out=out)


# ══════════════════════════════════════════════════════════════════
def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Threads 查核機器人：乾跑／--live／--reset-sim／--poll")
    ap.add_argument("--live", action="store_true", help="用真 token 驗證憑證並讀 mentions 筆數")
    ap.add_argument("--reset-sim", action="store_true",
                    help="sim 重播：清模擬回覆紀錄與輪詢游標、移除殘留鎖、離線預熱快取")
    ap.add_argument("--poll", action="store_true",
                    help="觸發一輪輪詢並印出結果（後端未啟動時在本程序內跑；live 模式會真的回覆）")
    ap.add_argument("--api", default=DEFAULT_API, help=f"後端網址（預設 {DEFAULT_API}）")
    ap.add_argument("--workdir", default=None, help="進階：後端工作目錄（.env 與 data/ 所在，預設 code/backend）")
    ap.add_argument("--timeout", type=float, default=POLL_TIMEOUT_SECONDS, help=argparse.SUPPRESS)
    args = ap.parse_args(argv)

    if args.reset_sim:
        rc = reset_sim(embed=_default_embedder())
        if rc != 0 or not args.poll:
            return rc
    if args.poll:
        return run_poll(args.api, timeout=args.timeout)
    rc = dry_run()
    if args.live:
        rc = live_check() or rc
    return rc


if __name__ == "__main__":
    sys.exit(main())
