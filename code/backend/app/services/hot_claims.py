"""
熱門查證排行：最近大家在查什麼（/api/knowledge/hot）。

原始資料是查證紀錄（tasks）：每一次查證只要對應到知識庫的某一列——快取命中或新寫入——
就算那一列的一次需求。換句話說的同一則謠言經由向量層命中同一列，所以會算在一起。

分數採時間衰減：每次查證的權重是 0.5 ^ (距今小時數 ÷ 半衰期)。
半衰期 3 小時：剛發生的查證算 1 次、3 小時前算 0.5 次、6 小時前算 0.25 次……
「最近突然很多人問」會排到前面，舊的熱度自然退場；流量小的時候，
視窗（7 天）內的查證仍會依遠近排出先後，不會整面空白。

這裡只排序、不過濾：公開頁只顯示已證實的列（由呼叫端 api/knowledge.py 決定）。
之後提供查核機構的熱搜名單（含尚未證實的列）沿用同一套分數。
"""
from datetime import datetime
from typing import Any, Dict, Iterable, List

HALF_LIFE_HOURS = 3.0
WINDOW_DAYS = 7


def rank(
    refs: Iterable[Dict[str, Any]],
    now: datetime,
    half_life_hours: float = HALF_LIFE_HOURS,
    window_days: int = WINDOW_DAYS,
) -> List[Dict[str, Any]]:
    """
    refs：[{kb_id, created_at}]（created_at 與 now 同為不帶時區的 UTC）。
    回傳每個 kb_id 一筆 {kb_id, score, count_24h, count_window, last_seen}，
    依 score 由高到低；同分時較近查證者在前，再依 kb_id 固定順序。
    視窗外、缺 kb_id 或時間的紀錄略過；未來時間視為剛發生。
    """
    window_hours = window_days * 24
    stats: Dict[str, Dict[str, Any]] = {}
    for ref in refs:
        kb_id = str(ref.get("kb_id") or "").strip()
        created = ref.get("created_at")
        if not kb_id or not isinstance(created, datetime):
            continue
        age_hours = max((now - created).total_seconds() / 3600.0, 0.0)
        if age_hours > window_hours:
            continue
        item = stats.setdefault(kb_id, {
            "kb_id": kb_id, "score": 0.0, "count_24h": 0, "count_window": 0, "last_seen": created,
        })
        item["score"] += 0.5 ** (age_hours / half_life_hours)
        item["count_window"] += 1
        if age_hours <= 24:
            item["count_24h"] += 1
        if created > item["last_seen"]:
            item["last_seen"] = created

    for item in stats.values():
        item["score"] = round(item["score"], 6)
    return sorted(
        stats.values(),
        key=lambda s: (-s["score"], (now - s["last_seen"]).total_seconds(), s["kb_id"]),
    )
