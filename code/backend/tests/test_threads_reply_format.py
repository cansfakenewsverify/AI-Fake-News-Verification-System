"""Threads 回覆模板與 threads_len 計數（spec 7.7／7.8；測試 FN-5）。純函式、離線。"""
import re

import pytest

from app.services import threads_reply
from app.services.threads_reply import (
    DISCLAIMER,
    THREADS_TARGET_LEN,
    THREADS_TEXT_LIMIT,
    format_verdict_reply,
    reply_cannot_read,
    reply_media_only,
    reply_too_short,
    strip_emoji,
    threads_len,
)

RED, YELLOW, GREEN = "\U0001F534", "\U0001F7E1", "\U0001F7E2"
WARN = "⚠️"  # ⚠️
BASE = "https://factcheck-demo.vercel.app"
RESULT_URL = BASE + "/r/0f8e2b7c-3d1a-4c55-9b61-2a7f3e9d1c44"
TIER1 = {"title": "MyGoPen", "url": "https://www.mygopen.com/2026/09/nhi-card-rumor-abcdef.html", "tier": 1}
TIER2 = {"title": "查核報導", "url": "https://news.example.com/factcheck/123", "tier": 2}
TIER3 = {"title": "PTT 討論", "url": "https://www.ptt.cc/bbs/Gossiping/M.1.html", "tier": 3}
SUMMARY = "網傳健保卡將於下個月停用、需重新申辦並繳交手續費，衛福部與健保署已澄清為不實訊息，" * 2


@pytest.fixture(autouse=True)
def _base_url(monkeypatch):
    monkeypatch.setattr(threads_reply.settings, "PUBLIC_BASE_URL", BASE + "/", raising=False)


def _links(text):
    return re.findall(r"https?://", text)


FIRST_LINE_CASES = [
    ({"is_risk": True, "risk_type": "SCAM", "confidence_score": 0.9,
      "verification_status": "verified", "sources": [TIER1]}, RED + " 詐騙警告"),
    ({"is_risk": True, "risk_type": "MISINFO", "confidence_score": 0.9,
      "verification_status": "verified", "sources": [TIER1]}, RED + " 假訊息"),
    ({"is_risk": True, "risk_type": "OTHER", "confidence_score": 0.9,
      "verification_status": "rule", "sources": [TIER2]}, RED + " 風險訊息"),
    ({"is_risk": False, "risk_type": "SAFE", "confidence_score": 0.4,
      "verification_status": "verified", "sources": [TIER1]}, YELLOW + " 尚待確認"),
    ({"is_risk": False, "risk_type": "SAFE", "confidence_score": 0.95,
      "verification_status": "unverified", "sources": []}, YELLOW + " 尚無查核機構證實"),
    ({"is_risk": False, "risk_type": "UNVERIFIABLE", "confidence_score": 0.0,
      "verification_status": "unverified", "sources": []}, YELLOW + " 無法查證"),
    ({"is_risk": False, "risk_type": "SAFE", "confidence_score": 0.95,
      "verification_status": "verified", "sources": [TIER1]}, GREEN + " 查無異常"),
]


@pytest.mark.parametrize("result,first_line", FIRST_LINE_CASES)
def test_seven_first_lines_within_target(result, first_line):
    result = dict(result, summary=SUMMARY)
    reply = format_verdict_reply(result, RESULT_URL)
    lines = reply.split("\n")
    assert lines[0] == first_line
    assert threads_len(reply) <= THREADS_TARGET_LEN
    assert f"完整判讀：{RESULT_URL}" in lines
    assert lines[-1] == DISCLAIMER
    assert len(_links(reply)) <= 2


def test_first_line_reads_frame_not_risk_type():
    # SAFE 高信心但未證實 → 不得是綠燈（frame_of 單一權威）
    reply = format_verdict_reply({"risk_type": "SAFE", "confidence_score": 0.99, "summary": "s"}, RESULT_URL)
    assert reply.split("\n")[0] == YELLOW + " 尚無查核機構證實"
    assert GREEN not in reply


def test_summary_over_120_cut_at_118():
    long_summary = "甲" * 130
    reply = format_verdict_reply(
        {"is_risk": True, "risk_type": "SCAM", "verification_status": "unverified", "summary": long_summary},
        "https://x.app/r/1",
    )
    assert reply.split("\n")[1] == "甲" * 118 + "…"


def test_extreme_four_emoji_and_200_char_summary():
    summary = RED + YELLOW + GREEN + "\U0001F600" + "乙" * 200
    result = {"is_risk": True, "risk_type": "MISINFO", "confidence_score": 0.9,
              "verification_status": "verified", "sources": [TIER1], "summary": summary}
    reply = format_verdict_reply(result, RESULT_URL)
    assert threads_len(reply) <= THREADS_TEXT_LIMIT
    assert threads_len(reply) <= THREADS_TARGET_LEN
    assert "/r/" in reply
    assert "\U0001F600" not in reply          # 非燈號 emoji 已移除
    assert reply.split("\n")[1].endswith("…")
    assert len(_links(reply)) <= 2


