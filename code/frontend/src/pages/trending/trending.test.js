import { test } from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { t } from "../../i18n.js";
import { TRENDING_COPY } from "./copy.js";
import { isBlockedSourceUrl, sourceOrgName } from "./sourceOrgName.js";
import {
  TRENDING_FILTERS,
  TRENDING_LIMIT,
  applyTrendingFilter,
  formatDate,
  formatDateTime,
  isUnverifiedRecord,
  latestCreatedAt,
  parseServerTime,
  schedulerStateText,
  trendingLink,
  trendingTitle,
} from "./trendingModel.js";

// S-09 trending wall helpers (spec 8.3 S3, FR-06).

async function fixture(name) {
  return JSON.parse(await readFile(new URL(`../../dev/fixtures/${name}`, import.meta.url), "utf8"));
}

test("sourceOrgName maps the three fact-check organisations and falls back to the hostname", () => {
  assert.equal(sourceOrgName("https://www.mygopen.com/2026/07/typhoon.html"), TRENDING_COPY.org_mygopen);
  assert.equal(sourceOrgName("https://mygopen.com/x"), TRENDING_COPY.org_mygopen);
  assert.equal(sourceOrgName("https://tfc-taiwan.org.tw/articles/1"), TRENDING_COPY.org_tfc);
  assert.equal(sourceOrgName("https://cofacts.tw/article/3u6kcbs39j617"), TRENDING_COPY.org_cofacts);
  assert.equal(sourceOrgName("https://cofacts.g0v.tw/article/abc"), TRENDING_COPY.org_cofacts);
  assert.equal(sourceOrgName("https://news.cts.com.tw/cts/life/202609/1.html"), "news.cts.com.tw");
  assert.equal(sourceOrgName("https://www.ettoday.net/news/1.htm"), "ettoday.net");
  // look-alike hosts are shown as they are, never as the organisation
  assert.equal(sourceOrgName("https://evil-mygopen.com/x"), "evil-mygopen.com");
  assert.equal(sourceOrgName("https://mygopen.com.evil.io/x"), "mygopen.com.evil.io");
});

test("sourceOrgName never shows Google News redirects or non-http(s) values", () => {
  const google = "https://news.google.com/rss/articles/CBMiabc?oc=5";
  assert.equal(isBlockedSourceUrl(google), true);
  assert.equal(sourceOrgName(google), null);
  assert.equal(isBlockedSourceUrl("https://www.mygopen.com/x"), false);
  for (const bad of [null, undefined, "", "javascript:alert(1)", "not a url"]) {
    assert.equal(sourceOrgName(bad), null, String(bad));
  }
});

test("filter chips are only all / pending (report-week cut) and the request limit is 20", () => {
  assert.deepEqual(
    TRENDING_FILTERS.map((item) => item.id),
    ["all", "pending"],
  );
  assert.equal(t(TRENDING_FILTERS[0].labelKey), "全部");
  assert.equal(t(TRENDING_FILTERS[1].labelKey), "未查證");
  assert.equal(TRENDING_LIMIT, 20);
});

test("isUnverifiedRecord: PENDING, UNVERIFIABLE, unknown risk or verified=false", () => {
  assert.equal(isUnverifiedRecord({ risk_type: "SCAM", verified: true }), false);
  assert.equal(isUnverifiedRecord({ risk_type: "SAFE" }), false);
  assert.equal(isUnverifiedRecord({ risk_type: "MISINFO", verified: false }), true);
  assert.equal(isUnverifiedRecord({ risk_type: "SAFE", verified: false }), true);
  assert.equal(isUnverifiedRecord({ risk_type: "UNVERIFIABLE", verified: true }), true);
  assert.equal(isUnverifiedRecord({ risk_type: "PENDING" }), true);
  assert.equal(isUnverifiedRecord({ risk_type: null }), true);
  assert.equal(isUnverifiedRecord({ risk_type: "UNKNOWN", verified: true }), true);
  assert.equal(isUnverifiedRecord(null), true);
});

test("fixture trending_ok: 6 cards, the pending filter keeps exactly the verified=false and UNVERIFIABLE ones", async () => {
  const data = await fixture("trending_ok.json");
  assert.equal(data.records.length, 6);
  assert.equal(data.records.filter((r) => r.verified === false).length, 1);
  assert.equal(data.records.filter((r) => r.risk_type === "UNVERIFIABLE").length, 1);
  assert.equal(applyTrendingFilter(data.records, "all").length, 6);
  assert.deepEqual(
    applyTrendingFilter(data.records, "pending").map((r) => r.id),
    ["tr-fx-05", "tr-fx-06"],
  );
  assert.ok(!JSON.stringify(data).includes("news.google.com"));
});

