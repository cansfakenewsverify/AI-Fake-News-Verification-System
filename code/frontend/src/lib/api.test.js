import { test, afterEach } from "node:test";
import assert from "node:assert/strict";
import {
  ApiError,
  FALLBACK_PREFIX,
  configureFixtures,
  getThreadsStatus,
  analyzeText,
  getKnowledge,
  getResult,
  getTrending,
  getHealth,
  isFallback,
  parseRetryAfter,
  pollResult,
  request,
} from "./api.js";

const realFetch = globalThis.fetch;
afterEach(() => {
  globalThis.fetch = realFetch;
  configureFixtures(null);
});

function jsonResponse(status, body, headers = {}) {
  return new Response(body === undefined ? null : JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json", ...headers },
  });
}

function mockFetch(handler) {
  const calls = [];
  globalThis.fetch = async (url, init) => {
    calls.push({ url, init });
    return handler(url, init, calls.length);
  };
  return calls;
}

test("getResult encodes id into /api/result path", async () => {
  const calls = mockFetch(() => jsonResponse(200, { id: "a/b", status: "pending" }));
  await getResult("a/b");
  assert.equal(calls[0].url, "/api/result/a%2Fb");
  assert.equal(calls[0].init.method, "GET");
});

test("never-responding fetch with timeoutMs:50 -> kind timeout", async () => {
  globalThis.fetch = () => new Promise(() => {});
  await assert.rejects(request("/api/trending", { timeoutMs: 50 }), (err) => {
    assert.ok(err instanceof ApiError);
    assert.equal(err.kind, "timeout");
    return true;
  });
});

test("fetch throwing TypeError -> kind network", async () => {
  globalThis.fetch = async () => {
    throw new TypeError("Failed to fetch");
  };
  await assert.rejects(getHealth(), (err) => {
    assert.ok(err instanceof ApiError);
    assert.equal(err.kind, "network");
    return true;
  });
});

test("422 with array detail -> message is string", async () => {
  mockFetch(() =>
    jsonResponse(422, {
      detail: [{ loc: ["body", "content"], msg: "String should have at least 1 character", type: "string_too_short" }],
      code: "validation_error",
    }),
  );
  await assert.rejects(analyzeText(""), (err) => {
    assert.equal(err.kind, "http");
    assert.equal(err.status, 422);
    assert.equal(err.code, "validation_error");
    assert.equal(typeof err.message, "string");
    assert.equal(err.message, "String should have at least 1 character");
    return true;
  });
});

test("422 prefers top-level message when backend supplies it", async () => {
  mockFetch(() => jsonResponse(422, { detail: [{ msg: "x" }], code: "validation_error", message: "請輸入內容" }));
  await assert.rejects(analyzeText(""), (err) => err.message === "請輸入內容");
});

test("404 -> code result_not_found (from body and when body lacks code)", async () => {
  mockFetch(() => jsonResponse(404, { detail: "找不到這筆查證", code: "result_not_found" }));
  await assert.rejects(getResult("x"), (err) => {
    assert.equal(err.code, "result_not_found");
    assert.equal(err.message, "找不到這筆查證");
    return true;
  });
  mockFetch(() => jsonResponse(404, { detail: "Not Found" }));
  await assert.rejects(getResult("x"), (err) => err.code === "result_not_found");
});

test("429 with Retry-After: 30 -> retryAfter === 30", async () => {
  mockFetch(() => jsonResponse(429, { detail: "查證太頻繁", code: "daily_cap_reached" }, { "Retry-After": "30" }));
  await assert.rejects(analyzeText("hi"), (err) => {
    assert.equal(err.status, 429);
    assert.equal(err.retryAfter, 30);
    return true;
  });
});

test("parseRetryAfter handles HTTP date and garbage", () => {
  const now = Date.parse("2026-09-16T00:00:00Z");
  assert.equal(parseRetryAfter("Wed, 16 Sep 2026 00:00:10 GMT", now), 10);
  assert.equal(parseRetryAfter("soon"), null);
  assert.equal(parseRetryAfter(null), null);
});

test("POST sends JSON body; query params skip empty values", async () => {
  const calls = mockFetch(() => jsonResponse(200, { records: [] }));
  await analyzeText("hello");
  assert.equal(calls[0].url, "/api/analyze/text");
  assert.equal(calls[0].init.method, "POST");
  assert.deepEqual(JSON.parse(calls[0].init.body), { content: "hello" });
  await getTrending({ limit: 10, risk_type: "" });
  assert.equal(calls[1].url, "/api/trending?limit=10");
  await getKnowledge({ q: "健保", limit: 30, offset: 30 });
  assert.equal(calls[2].url, `/api/knowledge?q=${encodeURIComponent("健保")}&limit=30&offset=30`);
});

test("external signal abort rejects with AbortError, not ApiError", async () => {
  globalThis.fetch = () => new Promise(() => {});
  const ac = new AbortController();
  const p = request("/api/trending", { signal: ac.signal, timeoutMs: 5000 });
  ac.abort();
  await assert.rejects(p, (err) => err.name === "AbortError" && !(err instanceof ApiError));
});

test("isFallback: ai_unavailable / prefix only / normal", () => {
  assert.equal(isFallback({ ai_unavailable: true }), true);
  assert.equal(isFallback({ summary: `${FALLBACK_PREFIX}（額度用盡）` }), true);
  assert.equal(isFallback({ ai_unavailable: false, summary: "這是詐騙訊息" }), false);
  assert.equal(isFallback({ status: "completed", ai_unavailable: true, result: {} }), true);
  assert.equal(isFallback(null), false);
});

