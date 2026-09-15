import { t } from "../../i18n.js";
import { httpUrl } from "../../lib/httpUrl.js";
import { isBlockedSourceUrl } from "./sourceOrgName.js";

// Pure helpers for the trending page (S-09; spec 8.3 S3, FR-06). No React, testable with node --test.
// Report-week cut (tickets 0.5 / 9.3): the filter chips are only "all" and "pending"; one
// GET /api/trending?limit=20 without risk_type feeds both, and "pending" filters on the client.

export const TRENDING_LIMIT = 20;

export const TRENDING_FILTERS = [
  { id: "all", labelKey: "filter_all" },
  { id: "pending", labelKey: "chip_pending" },
];

const COLOURED_RISKS = ["SCAM", "MISINFO", "SAFE"];

/**
 * Card shows the grey chip_pending and no red/yellow/green: PENDING, UNVERIFIABLE, missing or unknown
 * risk_type, or verified === false (FR-06 acceptance 6). Same rule as listVerdict() without frame_type,
 * so the "pending" filter keeps exactly the cards that display the grey chip.
 */
export function isUnverifiedRecord(record) {
  if (!record || typeof record !== "object") return true;
  return record.verified === false || !COLOURED_RISKS.includes(record.risk_type);
}

export function applyTrendingFilter(records, filterId) {
  const list = Array.isArray(records) ? records : [];
  return filterId === "pending" ? list.filter(isUnverifiedRecord) : list;
}

/**
 * Backend timestamps come from datetime.utcnow().isoformat() without an offset: treat them as UTC.
 * Accepts "YYYY-MM-DDTHH:mm:ss[.ffffff]" or a space separator; fractions are cut to milliseconds
 * (Safari rejects longer fractions). Returns a Date or null.
 */
export function parseServerTime(value) {
  if (typeof value !== "string") return null;
  let s = value.trim();
  const m = s.match(/^(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2}(?::\d{2})?)(\.\d+)?(Z|[+-]\d{2}:?\d{2})?$/i);
  if (!m) return null;
  const fraction = m[3] ? m[3].slice(0, 4).padEnd(4, "0") : "";
  let zone = m[4] ? m[4].toUpperCase() : "Z";
  if (/^[+-]\d{4}$/.test(zone)) zone = `${zone.slice(0, 3)}:${zone.slice(3)}`;
  s = `${m[1]}T${m[2]}${fraction}${zone}`;
  const date = new Date(s);
  return Number.isNaN(date.getTime()) ? null : date;
}

/** Newest created_at of the list (FR-06 acceptance 3: "data updated at"), or null. */
export function latestCreatedAt(records) {
  let latest = null;
  for (const record of Array.isArray(records) ? records : []) {
    const date = parseServerTime(record?.created_at);
    if (date && (!latest || date.getTime() > latest.getTime())) latest = date;
  }
  return latest;
}

function pad2(n) {
  return String(n).padStart(2, "0");
}

/** Local calendar date "YYYY-MM-DD" (Trending.dc.html card date). */
export function formatDate(date) {
  if (!(date instanceof Date) || Number.isNaN(date.getTime())) return "";
  return `${date.getFullYear()}-${pad2(date.getMonth() + 1)}-${pad2(date.getDate())}`;
}

/** Local "YYYY-MM-DD HH:mm" (Trending.dc.html trending_updated). */
export function formatDateTime(date) {
  const day = formatDate(date);
  return day ? `${day} ${pad2(date.getHours())}:${pad2(date.getMinutes())}` : "";
}

/**
 * {scheduler_state} for trending_sub from GET /api/health (spec 5.1 scheduler block):
 * enabled with a positive interval -> scheduler_on; enabled false -> scheduler_off;
 * health not loaded / malformed -> "" (the sentence ends after the source list).
 */
export function schedulerStateText(health) {
  const scheduler = health?.scheduler;
  if (!scheduler || typeof scheduler !== "object") return "";
  if (scheduler.enabled === false) return t("scheduler_off");
  const hours = Number(scheduler.interval_hours);
  if (scheduler.enabled === true && Number.isFinite(hours) && hours > 0) return t("scheduler_on", { n: hours });
  return "";
}

/**
 * Card target (FR-06 acceptance 5): result_id -> in-app /r/{id}; otherwise the http(s) source_url opens
 * in a new tab; Google News redirects and non-http(s) values are never linked (returns null).
 */
export function trendingLink(record) {
  const id = record?.result_id;
  if (typeof id === "string" && id.trim()) return { to: `/r/${encodeURIComponent(id.trim())}` };
  const url = httpUrl(record?.source_url);
  if (url && !isBlockedSourceUrl(record.source_url)) return { href: url.href };
  return null;
}

export function trendingTitle(record) {
  for (const key of ["news_title", "ai_summary"]) {
    const value = record?.[key];
    if (typeof value === "string" && value.trim()) return value.trim();
  }
  return "";
}
