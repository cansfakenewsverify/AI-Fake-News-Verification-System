"""FR-19 來源 prompt 規則守門測試（離線、零點數）。"""
from app.services import ai_service

FR19_RULE = (
    "`sources` 只能列出**已對這則訊息做出判定**的查核機構或媒體查核報導"
    "（TFC、MyGoPen、Cofacts 有回覆的文章、政府機關公告、主流媒體的查核報導）。"
    "找不到這類來源就回 `sources: []`，不要列出求證平台上尚未回覆的貼文、"
    "一般新聞或社群貼文，不要猜測或編造網址。"
)


def test_system_prompt_contains_fr19_rule():
    prompt = ai_service.SYSTEM_PROMPT_V41
    assert "找不到這類來源就回 `sources: []`" in prompt
    assert "已對這則訊息做出判定" in prompt


def test_fr19_rule_is_verbatim_and_inside_fact_check_section():
    prompt = ai_service.SYSTEM_PROMPT_V41
    assert FR19_RULE in prompt
    section_start = prompt.index("雙重事實查核")
    section_end = prompt.index("3. **短影音邏輯")
    assert section_start < prompt.index(FR19_RULE) < section_end
