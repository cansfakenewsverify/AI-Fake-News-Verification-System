import { test } from "node:test";
import assert from "node:assert/strict";
import { ApiError } from "../../lib/api.js";
import { HEALTH_RETRY_MS, isBackendDownError, startHealthRetry } from "./useBackendStatus.js";

// 「後端不可用」橫幅的判定（P-14）：只有真的連不上／閘道錯誤才顯示。

test("network and timeout errors mean backend down", () => {
  assert.equal(isBackendDownError(new ApiError({ kind: "network" })), true);
  assert.equal(isBackendDownError(new ApiError({ kind: "timeout" })), true);
});

test("5xx from proxy or tunnel means backend down", () => {
  for (const status of [500, 502, 503, 504, 530]) {
    assert.equal(isBackendDownError(new ApiError({ kind: "http", status })), true, String(status));
  }
});

test("4xx means the request reached the backend", () => {
  assert.equal(isBackendDownError(new ApiError({ kind: "http", status: 404 })), false);
  assert.equal(isBackendDownError(new ApiError({ kind: "http", status: 429 })), false);
});

test("abort and non-ApiError values are ignored", () => {
  const abort = new Error("The operation was aborted.");
  abort.name = "AbortError";
  assert.equal(isBackendDownError(abort), false);
  assert.equal(isBackendDownError(undefined), false);
});

// 橫幅顯示期間的自動重試（雲端主機休眠後喚醒約 1 分鐘）

function fakeTimers() {
  const state = { tick: null, intervalMs: null, cleared: [] };
  return {
    state,
    setInterval(fn, ms) {
      state.tick = fn;
      state.intervalMs = ms;
      return 42;
    },
    clearInterval(id) {
      state.cleared.push(id);
    },
  };
}

const flush = () => new Promise((resolve) => setTimeout(resolve, 0));

test("health retry polls every 10 seconds and stops when asked", async () => {
  const timers = fakeTimers();
  let calls = 0;
  const stop = startHealthRetry(async () => { calls += 1; }, { timers });
  assert.equal(timers.state.intervalMs, HEALTH_RETRY_MS);
  assert.equal(HEALTH_RETRY_MS, 10000);
  assert.equal(calls, 0, "does not fire immediately: the failed request just happened");

  timers.state.tick();
  await flush();
  timers.state.tick();
  await flush();
  assert.equal(calls, 2);

  stop();
  assert.deepEqual(timers.state.cleared, [42]);
});

test("health retry skips a round while the previous check is still pending", async () => {
  const timers = fakeTimers();
  let calls = 0;
  let release;
  startHealthRetry(() => {
    calls += 1;
    return new Promise((resolve) => { release = resolve; });
  }, { timers });

  timers.state.tick();
  await flush();
  timers.state.tick();
  await flush();
  assert.equal(calls, 1);

  release();
  await flush();
  timers.state.tick();
  await flush();
  assert.equal(calls, 2);
});

test("health retry survives a failing check", async () => {
  const timers = fakeTimers();
  let calls = 0;
  startHealthRetry(() => {
    calls += 1;
    throw new Error("still down");
  }, { timers });
  timers.state.tick();
  await flush();
  timers.state.tick();
  await flush();
  assert.equal(calls, 2);
});
