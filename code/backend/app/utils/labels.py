"""
category 中文對照（spec §5.3：category_label 由後端統一中文化，取代前端各自的 CAT_MAP）。

鍵取自 ai_service.SYSTEM_PROMPT_V41 的「Category List」；AI 的 category 未經清單驗證，
未知值回退 CATEGORY_LABEL_UNKNOWN，空值回空字串。
"""
from typing import Any, Dict

CATEGORY_LABELS: Dict[str, str] = {
    # 詐騙類 - SCAM
    "Investment": "投資詐騙",
    "Phishing": "釣魚詐騙",
    "Impersonation": "假冒身分",
    "E-Commerce": "網購詐騙",
    "Job": "求職詐騙",
    "Romance": "愛情詐騙",
    # 假訊息類 - MISINFO
    "Health_Rumor": "健康謠言",
    "Political_Rumor": "政治謠言",
    "Content_Farm": "內容農場",
    "Old_News": "舊聞重炒",
    "Urban_Legend": "都市傳說",
    # 其他
    "Safe": "安全資訊",
    "Irrelevant": "無關內容",
}

CATEGORY_LABEL_UNKNOWN = "其他"

_LOWER_LOOKUP = {k.lower(): v for k, v in CATEGORY_LABELS.items()}


def category_label(category: Any) -> str:
    """英文 category → 中文標籤；大小寫不敏感，未知值回「其他」，空值回空字串。"""
    key = str(category or "").strip()
    if not key:
        return ""
    return CATEGORY_LABELS.get(key) or _LOWER_LOOKUP.get(key.lower()) or CATEGORY_LABEL_UNKNOWN
