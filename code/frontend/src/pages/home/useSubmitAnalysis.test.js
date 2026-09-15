import { test } from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { t } from "../../i18n.js";
import { ApiError, analyzeText, analyzeUrl, configureFixtures } from "../../lib/api.js";
import {
  DEFAULT_RETRY_AFTER_SECONDS,
  homePrefillState,
  inputStorageKey,
  loadSubmittedInput,
  previewOf,
  readHomePrefill,
  resultIdOf,
  saveSubmittedInput,
  submitErrorFeedback,
} from "./useSubmitAnalysis.js";

// S-02 home submit helpers. Expected texts come from t() so this folder stays free of Han characters.

const http = (status, extra = {}) => new ApiError({ kind: "http", status, ...extra });

function memoryStorage() {
  const data = new Map();
  return {
    getItem: (k) => (data.has(k) ? data.get(k) : null),
    setItem: (k, v) => data.set(k, String(v)),
    removeItem: (k) => data.delete(k),
    data,
  };
}

const throwingStorage = {
  getItem() {
    throw new Error("denied");
  },
  setItem() {
    throw new Error("denied");
  },
};

test("network, timeout and gateway errors defer to the backend_down banner", () => {
  assert.deepEqual(submitErrorFeedback(new ApiError({ kind: "network" })), { type: "backend_down" });
  assert.deepEqual(submitErrorFeedback(new ApiError({ kind: "timeout" })), { type: "backend_down" });
  for (const status of [502, 503, 504]) {
    assert.deepEqual(submitErrorFeedback(http(status)), { type: "backend_down" }, String(status));
  }
});

test("422 invalid_url and blocked_url map to the 8.7 strings", () => {
  assert.deepEqual(submitErrorFeedback(http(422, { code: "invalid_url", message: "x" })), {
    type: "inline",
    message: t("err_invalid_url"),
  });
  assert.deepEqual(submitErrorFeedback(http(422, { code: "blocked_url", message: "x" })), {
    type: "inline",
    message: t("err_blocked_url"),
  });
});

test("422 validation_error shows the response message", () => {
  assert.deepEqual(submitErrorFeedback(http(422, { code: "validation_error", message: "server says" })), {
    type: "inline",
    message: "server says",
  });
  // no readable message: ApiError falls back to the code or "HTTP 422"
  for (const message of [undefined, "HTTP 422", "  "]) {
    assert.deepEqual(submitErrorFeedback(http(422, { code: "validation_error", message })), {
      type: "inline",
      message: t("error_server", { code: "validation_error" }),
    }, String(message));
  }
});

test("429 rate_limited uses Retry-After seconds, defaulting when missing", () => {
  const withHeader = submitErrorFeedback(http(429, { code: "rate_limited", retryAfter: 30 }));
  assert.deepEqual(withHeader, { type: "inline", message: t("err_rate", { n: 30 }) });
  for (const retryAfter of [null, 0, Number.NaN]) {
    const fallback = submitErrorFeedback(http(429, { code: "rate_limited", retryAfter }));
    assert.equal(fallback.message, t("err_rate", { n: DEFAULT_RETRY_AFTER_SECONDS }), String(retryAfter));
  }
  // unknown 429 codes are treated as rate limiting too
  assert.equal(submitErrorFeedback(http(429, { retryAfter: 5 })).message, t("err_rate", { n: 5 }));
});

test("429 daily_cap_reached asks for the quota card", () => {
  assert.deepEqual(submitErrorFeedback(http(429, { code: "daily_cap_reached", retryAfter: 3600 })), {
    type: "quota",
  });
});

test("other failures show error_server with the code or status", () => {
  assert.equal(
    submitErrorFeedback(http(500, { code: "analysis_failed" })).message,
    t("error_server", { code: "analysis_failed" }),
  );
  assert.equal(submitErrorFeedback(http(500)).message, t("error_server", { code: 500 }));
  assert.equal(submitErrorFeedback(http(422, { code: "something_new" })).message, t("error_server", { code: "something_new" }));
  assert.equal(submitErrorFeedback(new TypeError("boom")).message, t("error_server", { code: "unknown" }));
});

test("inline messages never leak placeholders", () => {
  const cases = [
    http(422, { code: "invalid_url" }),
    http(422, { code: "blocked_url" }),
    http(429, { code: "rate_limited" }),
    http(500),
    new Error("x"),
  ];
  for (const err of cases) {
    const feedback = submitErrorFeedback(err);
    assert.equal(feedback.type, "inline");
    assert.ok(!/[{}]/.test(feedback.message), feedback.message);
  }
});

