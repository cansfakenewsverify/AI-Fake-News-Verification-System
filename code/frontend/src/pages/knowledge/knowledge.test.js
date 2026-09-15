import { test } from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { t } from "../../i18n.js";
import { configureFixtures, getKnowledge } from "../../lib/api.js";
import {
  KNOWLEDGE_FILTERS,
  KNOWLEDGE_LIMIT,
  emptyMessage,
  firstVerifiedSourceDomain,
  hitCountOf,
  knowledgeLink,
  knowledgeQuery,
  toggleRiskFilter,
  visibleKnowledgeRecords,
} from "./knowledgeModel.js";

// S-10 knowledge page helpers (spec 8.3 S4, FR-07, FR-16, FR-17).

async function fixture(name) {
  return JSON.parse(await readFile(new URL(`../../dev/fixtures/${name}`, import.meta.url), "utf8"));
}

test("filter chips: SCAM / MISINFO / SAFE / UNVERIFIABLE with 8.7 wording", () => {
  assert.deepEqual(
    KNOWLEDGE_FILTERS.map((item) => item.riskType),
    ["SCAM", "MISINFO", "SAFE", "UNVERIFIABLE"],
  );
  assert.deepEqual(
    KNOWLEDGE_FILTERS.map((item) => t(item.labelKey)),
    ["詐騙", "假訊息", "安全", "無法查證"],
  );
});

test("toggleRiskFilter is single select and clears on a second click", () => {
  assert.equal(toggleRiskFilter("", "SCAM"), "SCAM");
  assert.equal(toggleRiskFilter("SCAM", "SAFE"), "SAFE");
  assert.equal(toggleRiskFilter("SAFE", "SAFE"), "");
});

test("knowledgeQuery: one request with limit=60 and offset=0 (report-week cut)", () => {
  assert.equal(KNOWLEDGE_LIMIT, 60);
  assert.deepEqual(knowledgeQuery(), { limit: 60, offset: 0 });
  assert.deepEqual(knowledgeQuery({ q: "  健保  ", riskType: "SCAM" }), {
    limit: 60,
    offset: 0,
    q: "健保",
    risk_type: "SCAM",
  });
  assert.deepEqual(knowledgeQuery({ q: "   ", riskType: "" }), { limit: 60, offset: 0 });
});

test("getKnowledge encodes special characters in q through URLSearchParams (FN-8 front end)", async () => {
  const calls = [];
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (url) => {
    calls.push(String(url));
    return { ok: true, status: 200, headers: { get: () => null }, text: async () => '{"total":0,"records":[]}' };
  };
  configureFixtures(null);
  const keywords = ["(", "[", "*", "a&b=c", "健保 卡"];
  try {
    for (const q of keywords) {
      await getKnowledge(knowledgeQuery({ q }));
    }
  } finally {
    globalThis.fetch = originalFetch;
  }
  assert.equal(calls.length, keywords.length);
  calls.forEach((url, index) => {
    const parsed = new URL(url, "http://localhost");
    assert.equal(parsed.pathname, "/api/knowledge");
    assert.equal(parsed.searchParams.get("q"), keywords[index]); // round-trips exactly
    assert.equal(parsed.searchParams.get("limit"), "60");
    assert.equal(parsed.searchParams.get("offset"), "0");
    assert.equal(parsed.searchParams.get("risk_type"), null);
  });
  assert.ok(calls[0].includes("q=%28"));
  assert.ok(calls[1].includes("q=%5B"));
  assert.ok(calls[3].includes("q=a%26b%3Dc"));
});

test("visibleKnowledgeRecords drops verified=false rows and applies the exact risk filter", async () => {
  const data = await fixture("knowledge_page1.json");
  assert.equal(visibleKnowledgeRecords(data).length, data.records.length);
  assert.deepEqual(
    visibleKnowledgeRecords(data, "UNVERIFIABLE").map((r) => r.id),
    ["kb-fx-05"],
  );
  assert.equal(visibleKnowledgeRecords(data, "SCAM").length, 3);
  assert.deepEqual(
    visibleKnowledgeRecords({ records: [{ id: "a", risk_type: "SAFE", verified: false }, { id: "b", risk_type: "SAFE" }] }).map(
      (r) => r.id,
    ),
    ["b"],
  );
  assert.deepEqual(visibleKnowledgeRecords(null), []);
  assert.deepEqual(visibleKnowledgeRecords({ records: [null, 3, "x"] }), []);
});

test("firstVerifiedSourceDomain returns the first Tier 1/2 host and never a Tier 3 one", async () => {
  const data = await fixture("knowledge_page1.json");
  const byId = Object.fromEntries(data.records.map((r) => [r.id, r]));
  assert.equal(firstVerifiedSourceDomain(byId["kb-fx-01"].sources), "tfc-taiwan.org.tw");
  assert.equal(firstVerifiedSourceDomain(byId["kb-fx-06"].sources), "news.cts.com.tw");
  assert.equal(firstVerifiedSourceDomain(byId["kb-fx-07"].sources), "165.npa.gov.tw");
  assert.equal(firstVerifiedSourceDomain(byId["kb-fx-05"].sources), null);
  assert.equal(firstVerifiedSourceDomain([{ url: "https://www.mygopen.com/x" }]), null); // no tier -> hidden
  assert.equal(firstVerifiedSourceDomain([{ tier: 1, url: "javascript:alert(1)" }]), null);
  assert.equal(firstVerifiedSourceDomain([{ tier: "2", url: "https://www.ettoday.net/a" }]), "ettoday.net");
  assert.equal(firstVerifiedSourceDomain(null), null);
});

test("knowledgeLink: last_result_id -> /r/{id}, otherwise null", () => {
  assert.equal(knowledgeLink({ last_result_id: "fx-red-misinfo" }), "/r/fx-red-misinfo");
  assert.equal(knowledgeLink({ last_result_id: "a/b" }), "/r/a%2Fb");
  assert.equal(knowledgeLink({ last_result_id: null }), null);
  assert.equal(knowledgeLink({ last_result_id: "  " }), null);
  assert.equal(knowledgeLink(undefined), null);
});

test("hitCountOf keeps non-negative numbers only", () => {
  assert.equal(hitCountOf({ hit_count: 37 }), 37);
  assert.equal(hitCountOf({ hit_count: "12" }), 12);
  assert.equal(hitCountOf({ hit_count: 0 }), 0);
  assert.equal(hitCountOf({ hit_count: -1 }), null);
  assert.equal(hitCountOf({ hit_count: null }), null);
  assert.equal(hitCountOf({}), null);
  assert.equal(t("hit_count", { n: hitCountOf({ hit_count: 37 }) }), "命中 37 次");
});

test("emptyMessage: keyword -> knowledge_no_match with q; filter only -> filter_empty; else knowledge_empty", () => {
  const noMatch = emptyMessage({ q: " ( ", riskType: "SCAM" });
  assert.deepEqual(noMatch, { key: "knowledge_no_match", params: { q: "(" } });
  assert.equal(t(noMatch.key, noMatch.params), "找不到符合「(」的資料，試試其他關鍵字，或直接貼到首頁查證。");
  assert.deepEqual(emptyMessage({ q: "", riskType: "UNVERIFIABLE" }), { key: "filter_empty", params: {} });
  assert.deepEqual(emptyMessage(), { key: "knowledge_empty", params: {} });
  assert.equal(t("knowledge_empty"), "知識庫是空的。");
});

test("fixture knowledge_empty has no records", async () => {
  const data = await fixture("knowledge_empty.json");
  assert.deepEqual(visibleKnowledgeRecords(data), []);
});