test("pollResult stops on third response (completed); onUpdate called 3 times", async () => {
  const statuses = ["pending", "processing", "completed"];
  const calls = mockFetch((_url, _init, n) => jsonResponse(200, { id: "t1", status: statuses[n - 1] }));
  let updates = 0;
  const out = await pollResult("t1", { intervalMs: 5, maxMs: 5000, onUpdate: () => updates++ });
  assert.equal(calls.length, 3);
  assert.equal(updates, 3);
  assert.equal(out.timedOut, false);
  assert.equal(out.last.status, "completed");
});

test("pollResult stops on failed", async () => {
  mockFetch(() => jsonResponse(200, { id: "t2", status: "failed", error: { code: "analysis_failed" } }));
  const out = await pollResult("t2", { intervalMs: 5, maxMs: 5000 });
  assert.equal(out.timedOut, false);
  assert.equal(out.last.status, "failed");
});

test("pollResult returns timedOut when maxMs elapses", async () => {
  mockFetch(() => jsonResponse(200, { id: "t3", status: "processing" }));
  const out = await pollResult("t3", { intervalMs: 10, maxMs: 60 });
  assert.equal(out.timedOut, true);
  assert.equal(out.last.status, "processing");
});

test("pollResult throws result_not_found on 404", async () => {
  mockFetch(() => jsonResponse(404, { detail: "找不到這筆查證", code: "result_not_found" }));
  await assert.rejects(pollResult("nope", { intervalMs: 5, maxMs: 1000 }), (err) => err.code === "result_not_found");
});

test("pollResult is abortable", async () => {
  mockFetch(() => jsonResponse(200, { id: "t4", status: "pending" }));
  const ac = new AbortController();
  const p = pollResult("t4", { intervalMs: 1000, maxMs: 90000, signal: ac.signal });
  setTimeout(() => ac.abort(), 20);
  await assert.rejects(p, (err) => err.name === "AbortError");
});

// ---- fixture 模式（P-10）----------------------------------------------------

function fixtureLoader(files) {
  const asked = [];
  const loader = async (name) => {
    asked.push(name);
    return Object.prototype.hasOwnProperty.call(files, name) ? structuredClone(files[name]) : null;
  };
  return { loader, asked };
}

function noFetch() {
  globalThis.fetch = async () => {
    throw new Error("fetch must not be called in fixture mode");
  };
}

test("fixture mode: getResult('fx-pending') returns file content without fetch", async () => {
  noFetch();
  const pending = { id: "fx-pending", status: "pending", result: null };
  const { loader, asked } = fixtureLoader({ "result_fx-pending.json": pending });
  configureFixtures({ loader });
  const out = await getResult("fx-pending");
  assert.deepEqual(out, pending);
  assert.deepEqual(asked, ["result_fx-pending.json"]);
});

test("fixture mode: _status 429 + Retry-After -> ApiError retryAfter 30", async () => {
  noFetch();
  const { loader } = fixtureLoader({
    "analyze_text_ok.json": { detail: "查證太頻繁", code: "rate_limited", _status: 429, _headers: { "Retry-After": "30" } },
  });
  configureFixtures({ loader });
  await assert.rejects(analyzeText("hi"), (err) => {
    assert.ok(err instanceof ApiError);
    assert.equal(err.kind, "http");
    assert.equal(err.status, 429);
    assert.equal(err.code, "rate_limited");
    assert.equal(err.retryAfter, 30);
    return true;
  });
});

test("fixture mode: missing result file -> 404 result_not_found", async () => {
  noFetch();
  configureFixtures({ loader: fixtureLoader({}).loader });
  await assert.rejects(getResult("fx-anything"), (err) => err.status === 404 && err.code === "result_not_found");
});

test("fixture mode: path mapping rules", async () => {
  noFetch();
  const { loader, asked } = fixtureLoader({});
  configureFixtures({ loader, search: "?fixture=empty" });
  await getTrending({ limit: 10 }).catch(() => {});
  await getKnowledge({ offset: 0 }).catch(() => {});
  configureFixtures({ loader, search: "" });
  await getTrending().catch(() => {});
  await getKnowledge({ q: "x", offset: 60, limit: 30 }).catch(() => {});
  await getKnowledge().catch(() => {});
  await request("/api/knowledge/stats").catch(() => {});
  await getThreadsStatus().catch(() => {});
  await request("/api/threads/replies?limit=5").catch(() => {});
  await getHealth().catch(() => {});
  await analyzeText("hi").catch(() => {});
  configureFixtures({ loader, search: () => "?fixture=live" });
  await getThreadsStatus().catch(() => {});
  configureFixtures({ loader, search: "?fixture=analyze_url_invalid" });
  await request("/api/analyze/url", { method: "POST", body: { content: "x" } }).catch(() => {});
  assert.deepEqual(asked, [
    "trending_empty.json",
    "knowledge_empty.json",
    "trending_ok.json",
    "knowledge_page3.json",
    "knowledge_page1.json",
    "knowledge_stats.json",
    "threads_status_sim.json",
    "threads_replies.json",
    "health_ok.json",
    "analyze_text_ok.json",
    "threads_status_live.json",
    "analyze_url_invalid.json",
  ]);
});
