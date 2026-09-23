"""
證據信心（夾角）：信心等級依「判定與查核機構已證實內容的相似度」決定，不用 AI 自評分數。

規則、門檻與依據寫在 docs/rebuild/信心程度的產生方式.md（實測：docs/test/results/evidence_confidence_2026-09-24.md）。
判斷順序（先符合者為準）：

  1. AI 服務暫時無法使用                                   → 低  ai_unavailable（前端不顯示信心）
  2. 結果來自確定性標記（rule／gold／admin；查核機構或人工）  → 高  factchecked
  3. 判定有風險＋最接近的已證實不實內容相似度 ≥ 0.65          → 中  similar_case
  4. 判定有風險＋話術差距 ≥ 0.10                             → 中  pattern
  5. 判定有風險＋AI 引用了 Tier 1／2 來源                     → 中  cited_source
  6. 判定為安全，但規則 3 或 4 的條件成立（衝突）              → 低  conflict
  7. 判定為安全＋有 Tier 1／2 來源                            → 中  safe_source
  8. 無法查證                                               → 低  unverifiable
  9. 其他                                                   → 低  ai_only

相似度一律是 cosine（text-embedding-3-small）；夾角 = arccos(相似度)。
「話術差距」= 與最接近的話術原型（已證實的不實內容分群）的相似度 − 與最接近的正常訊息原型的相似度，
原型由 scripts/evidence_confidence_study.py 產生、存在 data/claim_prototypes.npz。
"""
import logging
import math
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import numpy as np

from app.services.pandas_store import DETERMINISTIC_LABEL_SOURCES
from app.utils.source_tier import _host_matches, _host_of
from app.utils.verdict import frame_of

logger = logging.getLogger(__name__)

MID_SIMILARITY = 0.65        # 規則 3／6：評測題庫中 ≥0.65 的 30 題有 27 題真的有風險
PATTERN_MARGIN = 0.10        # 規則 4／6：話術差距 ≥0.10 的 29 題有 27 題真的有風險
EVIDENCE_NEIGHBOURS = 5      # 查幾筆最近的已證實列
SIMILAR_NEWS_MIN = 0.60      # 「知識庫中的相似查證」列出的下限（spec FR-02）
SIMILAR_NEWS_MAX = 3
RISK_TYPES = frozenset({"SCAM", "MISINFO"})
PROTOTYPES_PATH = Path(__file__).resolve().parents[2] / "data" / "claim_prototypes.npz"
# 「知識庫中的相似查證」顯示的機構名稱（其他網域顯示主機名稱）
SOURCE_NAMES = (
    (("mygopen.com",), "MyGoPen"),
    (("tfc-taiwan.org.tw",), "台灣事實查核中心"),
    (("cofacts.tw", "cofacts.g0v.tw"), "Cofacts"),
    (("gov.tw",), "政府機關"),
)

LEVEL_OF_BASIS = {
    "ai_unavailable": "低",
    "factchecked": "高",
    "similar_case": "中",
    "pattern": "中",
    "cited_source": "中",
    "conflict": "低",
    "safe_source": "中",
    "unverifiable": "低",
    "ai_only": "低",
}

# API 的 confidence_note（Threads 回覆與 API 使用者讀這段）；網站畫面的文字在前端 i18n.js（confidence_basis_*）
NOTE_OF_BASIS = {
    "ai_unavailable": "AI 服務暫時無法使用",
    "factchecked": "查核機構已查證過同一則訊息",
    "similar_case": "相近的已查核案例支持此判定",
    "pattern": "寫法符合已知的詐騙或謠言話術",
    "cited_source": "AI 引用了查核機構的資料",
    "conflict": "與已查核的不實訊息相近，請小心",
    "safe_source": "有查核機構或官方資料佐證",
    "unverifiable": "無法取得內容，無從判斷",
    "ai_only": "只有 AI 判斷，沒有相近的查核案例",
}


def degrees(similarity: Optional[float]) -> Optional[float]:
    if similarity is None:
        return None
    return round(math.degrees(math.acos(max(-1.0, min(1.0, float(similarity))))), 1)


@lru_cache(maxsize=1)
def _prototypes() -> Optional[Tuple[np.ndarray, np.ndarray]]:
    """（話術原型, 正常訊息原型）單位向量矩陣；檔案不存在或壞掉 → None（規則 4／6 的話術條件不成立）。"""
    try:
        with np.load(PROTOTYPES_PATH) as data:
            return data["risk"].astype(np.float32), data["safe"].astype(np.float32)
    except Exception as exc:  # 缺檔不影響判讀，只少一個證據來源
        logger.warning("claim prototypes unavailable: %s", exc)
        return None


