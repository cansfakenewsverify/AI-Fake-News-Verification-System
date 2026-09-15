import { test } from "node:test";
import assert from "node:assert/strict";
import { STRINGS, EXTRA, BRAND, BOT_HANDLE, t } from "./i18n.js";

// spec §8.7 全部 key（成對 key 已拆開）+ §7.7 分享文案五則
const SPEC_87_KEYS = [
  "home_tagline", "home_sub", "tab_text", "tab_url", "tab_image",
  "input_placeholder_text", "input_placeholder_url", "upload_hint",
  "btn_analyze", "btn_analyzing", "analyze_note",
  "example_1", "example_2", "example_3",
  "err_empty", "err_too_long", "err_invalid_url", "err_blocked_url",
  "err_image_type", "err_image_size", "err_rate", "backend_down",
  "result_loading", "result_step_1", "result_step_2", "result_step_3",
  "error_timeout", "chip_live", "chip_cache_url", "chip_cache_hash", "chip_cache_vector",
  "cache_hint", "frame_red_scam", "frame_red_misinfo", "frame_red_other",
  "frame_yellow", "frame_yellow_unverifiable", "frame_green", "frame_grey",
  "confidence_chip_high", "confidence_chip_mid", "confidence_chip_low", "confidence_note",
  "section_input", "section_summary", "section_explanation", "section_sources", "section_similar",
  "similar_item", "sources_empty", "tier_1_chip", "tier_2_chip",
  "no_verified_source_title", "no_verified_source_body", "frame_yellow_no_source",
  "ai_unavailable_title", "ai_unavailable_body", "quota_exceeded_title", "quota_exceeded_body",
  "unverifiable_body", "unverifiable_threads_hint",
  "error_title", "error_network", "error_server",
  "btn_retry", "btn_reanalyze", "btn_share_threads", "btn_share_opened",
  "btn_copy_link", "btn_copied", "btn_check_another", "toast_share",
  "result_not_found_title", "result_not_found_body", "btn_home", "from_threads",
  "label_source_ai", "label_source_rule", "label_source_gold", "label_source_admin",
  "analyzed_at", "disclaimer_short",
  "trending_title", "trending_sub", "scheduler_on", "scheduler_off", "trending_updated",
  "trending_empty", "filter_empty", "chip_pending",
  "knowledge_title", "knowledge_sub", "knowledge_search_placeholder", "knowledge_stats",
  "knowledge_verified_note", "knowledge_empty", "knowledge_no_match", "hit_count",
  "btn_load_more", "knowledge_end",
  "history_title", "history_sub", "history_empty", "history_unavailable",
  "btn_clear_history", "confirm_clear",
  "bot_howto", "threads_title", "threads_mode_live", "threads_mode_sim", "threads_mode_off",
  "threads_mode_invalid", "threads_off", "threads_last_poll", "threads_token_days",
  "threads_token_warn", "threads_daily", "dev_mode_notice", "btn_run_poll",
  "threads_replies_title", "threads_replies_empty", "btn_view_post", "btn_view_result",
  "theme_dark", "theme_light", "nav_home", "nav_trending", "nav_knowledge", "nav_bot",
  "nav_history",
  "deauthorize_title", "deauthorize_body", "footer",
  "privacy_title", "privacy_collect", "privacy_not", "privacy_ai",
  "deletion_title", "deletion_body", "oauth_cb_title", "oauth_cb_body", "page_title_suffix",
  "share_text_red_scam", "share_text_red_misinfo", "share_text_yellow",
  "share_text_green", "share_text_yellow_unverified",
];

for (const key of SPEC_87_KEYS) {
  test(`STRINGS has non-empty ${key}`, () => {
    assert.equal(typeof STRINGS[key], "string");
    assert.ok(STRINGS[key].trim().length > 0);
  });
}

test("EXTRA strings are non-empty and do not shadow STRINGS", () => {
  for (const [key, value] of Object.entries(EXTRA)) {
    assert.ok(value.trim().length > 0, key);
    assert.ok(!(key in STRINGS), key);
  }
});

test("t err_rate substitutes n", () => {
  assert.equal(t("err_rate", { n: 30 }), "查證太頻繁，請 30 秒後再試。");
});

test("t page_title_suffix uses default brand", () => {
  assert.equal(BRAND, "全民查證公社");
  assert.equal(t("page_title_suffix"), "｜全民查證公社");
});

test("t auto-fills BOT_HANDLE", () => {
  assert.ok(t("bot_howto", { n: 2 }).includes(`@${BOT_HANDLE}`));
  assert.ok(t("bot_howto", { n: 2 }).includes("2 分鐘"));
});

test("confidence chips are verbatim 8.7 without placeholders", () => {
  assert.equal(t("confidence_chip_high"), "信心 高");
  assert.equal(t("confidence_chip_mid"), "信心 中");
  assert.equal(t("confidence_chip_low"), "信心 低");
  assert.ok(!("confidence_chip" in STRINGS));
});

test("t falls back to EXTRA", () => {
  assert.equal(t("back"), "← 返回");
});

test("t missing key returns key", () => {
  const origWarn = console.warn;
  const calls = [];
  console.warn = (...args) => calls.push(args);
  try {
    assert.equal(t("no_such_key"), "no_such_key");
    // node --test 下 import.meta.env 不存在 -> 視為開發環境，須警告一次
    assert.equal(calls.length, 1);
    assert.ok(String(calls[0][0]).includes("no_such_key"));
  } finally {
    console.warn = origWarn;
  }
});

test("t leaves unknown placeholders intact", () => {
  assert.ok(t("deletion_body").includes("{CONTACT_EMAIL}"));
});

test("t truncates {summary≤80}", () => {
  const long = "字".repeat(100);
  const out = t("share_text_green", { summary: long });
  const summaryPart = out.replace("🟢 AI 查證這則訊息沒有發現異常：", "");
  assert.equal(Array.from(summaryPart).length, 80);
  assert.ok(summaryPart.endsWith("…"));
  assert.equal(t("share_text_green", { summary: "短" }), "🟢 AI 查證這則訊息沒有發現異常：短");
});