test("pending filter on an all-verified list is empty (filter_empty state)", () => {
  const records = [
    { id: "a", risk_type: "MISINFO", verified: true },
    { id: "b", risk_type: "SCAM", verified: true },
  ];
  assert.deepEqual(applyTrendingFilter(records, "pending"), []);
  assert.deepEqual(applyTrendingFilter(null, "all"), []);
});

test("fixture trending_empty has no records", async () => {
  const data = await fixture("trending_empty.json");
  assert.deepEqual(data.records, []);
});

test("parseServerTime treats offset-less backend timestamps as UTC", () => {
  assert.equal(parseServerTime("2026-09-15T00:30:00.123456")?.toISOString(), "2026-09-15T00:30:00.123Z");
  assert.equal(parseServerTime("2026-07-12 10:42:42.666072")?.toISOString(), "2026-07-12T10:42:42.666Z");
  assert.equal(parseServerTime("2026-07-12T10:42:42")?.toISOString(), "2026-07-12T10:42:42.000Z");
  assert.equal(parseServerTime("2026-07-12T10:42:42.5Z")?.toISOString(), "2026-07-12T10:42:42.500Z");
  assert.equal(parseServerTime("2026-09-15T08:30:00+08:00")?.toISOString(), "2026-09-15T00:30:00.000Z");
  assert.equal(parseServerTime("2026-09-15T08:30:00+0800")?.toISOString(), "2026-09-15T00:30:00.000Z");
  for (const bad of [null, undefined, "", "yesterday", "2026-13-45T99:99:99", 1726360000000]) {
    assert.equal(parseServerTime(bad), null, String(bad));
  }
});

test("latestCreatedAt picks the newest valid created_at", async () => {
  const data = await fixture("trending_ok.json");
  assert.equal(latestCreatedAt(data.records)?.toISOString(), "2026-09-15T00:30:00.123Z");
  assert.equal(latestCreatedAt([{ created_at: "bad" }, { created_at: null }]), null);
  assert.equal(latestCreatedAt([]), null);
});

test("formatDate / formatDateTime use the local calendar with zero padding", () => {
  const date = new Date(2026, 8, 5, 7, 3, 59);
  assert.equal(formatDate(date), "2026-09-05");
  assert.equal(formatDateTime(date), "2026-09-05 07:03");
  assert.equal(formatDate(new Date("bad")), "");
  assert.equal(formatDateTime(null), "");
});

test("schedulerStateText reads the /api/health scheduler block", async () => {
  const health = await fixture("health_ok.json");
  assert.equal(schedulerStateText(health), t("scheduler_off"));
  assert.equal(schedulerStateText({ scheduler: { enabled: true, interval_hours: 6 } }), "每 6 小時自動更新");
  assert.equal(schedulerStateText({ scheduler: { enabled: false, interval_hours: 6 } }), "目前為手動更新");
  assert.equal(schedulerStateText({ scheduler: { enabled: true } }), "");
  assert.equal(schedulerStateText(null), "");
  assert.equal(schedulerStateText({ status: "healthy" }), "");
  assert.equal(
    t("trending_sub", { scheduler_state: schedulerStateText(health) }),
    "來源：MyGoPen、台灣事實查核中心、Cofacts。目前為手動更新",
  );
  // health not loaded yet: no raw placeholder leaks into the page
  assert.ok(!t("trending_sub", { scheduler_state: schedulerStateText(null) }).includes("{"));
});

test("trendingLink: result_id -> /r/{id}; else http(s) source_url; never Google News", () => {
  assert.deepEqual(trendingLink({ result_id: "fx-green-cache-vector", source_url: "https://cofacts.tw/a" }), {
    to: "/r/fx-green-cache-vector",
  });
  assert.deepEqual(trendingLink({ result_id: "a/b c" }), { to: "/r/a%2Fb%20c" });
  assert.deepEqual(trendingLink({ result_id: null, source_url: "https://www.mygopen.com/x.html" }), {
    href: "https://www.mygopen.com/x.html",
  });
  assert.equal(trendingLink({ source_url: "https://news.google.com/rss/articles/abc" }), null);
  assert.equal(trendingLink({ source_url: "javascript:alert(1)" }), null);
  assert.equal(trendingLink({ result_id: "  ", source_url: "" }), null);
  assert.equal(trendingLink(null), null);
});

test("trendingTitle prefers news_title and falls back to ai_summary", () => {
  assert.equal(trendingTitle({ news_title: "  title  ", ai_summary: "summary" }), "title");
  assert.equal(trendingTitle({ news_title: "", ai_summary: "summary" }), "summary");
  assert.equal(trendingTitle({}), "");
});
