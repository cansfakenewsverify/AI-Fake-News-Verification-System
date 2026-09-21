import { test } from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { t } from "../../i18n.js";
import { HOT_LIMIT, TRENDING_TABS, hotCountText, tabFromSearch } from "./hotModel.js";

// Trending page tabs and the "本站熱門查證" tab (GET /api/knowledge/hot).

test("tabs: feed first (default), hot second, labels come from i18n", () => {
  assert.deepEqual(TRENDING_TABS.map((tab) => tab.value), ["feed", "hot"]);
  assert.equal(t(TRENDING_TABS[0].labelKey), "查核機構最新");
  assert.equal(t(TRENDING_TABS[1].labelKey), "本站熱門查證");
  assert.equal(HOT_LIMIT, 10);
});

test("tabFromSearch: only ?tab=hot opens the hot tab", () => {
  assert.equal(tabFromSearch("tab=hot"), "hot");
  assert.equal(tabFromSearch("?tab=hot&fixture=empty"), "hot");
  assert.equal(tabFromSearch("fixture=empty&tab=hot"), "hot");
  for (const search of ["", "?tab=feed", "?tab=HOT", "?tab=", "tab=other", undefined, null, 5]) {
    assert.equal(tabFromSearch(search), "feed", String(search));
  }
});

test("hotCountText: recent counts, malformed values read as 0", () => {
  assert.equal(hotCountText({ recent_24h: 12, recent_7d: 41 }), "近 24 小時 12 次・近 7 天 41 次");
  assert.equal(hotCountText({ recent_24h: "3", recent_7d: 3.9 }), "近 24 小時 3 次・近 7 天 3 次");
  assert.equal(hotCountText({ recent_24h: -1, recent_7d: "x" }), "近 24 小時 0 次・近 7 天 0 次");
  assert.equal(hotCountText(null), "近 24 小時 0 次・近 7 天 0 次");
});

test("hot fixtures follow the /api/knowledge/hot response shape", async () => {
  const read = async (name) =>
    JSON.parse(await readFile(new URL(`../../dev/fixtures/${name}`, import.meta.url), "utf8"));
  const hot = await read("knowledge_hot.json");
  assert.equal(hot.window_days, 7);
  assert.equal(hot.total, hot.records.length);
  assert.ok(hot.records.length > 0);
  for (const record of hot.records) {
    assert.equal(typeof record.id, "string");
    assert.ok(["SCAM", "MISINFO", "SAFE"].includes(record.risk_type));
    assert.ok(Number.isInteger(record.recent_24h) && Number.isInteger(record.recent_7d));
    assert.ok(record.recent_24h <= record.recent_7d);
    assert.ok(record.sources.every((s) => s.tier === 1 || s.tier === 2)); // verified rows only
  }
  const empty = await read("knowledge_hot_empty.json");
  assert.deepEqual(empty.records, []);
  assert.equal(empty.total, 0);
});
