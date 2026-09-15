"""
紅黃綠判定映射（spec §7.8，單一權威；Web 與 Threads 共用）。

前端與 Threads 回覆一律只讀 frame_type / frame_label，不自行由 risk_type 推燈色。
判斷依序（先符合者勝）：
  1. ai_unavailable                               -> grey   「AI 暫時無法使用」
  2. risk_type == UNVERIFIABLE                    -> yellow 「無法查證」
  3. is_risk and risk_type == SCAM                -> red    「詐騙警告」
  4. is_risk and risk_type == MISINFO             -> red    「假訊息」
  5. is_risk（其他）                               -> red    「風險訊息」
  6. SAFE and verification_status == unverified   -> yellow 「尚無查核機構證實」
  7. SAFE and confidence >= GREEN_MIN_CONFIDENCE  -> green  「查無異常」（且已證實）
  8. 其餘（低信心 SAFE、UNKNOWN）                  -> yellow 「尚待確認」

verification_status 只有 "verified" / "rule" 算已證實；缺鍵或任何其他值
（"Unverified"、"pending"、拼錯）一律視為 "unverified"（保守：沒有證據就不給綠燈）。
"""
from typing import Any, Dict, Optional, Tuple

# 綠燈信心門檻（spec 第 13 節 D-6：門檻集中在此一處可調）
GREEN_MIN_CONFIDENCE = 0.7

# 視為「已證實」的 verification_status（spec §7.8 合法值：verified / rule / unverified）
VERIFIED_STATUSES = ("verified", "rule")

LIGHT_RED = "\U0001F534"     # 紅圓
LIGHT_YELLOW = "\U0001F7E1"  # 黃圓
LIGHT_GREEN = "\U0001F7E2"   # 綠圓

LABEL_AI_UNAVAILABLE = "AI 暫時無法使用"
LABEL_UNVERIFIABLE = "無法查證"
LABEL_SCAM = "詐騙警告"
LABEL_MISINFO = "假訊息"
LABEL_RISK = "風險訊息"
LABEL_NO_VERIFIED_SOURCE = "尚無查核機構證實"
LABEL_SAFE = "查無異常"
LABEL_PENDING = "尚待確認"


def is_fallback(result: Any) -> bool:
    """判斷是否為 AI 失敗的 fallback 結果（不可快取、不可當成有效判定）。

    任一成立即為 True：非 dict、ai_unavailable is True、
    summary 以「AI 分析暫時無法使用」開頭、summary 含「服務異常」。
    """
    if not isinstance(result, dict):
        return True
    if result.get("ai_unavailable") is True:
        return True
    summary = str(result.get("summary") or "")
    return summary.startswith("AI 分析暫時無法使用") or "服務異常" in summary


def _confidence(result: Dict[str, Any]) -> float:
    raw = result.get("confidence_score", result.get("confidence", 0))
    try:
        return float(raw or 0)
    except (TypeError, ValueError):
        return 0.0


def frame_of(result: Any) -> Tuple[str, str, Optional[str]]:
    """回傳 (frame_type, frame_label, light)；grey 的 light 為 None。"""
    if not isinstance(result, dict):
        return "grey", LABEL_AI_UNAVAILABLE, None

    if result.get("ai_unavailable") is True:
        return "grey", LABEL_AI_UNAVAILABLE, None

    risk_type = str(result.get("risk_type") or "").upper()
    if risk_type == "UNVERIFIABLE":
        return "yellow", LABEL_UNVERIFIABLE, LIGHT_YELLOW

    if bool(result.get("is_risk")):
        if risk_type == "SCAM":
            return "red", LABEL_SCAM, LIGHT_RED
        if risk_type == "MISINFO":
            return "red", LABEL_MISINFO, LIGHT_RED
        return "red", LABEL_RISK, LIGHT_RED

    if risk_type == "SAFE":
        # 只有 verified / rule 算已證實；缺鍵、unverified、大小寫錯誤或未知值一律保守視為未證實
        status = result.get("verification_status")
        if status not in VERIFIED_STATUSES:
            return "yellow", LABEL_NO_VERIFIED_SOURCE, LIGHT_YELLOW
        if _confidence(result) >= GREEN_MIN_CONFIDENCE:
            return "green", LABEL_SAFE, LIGHT_GREEN

    return "yellow", LABEL_PENDING, LIGHT_YELLOW
