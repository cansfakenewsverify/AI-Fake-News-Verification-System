"""
查核結論同步（spec FR-23）：把查核機構新發布的判定寫進知識庫（label_source=rule、origin=factcheck_batch），
收錄規則與批次入庫相同（factcheck_corpus）。只呼叫 embedding，不呼叫判讀模型。

- mode="recent"（每天兩次）：MyGoPen 最新 150 篇、台灣事實查核中心最新 100 篇報告與 300 則謠言原文、
  Cofacts 最近有新回覆的 300 則已判定訊息。一次約十幾個請求，embedding 只算新文字（通常 < USD 0.001）。
- mode="full"（每週一次）：三個來源全部掃過，範圍與 scripts/ingest_factchecks.py fetch 相同；第一次執行就是完整回填
  （約 1.8 萬筆、embedding 約 USD 0.25，約 30～40 分鐘）。知識庫還沒有任何 origin=factcheck_batch 列時，
  recent 會自動改跑 full（STATUS 的 upgraded_from 記 "recent"），所以不必另外手動回填。Cofacts 新文章要累積到 3 人回報才收，recent 模式只看最近有新回覆者，
  所以後來才達標的文章靠每週 full 補上。
- 只寫入知識庫還沒有的文字（existing_hashes：已證實列或 origin=factcheck_batch 的列），可重跑；每 256 筆寫一次，
  中途被中斷（例如免費主機重啟）時下次從剩下的繼續。
- 同一時間只跑一個（行程內鎖）。狀態 STATUS 給 GET /api/admin/factcheck-sync 讀；GitHub Actions 的 factcheck-sync
  輪詢它，順便讓 Render 免費主機在同步期間保持清醒（沒有流量 15 分鐘會休眠）。
- 每次執行先讀 CGU 閘道的模型清單（GET /models，不花額度）：CGU_MODEL、CGU_FALLBACK_MODEL、EMBED_MODEL 有任何一個
  不在清單上就記在 STATUS["model_check"]["missing"]，workflow 會標為失敗並寄信（2026-09-30 閘道無預警下架 gpt-5.4-mini，
  網站的新內容判讀全部變成 fallback，沒有人發現）。
- 三個來源依序處理，原始回應轉成語料列後就釋放（免費主機只有 512 MB 記憶體）。某個來源抓取失敗時照樣寫入其他來源，
  錯誤記在 STATUS["source_errors"]（workflow 看到它就標為失敗，GitHub 會寄信通知）；三個都失敗才算整輪失敗。
"""
import logging
import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.config import settings
from app.services import factcheck_corpus as fc
from app.services.store_factory import get_knowledge_store

logger = logging.getLogger(__name__)

MODES = ("recent", "full")
WRITE_CHUNK = 256
RECENT = {"mygopen_pages": 1, "tfc_report_pages": 1, "tfc_rumor_pages": 3, "cofacts_limit": 300}
FULL = {"cofacts_limit": 9000}
COFACTS_MIN_REQUESTS = fc.COFACTS_MIN_REQUESTS

