import { test } from "node:test";
import assert from "node:assert/strict";
import {
  HISTORY_KEY,
  addEntry,
  updateEntry,
  listRecent,
  listAll,
  clearAll,
  isAvailable,
  relativeTime,
} from "./history.js";

function memStorage(init = {}) {
  const data = { ...init };
  return {
    data,
    getItem: (k) => (k in data ? data[k] : null),
    setItem: (k, v) => { data[k] = String(v); },
    removeItem: (k) => { delete data[k]; },
  };
}

const throwingStorage = {
  getItem() { throw new Error("SecurityError"); },
  setItem() { throw new Error("SecurityError"); },
  removeItem() { throw new Error("SecurityError"); },
};

const entry = (i) => ({ id: `r${i}`, input_type: "text", preview: `內容 ${i}`, created_at: "2026-09-15T00:00:00Z" });

test("adding 51 entries keeps 50 with newest first", () => {
  const s = memStorage();
  for (let i = 1; i <= 51; i++) addEntry(entry(i), s);
  const all = listAll(s);
  assert.equal(all.length, 50);
  assert.equal(all[0].id, "r51");
  assert.equal(all[49].id, "r2");
  assert.equal(JSON.parse(s.data[HISTORY_KEY]).length, 50);
});

test("duplicate id is not duplicated and moves to front", () => {
  const s = memStorage();
  addEntry(entry(1), s);
  addEntry(entry(2), s);
  addEntry({ ...entry(1), preview: "新的" }, s);
  const all = listAll(s);
  assert.equal(all.length, 2);
  assert.equal(all[0].id, "r1");
  assert.equal(all[0].preview, "新的");
});

test("preview of 81 chars is truncated to 80", () => {
  const s = memStorage();
  addEntry({ ...entry(1), preview: "字".repeat(81) }, s);
  assert.equal(Array.from(listRecent(5, s)[0].preview).length, 80);
});

test("new entry starts with null risk_type/frame_type", () => {
  const s = memStorage();
  addEntry(entry(1), s);
  const e = listRecent(5, s)[0];
  assert.equal(e.risk_type, null);
  assert.equal(e.frame_type, null);
  assert.deepEqual(Object.keys(e).sort(), ["created_at", "frame_type", "id", "input_type", "preview", "risk_type"]);
});

test("updateEntry writes back frame_type", () => {
  const s = memStorage();
  addEntry(entry(1), s);
  assert.equal(updateEntry("r1", { risk_type: "SCAM", frame_type: "red" }, s), true);
  assert.equal(listRecent(undefined, s)[0].frame_type, "red");
  assert.equal(listRecent(undefined, s)[0].risk_type, "SCAM");
  assert.equal(updateEntry("missing", { frame_type: "green" }, s), false);
});

test("listRecent defaults to 5", () => {
  const s = memStorage();
  for (let i = 1; i <= 8; i++) addEntry(entry(i), s);
  const recent = listRecent(undefined, s);
  assert.equal(recent.length, 5);
  assert.equal(recent[0].id, "r8");
});

test("throwing storage: listRecent returns [] and isAvailable false without throwing", () => {
  assert.deepEqual(listRecent(5, throwingStorage), []);
  assert.equal(isAvailable(throwingStorage), false);
  assert.doesNotThrow(() => addEntry(entry(1), throwingStorage));
  assert.doesNotThrow(() => updateEntry("r1", { frame_type: "red" }, throwingStorage));
  assert.equal(clearAll(throwingStorage), false);
});

test("missing storage is treated as unavailable", () => {
  assert.equal(isAvailable(null), false);
  assert.deepEqual(listRecent(5, null), []);
});

test("isAvailable true for working storage", () => {
  assert.equal(isAvailable(memStorage()), true);
});

test("corrupted JSON returns [] and is overwritten", () => {
  const s = memStorage({ [HISTORY_KEY]: "{not json" });
  assert.deepEqual(listRecent(5, s), []);
  assert.equal(s.data[HISTORY_KEY], "[]");
});

test("non-array JSON returns [] and is overwritten", () => {
  const s = memStorage({ [HISTORY_KEY]: '{"id":"x"}' });
  assert.deepEqual(listRecent(5, s), []);
  assert.equal(s.data[HISTORY_KEY], "[]");
});

test("clearAll empties history", () => {
  const s = memStorage();
  addEntry(entry(1), s);
  assert.equal(clearAll(s), true);
  assert.deepEqual(listRecent(5, s), []);
});

test("relativeTime buckets", () => {
  const now = new Date("2026-09-15T12:00:00Z");
  assert.equal(relativeTime("2026-09-15T11:59:30Z", now), "剛剛");
  assert.equal(relativeTime("2026-09-15T12:05:00Z", now), "剛剛");
  assert.equal(relativeTime("2026-09-15T11:57:00Z", now), "3 分鐘前");
  assert.equal(relativeTime("2026-09-15T09:00:00Z", now), "3 小時前");
  const old = new Date(2026, 8, 3, 8, 0, 0); // 本地時區 9/3
  assert.equal(relativeTime(old.toISOString(), now), "9/3");
  assert.equal(relativeTime("not a date", now), "");
});
