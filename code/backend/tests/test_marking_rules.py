"""標記規則測試（CLAUDE.md 第 9 節，勿退回舊邏輯的守門測試）。"""
from app.services.news_fetcher import (
    _extract_claim_from_title,
    _is_real_claim,
    _title_says_false,
    _title_indicates_debunk,
)
from app.services.search_service import _strip_html, _is_valid_url


# ── MyGoPen/TFC 標題標籤 ───────────────────────────────────────
def test_title_says_false_with_tag():
    assert _title_says_false("【錯誤】網傳紅豆營養比牛肉高？")
    assert _title_says_false("【易誤解】吃這些天然增肌果比雞蛋厲害？")
    assert not _title_says_false("紅豆營養比牛肉高？")           # 無標籤
    assert not _title_says_false("【活動】全民查核小考題")        # 標籤非不實判定


def test_extract_claim_from_title():
    assert _extract_claim_from_title("【錯誤】網傳紅豆營養比牛肉高？專家詳解") == "紅豆營養比牛肉高"
    assert _extract_claim_from_title("網傳「出國換SIM卡會被過戶」！查核") == "「出國換SIM卡會被過戶」"


def test_is_real_claim_filters():
    assert _is_real_claim("出國換SIM卡會導致房產被過戶")
    assert not _is_real_claim("https://example.com/only-url")   # 純網址
    assert not _is_real_claim("too short")                       # 無中文
    assert not _is_real_claim("短")                              # 太短
    assert not _is_real_claim("標籤,雲,一,二,三,四,五,六,七,八")   # 標籤雲


# ── 主流媒體查核報導判定（2026-07 修的「同謠言兩種標籤」bug）────
def test_debunk_title_positive():
    # 需同時含「查核語境詞」與「不實判定詞」
    assert _title_indicates_debunk(
        "出國換SIM卡「個資外洩、房產被轉移」？ 台灣事實查核中心：說法過度誇大"
    )
    assert _title_indicates_debunk("車停紅白結界罰3.6萬？高雄警急闢謠：那是假的！")
    assert _title_indicates_debunk("經濟部澄清並呼籲民眾警惕「冒用機關名義」的錯假訊息")


def test_debunk_title_negative():
    assert not _title_indicates_debunk("警方成立闢謠專區服務民眾")       # 只有語境詞
    assert not _title_indicates_debunk("網傳「健保隱藏福利」是部分負擔上限核退")  # 查核為真
    assert not _title_indicates_debunk("台灣大反詐戰警2025年趨勢報告")   # 一般反詐報導
    assert not _title_indicates_debunk("")


# ── RSS 清洗 ──────────────────────────────────────────────────
def test_strip_html_decodes_entities():
    assert _strip_html("標題&nbsp;&nbsp;來源") == "標題  來源"
    assert _strip_html("<b>A &amp; B</b>") == "A & B"
    assert _strip_html(None) == ""


def test_is_valid_url_skips_social():
    assert _is_valid_url("https://news.example.com/a")
    assert not _is_valid_url("https://facebook.com/post/1")
    assert not _is_valid_url("not-a-url")