_lock = threading.Lock()
STATUS: Dict[str, Any] = {
    "state": "idle", "mode": None, "phase": None, "started_at": None, "finished_at": None,
    "candidates": 0, "already_present": 0, "to_write": 0, "written": 0, "tokens": 0,
    "written_by_source": {}, "skipped": {}, "source_errors": {}, "upgraded_from": None, "model_check": None,
    "error": None,
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def model_check() -> Dict[str, Any]:
    """設定的模型是否都還在 CGU 閘道上：{checked, missing}。讀不到清單時 checked=False（不當成下架）。"""
    from app.services.ai_service import gateway_models

    models = gateway_models()
    if models is None:
        return {"checked": False, "missing": []}
    wanted = [settings.CGU_MODEL, settings.CGU_FALLBACK_MODEL]
    if (settings.EMBED_RELAY_URL or "").rstrip("/") == (settings.CGU_BASE_URL or "").rstrip("/"):
        wanted.append(settings.EMBED_MODEL)
    return {"checked": True, "missing": [m for m in wanted if m and m not in models]}


def is_running() -> bool:
    return _lock.locked()


def status() -> Dict[str, Any]:
    return {**STATUS, "written_by_source": dict(STATUS["written_by_source"]), "skipped": dict(STATUS["skipped"]),
            "source_errors": dict(STATUS["source_errors"])}


def _mygopen(mode: str, skipped: dict) -> List[dict]:
    pages = None if mode == "full" else RECENT["mygopen_pages"]
    return fc.mygopen_rows(fc.mygopen_entries(max_pages=pages), skipped)


def _tfc(mode: str, skipped: dict) -> List[dict]:
    if mode == "full":
        return fc.tfc_rows(skipped=skipped)
    return fc.tfc_rows(report_pages=RECENT["tfc_report_pages"], rumor_pages=RECENT["tfc_rumor_pages"], skipped=skipped)


def _cofacts(mode: str, skipped: dict) -> List[dict]:
    if mode == "full":
        nodes = fc.cofacts_nodes("RUMOR", COFACTS_MIN_REQUESTS, FULL["cofacts_limit"])
    else:
        nodes = fc.cofacts_nodes("RUMOR", COFACTS_MIN_REQUESTS, RECENT["cofacts_limit"], order="replied")
    return fc.cofacts_rows(nodes, "RUMOR", skipped)


SOURCES = (("MyGoPen", _mygopen), ("TFC", _tfc), ("Cofacts", _cofacts))


def collect(mode: str) -> Tuple[List[dict], dict, dict]:
    """
    三個來源依序抓取、轉成語料列並去重（原始回應在各函式結束時釋放）。
    → (可入庫列, 略過原因統計, 抓取失敗的來源 {名稱: 錯誤})。三個來源都失敗時丟 RuntimeError。
    """
    skipped: dict = {}
    errors: dict = {}
    rows: List[dict] = []
    for name, fetch in SOURCES:
        STATUS["phase"] = f"fetch:{name}"
        try:
            rows.extend(fetch(mode, skipped))
        except Exception as exc:
            logger.exception("fact-check sync: %s fetch failed", name)
            errors[name] = f"{type(exc).__name__}: {exc}"[:200]
    if len(errors) == len(SOURCES):
        raise RuntimeError("all sources failed: " + "; ".join(f"{k} {v}" for k, v in errors.items()))
    kept = [r for r in fc.dedupe_rows(rows, skipped) if r["use"] == "kb"]
    return kept, skipped, errors


def _reset(mode: str) -> None:
    STATUS.update(state="queued", mode=mode, phase=None, started_at=_now(), finished_at=None,
                  candidates=0, already_present=0, to_write=0, written=0, tokens=0,
                  written_by_source={}, skipped={}, source_errors={}, upgraded_from=None, model_check=None,
                  error=None)


def try_start(mode: str, background_tasks: Optional[Any] = None) -> bool:
    """
    在請求當下取得鎖並排入背景（BackgroundTasks 或執行緒）；已有一輪在跑回 False。
    鎖在這裡就取得，所以兩個同時到的請求只有一個會開始，狀態也立刻變成 queued（輪詢端不會讀到上一輪的 done）。
    """
    if mode not in MODES:
        raise ValueError(f"unknown mode {mode!r}")
    if not _lock.acquire(blocking=False):
        return False
    _reset(mode)
    if background_tasks is not None:
        background_tasks.add_task(_run_locked, mode)
    else:
        threading.Thread(target=_run_locked, args=(mode,), daemon=True).start()
    return True


def run_sync(mode: str = "recent", store: Any = None) -> Dict[str, Any]:
    """同步一次並等它做完（測試與腳本用）。已有一輪在跑時直接回傳目前狀態，不重複執行。"""
    if mode not in MODES:
        raise ValueError(f"unknown mode {mode!r}")
    if not _lock.acquire(blocking=False):
        return status()
    _reset(mode)
    return _run_locked(mode, store)


def _run_locked(mode: str, store: Any = None) -> Dict[str, Any]:
    """呼叫前必須已持有 _lock；結束時釋放。"""
    try:
        STATUS.update(state="running", phase="model_check", model_check=model_check())
        STATUS["phase"] = "fetch"
        store = store or get_knowledge_store()
        if mode == "recent" and store.verified_origin_count(fc.ORIGIN) == 0:
            # 知識庫還沒有查核機構資料：第一次同步就完整回填
            mode = "full"
            STATUS.update(mode="full", upgraded_from="recent")
        rows, skipped, errors = collect(mode)
        STATUS["source_errors"] = errors
        present = store.existing_hashes([r["content_hash"] for r in rows], origin=fc.ORIGIN)
        todo = sorted((r for r in rows if r["content_hash"] not in present), key=lambda r: str(r.get("published") or ""))
        STATUS.update(phase="write", candidates=len(rows), already_present=len(rows) - len(todo),
                      to_write=len(todo), skipped=skipped)
        # created_at 依查核文章發布日由舊到新遞增：知識庫頁「新到舊」會先列出最新的查核結論
        start = datetime.now()
        for offset in range(0, len(todo), WRITE_CHUNK):
            chunk = todo[offset:offset + WRITE_CHUNK]
            vectors: List[Any] = []
            for b in range(0, len(chunk), fc.EMBED_BATCH):
                got, used = fc.embed_batch([r["text"] for r in chunk[b:b + fc.EMBED_BATCH]])
                vectors.extend(got)
                STATUS["tokens"] += used
            pairs = [(offset + i, r, v) for i, (r, v) in enumerate(zip(chunk, vectors)) if v is not None]
            STATUS["written"] += store.save_records(
                fc.kb_item(r, v, start + timedelta(microseconds=n)) for n, r, v in pairs)
            for _, r, _ in pairs:
                STATUS["written_by_source"][r["source"]] = STATUS["written_by_source"].get(r["source"], 0) + 1
        STATUS.update(state="done", phase=None, finished_at=_now())
        logger.info("fact-check sync %s done: %d candidates, %d written, %d tokens",
                    mode, STATUS["candidates"], STATUS["written"], STATUS["tokens"])
    except Exception as exc:
        logger.exception("fact-check sync %s failed", mode)
        STATUS.update(state="failed", phase=None, finished_at=_now(), error=f"{type(exc).__name__}: {exc}"[:300])
    finally:
        _lock.release()
    return status()