def pattern_margin(vector: Optional[Iterable[float]]) -> Optional[float]:
    """話術差距；沒有向量、維度不符或原型不可用 → None。"""
    protos = _prototypes()
    if protos is None or vector is None:
        return None
    q = np.asarray(list(vector), dtype=np.float32)
    risk, safe = protos
    norm = float(np.linalg.norm(q))
    if q.shape != (risk.shape[1],) or norm == 0:
        return None
    q = q / norm
    return round(float((risk @ q).max() - (safe @ q).max()), 4)


def source_name(url: Optional[str]) -> str:
    """查核來源網址 → 機構名稱（網域精確尾綴比對，與 source_tier 相同）；沒有網址 → 知識庫。"""
    host = _host_of(url or "")
    if not host:
        return "知識庫"
    for domains, name in SOURCE_NAMES:
        if _host_matches(host, domains):
            return name
    return host[4:] if host.startswith("www.") else host


def _nearest_risky(neighbours: Optional[List[Dict[str, Any]]]) -> Optional[Dict[str, Any]]:
    best = None
    for n in neighbours or []:
        if str(n.get("risk_type") or "").upper() in RISK_TYPES:
            if best is None or float(n.get("similarity") or 0) > float(best.get("similarity") or 0):
                best = n
    return best


def assess(
    risk_type: str,
    *,
    ai_unavailable: bool = False,
    label_source: str = "ai",
    verification_status: str = "unverified",
    neighbours: Optional[List[Dict[str, Any]]] = None,
    margin: Optional[float] = None,
) -> Dict[str, Any]:
    """依模組開頭的規則表決定信心。回傳 {level, basis, note, nearest_similarity, nearest_degrees, pattern_margin}。"""
    risk = str(risk_type or "").upper()
    nearest = _nearest_risky(neighbours)
    near_sim = float(nearest["similarity"]) if nearest else None
    close_case = near_sim is not None and near_sim >= MID_SIMILARITY
    known_pattern = margin is not None and margin >= PATTERN_MARGIN
    has_source = verification_status in ("verified", "rule")

    if ai_unavailable:
        basis = "ai_unavailable"
    elif label_source in DETERMINISTIC_LABEL_SOURCES:
        basis = "factchecked"
    elif risk in RISK_TYPES:
        basis = ("similar_case" if close_case else "pattern" if known_pattern
                 else "cited_source" if has_source else "ai_only")
    elif risk == "SAFE":
        basis = "conflict" if (close_case or known_pattern) else "safe_source" if has_source else "ai_only"
    elif risk == "UNVERIFIABLE":
        basis = "unverifiable"
    else:
        basis = "ai_only"
    return {
        "level": LEVEL_OF_BASIS[basis],
        "basis": basis,
        "note": NOTE_OF_BASIS[basis],
        "nearest_similarity": round(near_sim, 4) if near_sim is not None else None,
        "nearest_degrees": degrees(near_sim),
        "pattern_margin": margin,
    }


def similar_news(neighbours: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """
    「知識庫中的相似查證」（spec FR-02 similar_news）：相似度 ≥ SIMILAR_NEWS_MIN 的已證實列，最多 3 筆。
    url 連到該列的 Tier 1／2 查核來源（查核機構原文）；沒有則為 None。
    """
    items = []
    for n in neighbours or []:
        similarity = float(n.get("similarity") or 0)
        if similarity < SIMILAR_NEWS_MIN:
            continue
        sources = n.get("sources") or []
        url = next((s.get("url") for s in sources if isinstance(s, dict) and s.get("tier") in (1, 2) and s.get("url")),
                   None)
        text = str(n.get("raw_content") or "").strip().replace("\n", " ")
        risk_type = str(n.get("risk_type") or "").upper() or None
        # 近鄰都是已證實列：燈號照 frame_of 的規則算（前端只讀 frame_type，不自行由 risk_type 推顏色）
        frame_type, frame_label, _ = frame_of({
            "risk_type": risk_type, "is_risk": risk_type in RISK_TYPES,
            "verification_status": "verified", "confidence_score": 1.0,
        })
        items.append({
            "title": text[:60] + ("…" if len(text) > 60 else ""),
            "url": url,
            "source": source_name(url),
            "risk_type": risk_type,
            "frame_type": frame_type,
            "frame_label": frame_label,
            "similarity": round(similarity, 4),
            "degrees": degrees(similarity),
            "kb_id": n.get("id"),
        })
        if len(items) >= SIMILAR_NEWS_MAX:
            break
    return items