test("submitted input round-trips through session storage", () => {
  const storage = memoryStorage();
  assert.equal(saveSubmittedInput("abc", { input_type: "url", content: "https://example.com" }, storage), true);
  assert.equal(storage.data.has(inputStorageKey("abc")), true);
  assert.equal(inputStorageKey("abc"), "fcc_input_abc");
  assert.deepEqual(loadSubmittedInput("abc", storage), { input_type: "url", content: "https://example.com" });
  assert.equal(loadSubmittedInput("missing", storage), null);
});

test("submitted input helpers swallow storage failures and reject bad data", () => {
  assert.equal(saveSubmittedInput("abc", { input_type: "text", content: "x" }, throwingStorage), false);
  assert.equal(loadSubmittedInput("abc", throwingStorage), null);
  assert.equal(saveSubmittedInput("abc", { input_type: "text", content: "x" }, undefined), false);
  assert.equal(saveSubmittedInput("", { input_type: "text", content: "x" }, memoryStorage()), false);

  const storage = memoryStorage();
  storage.setItem(inputStorageKey("bad-json"), "{oops");
  storage.setItem(inputStorageKey("bad-type"), JSON.stringify({ input_type: "image", content: "x" }));
  storage.setItem(inputStorageKey("empty"), JSON.stringify({ input_type: "text", content: "" }));
  assert.equal(loadSubmittedInput("bad-json", storage), null);
  assert.equal(loadSubmittedInput("bad-type", storage), null);
  assert.equal(loadSubmittedInput("empty", storage), null);
});

test("home prefill state round-trips text and url, and skips image or empty input", () => {
  assert.deepEqual(homePrefillState("text", "hello"), { prefill: { mode: "text", value: "hello" } });
  assert.deepEqual(readHomePrefill(homePrefillState("text", "hello")), { mode: "text", value: "hello" });
  assert.deepEqual(readHomePrefill(homePrefillState("url", "https://example.com")), {
    mode: "url",
    value: "https://example.com",
  });
  assert.equal(homePrefillState("image", "[x]"), null);
  assert.equal(homePrefillState("text", "   "), null);
  assert.equal(homePrefillState(undefined, "x"), null);
  assert.equal(readHomePrefill(null), null);
  assert.equal(readHomePrefill({ prefill: { mode: "image", value: "x" } }), null);
  assert.equal(readHomePrefill({ prefill: { mode: "text", value: 5 } }), null);
  assert.equal(readHomePrefill({ other: true }), null);
});

test("previewOf collapses whitespace into one line", () => {
  assert.equal(previewOf("  line one\n\n line\ttwo  "), "line one line two");
  assert.equal(previewOf(undefined), "");
});

test("resultIdOf prefers result_id and falls back to task_id", () => {
  assert.equal(resultIdOf({ result_id: "r1", task_id: "t1" }), "r1");
  assert.equal(resultIdOf({ result_id: "", task_id: "t1" }), "t1");
  assert.equal(resultIdOf({ task_id: "t1" }), "t1");
  assert.equal(resultIdOf({ frame_type: "red" }), null);
  assert.equal(resultIdOf(null), null);
});

// The S-02 fixture files flow through api.js exactly like real responses.
async function withFixture(search, run) {
  configureFixtures({
    loader: async (name) => JSON.parse(await readFile(new URL(`../../dev/fixtures/${name}`, import.meta.url), "utf8")),
    search,
  });
  try {
    return await run();
  } finally {
    configureFixtures(null);
  }
}

test("fixture analyze_text_ok yields a result id", async () => {
  const response = await withFixture("", () => analyzeText("hello"));
  assert.equal(resultIdOf(response), "fx-pending");
});

test("fixture analyze_rate_limited yields err_rate with 30 seconds", async () => {
  const err = await withFixture("?fixture=analyze_rate_limited", () => analyzeText("hello").catch((e) => e));
  assert.ok(err instanceof ApiError);
  assert.equal(err.retryAfter, 30);
  assert.deepEqual(submitErrorFeedback(err), { type: "inline", message: t("err_rate", { n: 30 }) });
});

test("fixture analyze_url_blocked yields err_blocked_url", async () => {
  const err = await withFixture("?fixture=analyze_url_blocked", () => analyzeUrl("http://127.0.0.1/").catch((e) => e));
  assert.deepEqual(submitErrorFeedback(err), { type: "inline", message: t("err_blocked_url") });
});

test("fixture analyze_daily_cap_reached yields the quota card", async () => {
  const err = await withFixture("?fixture=analyze_daily_cap_reached", () => analyzeText("hello").catch((e) => e));
  assert.deepEqual(submitErrorFeedback(err), { type: "quota" });
});
