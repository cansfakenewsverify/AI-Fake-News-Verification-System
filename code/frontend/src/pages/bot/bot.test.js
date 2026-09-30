import { test } from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { t } from "../../i18n.js";
import { formatTaipeiDateTime } from "../result/resultState.js";
import {
  KNOWN_ERRORS,
  backoffText,
  badgeKey,
  isOff,
  lastErrorText,
  lastPollText,
  replyRows,
} from "./botModel.js";

// Bot status page model (S-11). Expected texts come from t() so this folder stays free of Han characters.

const fixture = async (name) =>
  JSON.parse(await readFile(new URL(`../../dev/fixtures/${name}.json`, import.meta.url), "utf-8"));

test("badge follows the mode and token_invalid wins", () => {
  assert.equal(badgeKey({ mode: "live" }), "threads_mode_live");
  assert.equal(badgeKey({ mode: "sim" }), "threads_mode_sim");
  assert.equal(badgeKey({ mode: "off" }), "threads_mode_off");
  assert.equal(badgeKey({ mode: "weird" }), "threads_mode_off");
  assert.equal(badgeKey({ mode: "live", last_error: "token_invalid" }), "threads_mode_invalid");
  assert.equal(badgeKey(null), null);
});

test("off covers mode off, disabled and unknown modes", async () => {
  assert.equal(isOff(await fixture("threads_status_off")), true);
  assert.equal(isOff(await fixture("threads_status_sim")), false);
  assert.equal(isOff({ mode: "live", enabled: false }), true);
  assert.equal(isOff({ mode: "nope", enabled: true }), true);
  assert.equal(isOff(null), true);
});

test("last poll line shows time and the four counters", async () => {
  const status = await fixture("threads_status_sim");
  assert.equal(
    lastPollText(status),
    t("threads_last_poll", {
      time: formatTaipeiDateTime(status.last_poll_at),
      checked: 3,
      replied: 2,
      skipped: 1,
      errors: 0,
    }),
  );
  assert.equal(lastPollText({ last_poll_at: null }), t("threads_never_polled"));
  assert.match(lastPollText({ last_poll_at: "2026-09-23T06:32:10+00:00", last_poll_stats: null }), /0/);
});

test("known errors get their own sentence, unknown codes are shown as codes", () => {
  for (const code of KNOWN_ERRORS) {
    const text = lastErrorText({ last_error: code });
    assert.equal(text, t(`threads_error_${code}`));
    assert.notEqual(text, `threads_error_${code}`, code);
  }
  assert.equal(lastErrorText({ last_error: "client_error" }), t("threads_error_other", { code: "client_error" }));
  assert.equal(lastErrorText({ last_error: null }), null);
});

test("backoff line only while backoff_until is in the future", () => {
  const now = Date.parse("2026-09-24T00:00:00Z");
  assert.equal(backoffText({ backoff_until: "2026-09-24T01:00:00+00:00" }, now),
    t("threads_backoff", { time: formatTaipeiDateTime("2026-09-24T01:00:00+00:00") }));
  assert.equal(backoffText({ backoff_until: "2026-09-23T23:00:00+00:00" }, now), null);
  assert.equal(backoffText({ backoff_until: null }, now), null);
  assert.equal(backoffText({ backoff_until: "garbage" }, now), null);
});

test("reply rows keep the stored frame_type and link only to safe targets", async () => {
  const { records } = await fixture("threads_replies");
  const [first] = replyRows(records);
  assert.deepEqual(first.item, { frame_type: "red", risk_type: "MISINFO" });
  assert.equal(first.meta[0], t("from_threads", { username: "tester_c" }));
  assert.equal(first.permalink, "https://www.threads.com/@tester_c/post/sim2");
  assert.equal(first.resultTo, "/r/fx-red-misinfo");
  assert.ok(first.replyText.includes("\n"));

  const [unsafe] = replyRows([{ permalink: "javascript:alert(1)", result_id: "../admin", username: "@x" }]);
  assert.equal(unsafe.permalink, null);
  assert.equal(unsafe.resultTo, null);
  assert.equal(unsafe.meta[0], t("from_threads", { username: "x" }));
  assert.deepEqual(replyRows(null), []);
});
