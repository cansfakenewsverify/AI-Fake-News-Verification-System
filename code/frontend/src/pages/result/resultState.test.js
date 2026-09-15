import { test } from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { t } from "../../i18n.js";
import { ApiError, FALLBACK_PREFIX, configureFixtures, pollResult } from "../../lib/api.js";
import {
  POLL_INTERVAL_MS,
  POLL_MAX_MS,
  failureCode,
  followSpaLink,
  formatTaipeiDateTime,
  historyPatch,
  httpUrlOrNull,
  isThreadsUrl,
  outcomeFromError,
  outcomeFromPoll,
  resultView,
  visibleSources,
} from "./resultState.js";
import { reanalyzeMessage } from "./useReanalyze.js";

// S-04..S-08 result page helpers. Expected texts come from t() so this folder stays free of Han characters.

test("polling budget matches spec 8.3 S2 (2 s interval, 90 s max)", () => {
  assert.equal(POLL_INTERVAL_MS, 2000);
  assert.equal(POLL_MAX_MS, 90000);
});

test("outcomeFromPoll maps timeout, failed and completed", () => {
  const pending = { status: "pending" };
  assert.deepEqual(outcomeFromPoll({ timedOut: true, last: pending }), { phase: "timeout", data: pending });
  assert.deepEqual(outcomeFromPoll({ timedOut: true, last: null }), { phase: "timeout", data: null });
  const failed = { status: "failed", error: { code: "analysis_failed" } };
  assert.deepEqual(outcomeFromPoll({ timedOut: false, last: failed }), { phase: "failed", data: failed });
  const done = { status: "completed", result: {} };
  assert.deepEqual(outcomeFromPoll({ timedOut: false, last: done }), { phase: "completed", data: done });
});

test("outcomeFromError: 404 -> not_found", () => {
  assert.equal(outcomeFromError(new ApiError({ kind: "http", status: 404, code: "result_not_found" })).phase, "not_found");
  assert.equal(outcomeFromError(new ApiError({ kind: "http", status: 404 })).phase, "not_found");
});

test("outcomeFromError: network, timeout and gateway errors -> network", () => {
  assert.equal(outcomeFromError(new ApiError({ kind: "network" })).phase, "network");
  assert.equal(outcomeFromError(new ApiError({ kind: "timeout" })).phase, "network");
  for (const status of [502, 503, 504]) {
    assert.equal(outcomeFromError(new ApiError({ kind: "http", status })).phase, "network", String(status));
  }
});

test("outcomeFromError: other failures -> error with code or status", () => {
  assert.deepEqual(outcomeFromError(new ApiError({ kind: "http", status: 500, code: "boom" })), {
    phase: "error",
    data: null,
    code: "boom",
  });
  assert.equal(outcomeFromError(new ApiError({ kind: "http", status: 500 })).code, "500");
  assert.equal(outcomeFromError(new TypeError("x")).code, "unknown");
});

test("resultView dispatches on the ai_unavailable boolean, never on the summary prefix", () => {
  assert.equal(resultView({ ai_unavailable: true, result: { risk_type: "SAFE", frame_type: "grey" } }), "ai_unavailable");
  assert.equal(resultView({ ai_unavailable: true, result: null }), "ai_unavailable");
  // prefix alone must not switch to the grey card
  const prefixOnly = { ai_unavailable: false, result: { risk_type: "SAFE", summary: `${FALLBACK_PREFIX} x` } };
  assert.equal(resultView(prefixOnly), "success");
  assert.equal(resultView({ ai_unavailable: false, result: { risk_type: "UNVERIFIABLE" } }), "unverifiable");
  assert.equal(resultView({ ai_unavailable: false, result: { risk_type: "SCAM" } }), "success");
  assert.equal(resultView({ ai_unavailable: false, result: null }), "invalid");
  assert.equal(resultView(null), "invalid");
});

test("visibleSources keeps tier 1 and 2 only, in order", () => {
  const t1 = { title: "a", url: "https://www.mygopen.com/x", tier: 1 };
  const t2 = { title: "b", url: "https://news.example.com/x", tier: 2 };
  const t3 = { title: "c", url: "https://www.threads.com/@u/post/1", tier: 3 };
  const untiered = { title: "d", url: "https://example.com" };
  assert.deepEqual(visibleSources({ sources: [t1, t3, untiered, null, "x", t2] }), [t1, t2]);
  assert.deepEqual(visibleSources({ sources: [{ ...t2, tier: "2" }] }).length, 1);
  assert.deepEqual(visibleSources({ sources: null }), []);
  assert.deepEqual(visibleSources(null), []);
});

test("failureCode falls back to analysis_failed", () => {
  assert.equal(failureCode({ error: { code: "analysis_failed" } }), "analysis_failed");
  assert.equal(failureCode({ error: { code: "other_code" } }), "other_code");
  assert.equal(failureCode({ error: null }), "analysis_failed");
  assert.equal(failureCode(null), "analysis_failed");
});