def test_extreme_summary_with_warning_emoji():
    summary = WARN + " 注意！" + "這是假冒銀行的釣魚簡訊，請勿點擊連結" * 12 + WARN
    result = {"is_risk": True, "risk_type": "SCAM", "confidence_score": 0.9,
              "verification_status": "verified", "sources": [TIER1], "summary": summary}
    reply = format_verdict_reply(result, RESULT_URL)
    assert threads_len(reply) <= THREADS_TEXT_LIMIT
    assert "/r/" in reply
    assert "⚠" not in reply and "️" not in reply
    assert reply.split("\n")[-1] == DISCLAIMER


def test_unverified_has_single_link():
    result = {"is_risk": True, "risk_type": "SCAM", "confidence_score": 0.9,
              "verification_status": "unverified", "sources": [TIER3], "summary": "假冒物流簡訊"}
    reply = format_verdict_reply(result, RESULT_URL)
    assert len(_links(reply)) == 1
    assert "尚無查核機構證實" in reply.split("\n")
    assert "查核來源：" not in reply


def test_tier3_source_never_appears():
    result = {"is_risk": True, "risk_type": "MISINFO", "confidence_score": 0.9,
              "verification_status": "verified", "sources": [TIER3, TIER2], "summary": "不實訊息"}
    reply = format_verdict_reply(result, RESULT_URL)
    assert "ptt.cc" not in reply
    assert f"查核來源：{TIER2['url']}" in reply.split("\n")
    assert len(_links(reply)) <= 2


def test_only_tier3_sources_even_if_verified_uses_placeholder():
    result = {"is_risk": True, "risk_type": "MISINFO", "verification_status": "verified",
              "sources": [TIER3], "summary": "不實訊息"}
    reply = format_verdict_reply(result, RESULT_URL)
    assert "ptt.cc" not in reply
    assert len(_links(reply)) == 1


def test_without_source_line_omits_line_three():
    result = {"is_risk": True, "risk_type": "SCAM", "verification_status": "verified",
              "sources": [TIER1], "summary": "詐騙"}
    reply = format_verdict_reply(result, RESULT_URL, without_source_line=True)
    assert "查核來源" not in reply
    assert len(_links(reply)) == 1
    assert reply.split("\n")[-2:] == [f"完整判讀：{RESULT_URL}", DISCLAIMER]


def test_huge_url_drops_source_line_but_keeps_result_link():
    long_src = {"title": "t", "url": "https://www.mygopen.com/" + "a" * 250, "tier": 1}
    result = {"is_risk": True, "risk_type": "SCAM", "verification_status": "verified",
              "sources": [long_src], "summary": "丙" * 110}
    reply = format_verdict_reply(result, RESULT_URL)
    assert "查核來源" not in reply
    assert reply.split("\n")[1] == "丙" * 60 + "…"
    assert RESULT_URL in reply and reply.endswith(DISCLAIMER)


def test_default_result_url_from_settings():
    reply = format_verdict_reply({"risk_type": "SAFE", "summary": "s", "task_id": "abc"})
    assert f"完整判讀：{BASE}/r/abc" in reply


# ── threads_len 計數 ──────────────────────────────────────────
def test_threads_len_counts():
    assert threads_len("中文abc") == 5                 # 中文算 1（推論）
    assert threads_len(RED) == 4                        # SMP emoji：4 bytes
    assert threads_len("⚠") == 3                   # BMP emoji ⚠ U+26A0：3 bytes
    assert threads_len("️") == 3                   # 變體選擇子
    assert threads_len("‍") == 3                   # ZWJ
    assert threads_len(WARN) == 6
    family = "\U0001F468‍\U0001F469‍\U0001F467"   # ZWJ 序列
    assert threads_len(family) == 4 + 3 + 4 + 3 + 4
    assert threads_len("") == 0 and threads_len(None) == 0


def test_strip_emoji_keeps_lights_and_plain_symbols():
    assert strip_emoji(RED + WARN + "30°C © 文字\U0001F600") == RED + "30°C © 文字"


# ── 固定文案（spec 7.7 逐字）─────────────────────────────────
def test_fixed_replies_verbatim():
    assert reply_cannot_read() == (
        YELLOW + " 我讀不到這則原貼文（可能是私人帳號、或尚未加入測試名單）。"
        "請把要查證的文字複製後貼到 " + BASE + " 查證。"
    )
    assert reply_media_only() == (
        YELLOW + " 這則貼文只有圖片或影片，我目前只能查文字。請到 " + BASE + " 上傳圖片或貼上文字。"
    )
    assert reply_too_short() == YELLOW + " 這則貼文的文字太短，無法判讀。請貼上完整訊息內容再 @我。"
    for text in (reply_cannot_read(), reply_media_only(), reply_too_short()):
        assert threads_len(text) <= 120 + 4


def test_threads_service_reexports():
    from app.services import threads_service
    assert threads_service.format_verdict_reply is format_verdict_reply
    assert threads_service.threads_len is threads_len
    assert threads_service.THREADS_TEXT_LIMIT == 500
