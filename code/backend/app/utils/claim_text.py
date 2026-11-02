"""
語意比對用的文字：去掉「網傳」「聽說」「請問」這類開頭詞與「是真的嗎？」這類結尾，只留被查證的說法。

使用者常把謠言寫成「網傳吃香蕉配優格會中毒」「聽說 XX 是真的嗎？」，知識庫存的卻是謠言本身。
開頭詞與問句會把向量拉開（2026-10-28 實測：「網傳吃香蕉配優格會中毒」對 MyGoPen「柿子香蕉不能一起吃，
吃完喝優酪乳中毒」0.597，去掉「網傳」後 0.663），所以向量層與證據信心的近鄰查詢都改用這裡的結果。
只影響「拿什麼去比對」：AI 判讀的仍是使用者原文（FR-01），hash 層與知識庫存的 raw_content 也是原文。
"""
import re

_PUNCT = r"[\s，,：:、。．.!！~～]*"
_ASK = r"(?:請問|想問|求證)(?:一下)?"
_WHEN = r"(?:最近|近日|近來|近期|這幾天)"
_WHERE = (r"(?:網路上|網路|網上|臉書上|臉書|FB上|LINE群組裡|LINE群組|LINE上|LINE|群組裡|群組上|群組|"
          r"長輩群組|長輩|親友|朋友|網友|有人|大家)")
_SAYS = r"(?:網傳|謠傳|瘋傳|流傳|盛傳|傳言|傳聞|據傳|據說|聽說|聽人說)"   # 單獨出現就是開頭詞
_TELL = r"(?:轉傳|傳來|在傳|在說|都說|說)"                                # 前面要有「誰」才算
_AFTER = r"(?:的|說|稱|指出|表示|一則|訊息|消息|文章|影片)*"
_LEAD_RE = re.compile(
    rf"^{_PUNCT}(?:{_ASK}{_PUNCT})?"
    rf"(?:(?:{_WHEN}?(?:{_WHERE}(?:都|也)?)?{_SAYS}|{_WHEN}?{_WHERE}(?:都|也)?{_TELL}){_AFTER}{_PUNCT})?",
    re.IGNORECASE,
)
_TRAIL_RE = re.compile(
    r"[\s，,、]*(?:(?:這|這是|這個)?(?:是真的嗎|是不是真的|是真的還是假的|真的假的|是假的嗎|真的嗎|對嗎|正確嗎|可信嗎))?"
    r"[\s？?！!。．.~～…]*$"
)
_QUOTES = {"「": "」", "『": "』", "“": "”", '"': '"'}
MIN_CHARS = 4   # 去完剩不到這麼多字就照原文比對（例如只打了「網傳」）


def matching_text(text: str) -> str:
    """回傳拿去算向量的文字；認不出開頭詞或結尾問句時原樣回傳（只去頭尾空白）。"""
    original = (text or "").strip()
    s = original
    for _ in range(3):   # 「請問，網傳…」「最近網傳，有人說…」這類疊在一起的開頭
        stripped = _LEAD_RE.sub("", s, count=1)
        if stripped == s:
            break
        s = stripped
    tail = _TRAIL_RE.search(s)
    if tail and tail.group(0):
        s = s[:tail.start()]
        if s.endswith("嗎") and re.search(r"[？?]", tail.group(0)):
            s = s[:-1]
    if len(s) >= 2 and _QUOTES.get(s[0]) == s[-1]:
        s = s[1:-1].strip()
    return s if len(s) >= MIN_CHARS else original
