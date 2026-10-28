"""語意比對用的文字（app/utils/claim_text.py）：去掉開頭詞與結尾問句，其餘原樣。"""
import pytest

from app.utils.claim_text import matching_text


@pytest.mark.parametrize("text, expected", [
    ("網傳吃香蕉配優格會中毒", "吃香蕉配優格會中毒"),
    ("網傳「吃香蕉配優格會中毒」是真的嗎？", "吃香蕉配優格會中毒"),
    ("聽說吃香蕉配優格會中毒是真的嗎？", "吃香蕉配優格會中毒"),
    ("吃香蕉配優格會中毒嗎？", "吃香蕉配優格會中毒"),
    ("請問一下，網路上流傳：吃完柿子不能喝優酪乳", "吃完柿子不能喝優酪乳"),
    ("LINE群組在傳 健保卡即日起停用", "健保卡即日起停用"),
    ("有人說喝溫水可以殺死病毒，真的假的", "喝溫水可以殺死病毒"),
    ("最近網傳，有人說喝溫水可以殺死病毒", "喝溫水可以殺死病毒"),
    ("朋友傳來的訊息：喝溫水可以殺死病毒", "喝溫水可以殺死病毒"),
    ("  據說颱風天不用上班。 ", "颱風天不用上班"),
])
def test_strips_lead_in_and_question(text, expected):
    assert matching_text(text) == expected


@pytest.mark.parametrize("text", [
    "台灣軍人若效忠中共取消退休金，這守護台灣的法案本週竟被國民黨擋下了",
    "朋友借錢不還怎麼辦",              # 「朋友」後面不是「說／傳來」：不是開頭詞
    "有人在路邊撿到錢",
    "大家好，我是銀行客服",
    "傳說中的寶藏在台東",              # 「傳說」不當開頭詞
    "緊急！點擊連結領取政府普發現金六千元，逾期作廢，加LINE客服 gov888 快速申請",
])
def test_leaves_other_text_alone(text):
    assert matching_text(text) == text


@pytest.mark.parametrize("text", ["網傳", "聽說真的嗎？", "網傳「是」"])
def test_too_short_after_stripping_keeps_original(text):
    assert matching_text(text) == text


def test_empty_input():
    assert matching_text("") == ""
    assert matching_text(None) == ""
