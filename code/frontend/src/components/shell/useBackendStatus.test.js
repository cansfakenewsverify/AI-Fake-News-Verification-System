import { test } from "node:test";
import assert from "node:assert/strict";
import { ApiError } from "../../lib/api.js";
import { isBackendDownError } from "./useBackendStatus.js";

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
