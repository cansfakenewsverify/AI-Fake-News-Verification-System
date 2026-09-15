import { displayHost, httpUrl } from "../../lib/httpUrl.js";
import { tierCaption } from "../../lib/verdict.js";

// Pure helpers for the knowledge page (S-10; spec 8.3 S4, FR-07, FR-16, FR-17). Testable with node --test.
// Report-week cut (tickets 0.5 / 9.3): one GET /api/knowledge?limit=60&offset=0 per search / filter;
// no "load more" and no four-number stats bar.

export const KNOWLEDGE_LIMIT = 60;

// Single-select verdict filter chips (8.3 S4); clicking the selected chip clears the filter.
export const KNOWLEDGE_FILTERS = [
  { riskType: "SCAM", labelKey: "dot_scam" },
  { riskType: "MISINFO", labelKey: "dot_misinfo" },
  { riskType: "SAFE", labelKey: "dot_safe" },
  { riskType: "UNVERIFIABLE", labelKey: "frame_yellow_unverifiable" },
];

export function toggleRiskFilter(current, clicked) {
  return current === clicked ? "" : clicked;
}

/** Query params for getKnowledge(): empty q / risk_type are left out of the URL. */
export function knowledgeQuery({ q = "", riskType = "" } = {}) {
  const query = { limit: KNOWLEDGE_LIMIT, offset: 0 };
  const keyword = String(q ?? "").trim();
  if (keyword) query.q = keyword;
  if (riskType) query.risk_type = riskType;
  return query;
}

/**
 * Records to render. Guards on top of the server (which already does both):
 * - verified === false never renders (FR-17: the page must not show unverified rows);
 * - an active filter keeps only its exact risk_type (same comparison as the server), which also keeps
 *   fixture mode honest because fixture files ignore query parameters.
 */
export function visibleKnowledgeRecords(data, riskType = "") {
  const list = Array.isArray(data?.records) ? data.records : [];
  const wanted = String(riskType || "").toUpperCase();
  return list.filter(
    (record) =>
      record &&
      typeof record === "object" &&
      record.verified !== false &&
      (!wanted || String(record.risk_type ?? "").toUpperCase() === wanted),
  );
}

/** Host of the first Tier 1/2 source with an http(s) URL (FR-16: Tier 3 never shows), or null. */
export function firstVerifiedSourceDomain(sources) {
  if (!Array.isArray(sources)) return null;
  for (const source of sources) {
    if (!source || !tierCaption(source.tier)) continue;
    const url = httpUrl(source.url);
    if (url) return displayHost(url) || null;
  }
  return null;
}

/** In-app result link when the row remembers its last result id (FR-07 acceptance 4), else null. */
export function knowledgeLink(record) {
  const id = record?.last_result_id;
  return typeof id === "string" && id.trim() ? `/r/${encodeURIComponent(id.trim())}` : null;
}

/** hit_count as a non-negative integer, or null when missing / not a number. */
export function hitCountOf(record) {
  const value = record?.hit_count;
  if (value === null || value === undefined || value === "") return null;
  const n = Number(value);
  return Number.isFinite(n) && n >= 0 ? Math.floor(n) : null;
}

/**
 * Empty-result message (8.3 S4): a submitted keyword -> knowledge_no_match with {q};
 * a filter without keyword -> filter_empty; nothing at all -> knowledge_empty.
 */
export function emptyMessage({ q = "", riskType = "" } = {}) {
  const keyword = String(q ?? "").trim();
  if (keyword) return { key: "knowledge_no_match", params: { q: keyword } };
  if (riskType) return { key: "filter_empty", params: {} };
  return { key: "knowledge_empty", params: {} };
}