test("historyPatch writes back risk_type and frame_type", () => {
  assert.deepEqual(historyPatch({ result: { risk_type: "SCAM", frame_type: "red" } }), {
    risk_type: "SCAM",
    frame_type: "red",
  });
  assert.deepEqual(historyPatch({ ai_unavailable: true, result: null }), { risk_type: null, frame_type: "grey" });
  assert.deepEqual(historyPatch({ result: null }), { risk_type: null, frame_type: null });
});

test("isThreadsUrl matches threads.net / threads.com hosts exactly", () => {
  for (const url of [
    "https://www.threads.net/@user/post/abc",
    "https://threads.net/@user",
    "https://www.threads.com/@user/post/abc",
    "http://threads.com",
    "  https://WWW.THREADS.COM/@u  ",
  ]) {
    assert.equal(isThreadsUrl(url), true, url);
  }
  for (const url of [
    "https://evilthreads.net/x",
    "https://threads.net.evil.com/x",
    "https://example.com/?u=threads.net",
    "threads.net/@user",
    "ftp://threads.net/x",
    "",
    null,
  ]) {
    assert.equal(isThreadsUrl(url), false, String(url));
  }
});

test("httpUrlOrNull only accepts http(s)", () => {
  assert.equal(httpUrlOrNull("https://www.threads.com/@u/post/1"), "https://www.threads.com/@u/post/1");
  assert.equal(httpUrlOrNull("javascript:alert(1)"), null);
  assert.equal(httpUrlOrNull("not a url"), null);
  assert.equal(httpUrlOrNull(undefined), null);
});

test("formatTaipeiDateTime renders Asia/Taipei YYYY-MM-DD HH:mm", () => {
  assert.equal(formatTaipeiDateTime("2026-09-16T10:21:14+08:00"), "2026-09-16 10:21");
  assert.equal(formatTaipeiDateTime("2026-09-16T02:21:14Z"), "2026-09-16 10:21");
  assert.equal(formatTaipeiDateTime("2026-09-15T16:05:00Z"), "2026-09-16 00:05");
  assert.equal(formatTaipeiDateTime("nope"), "");
  assert.equal(formatTaipeiDateTime(null), "");
});

test("followSpaLink navigates on plain clicks and leaves modified clicks to the browser", () => {
  const calls = [];
  const navigate = (to) => calls.push(to);
  const click = (extra = {}) => {
    const event = { button: 0, defaultPrevented: false, prevented: false, ...extra };
    event.preventDefault = () => {
      event.prevented = true;
    };
    return event;
  };
  const plain = click();
  followSpaLink(plain, navigate, "/");
  assert.equal(plain.prevented, true);
  assert.deepEqual(calls, ["/"]);
  for (const extra of [{ ctrlKey: true }, { metaKey: true }, { shiftKey: true }, { button: 1 }]) {
    const event = click(extra);
    followSpaLink(event, navigate, "/");
    assert.equal(event.prevented, false, JSON.stringify(extra));
  }
  assert.equal(calls.length, 1);
});

test("reanalyzeMessage maps submit feedback", () => {
  assert.deepEqual(reanalyzeMessage({ type: "inline", message: "m" }), ["m"]);
  assert.deepEqual(reanalyzeMessage({ type: "quota" }), [t("quota_exceeded_title"), t("quota_exceeded_body")]);
  assert.equal(reanalyzeMessage({ type: "backend_down" }), null);
  assert.equal(reanalyzeMessage(null), null);
});

// The S-04 fixture files flow through pollResult() exactly like real responses.
async function withFixtures(run) {
  configureFixtures({
    loader: async (name) => {
      try {
        return JSON.parse(await readFile(new URL(`../../dev/fixtures/${name}`, import.meta.url), "utf8"));
      } catch {
        return null;
      }
    },
    search: "",
  });
  try {
    return await run();
  } finally {
    configureFixtures(null);
  }
}

test("fixture fx-failed -> failed phase with analysis_failed", async () => {
  const outcome = await withFixtures(async () => outcomeFromPoll(await pollResult("fx-failed", { intervalMs: 1 })));
  assert.equal(outcome.phase, "failed");
  assert.equal(failureCode(outcome.data), "analysis_failed");
  assert.equal(t("error_server", { code: failureCode(outcome.data) }).includes("analysis_failed"), true);
});

test("fixture fx-notfound -> not_found phase", async () => {
  const outcome = await withFixtures(() =>
    pollResult("fx-notfound", { intervalMs: 1 }).then(outcomeFromPoll, outcomeFromError),
  );
  assert.equal(outcome.phase, "not_found");
});

test("fixture fx-pending keeps polling until the budget runs out", async () => {
  let updates = 0;
  const outcome = await withFixtures(async () =>
    outcomeFromPoll(await pollResult("fx-pending", { intervalMs: 5, maxMs: 60, onUpdate: () => (updates += 1) })),
  );
  assert.equal(outcome.phase, "timeout");
  assert.equal(outcome.data.status, "pending");
  assert.ok(updates >= 2, `polled ${updates} times`);
});
