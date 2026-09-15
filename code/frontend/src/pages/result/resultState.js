// Result page state helpers (S-04..S-08; spec 5.3, 8.3 S2 states 1-10). Pure functions without JSX so
// node --test can import them. Page files stay free of Han characters: all copy comes from i18n.js.
// - The light colour is never derived here: pages pass the backend frame_type/frame_label through.
// - "AI unavailable" is decided by the ai_unavailable boolean only, never by the summary prefix.

import { ApiError } from "../../lib/api.js";
import { tierCaption } from "../../lib/verdict.js";

export const POLL_INTERVAL_MS = 2000; // spec 8.3 S2 state 1: poll every 2 s
export const POLL_MAX_MS = 90000; // ... for at most 90 s, then the timeout state

const GATEWAY_DOWN = new Set([502, 503, 504]);

/** pollResult() resolution -> {phase: "timeout" | "failed" | "completed", data}. */
export function outcomeFromPoll({ timedOut, last } = {}) {
  if (timedOut) return { phase: "timeout", data: last ?? null };
  if (last?.status === "failed") return { phase: "failed", data: last };
  return { phase: "completed", data: last ?? null };
}

/**
 * pollResult() rejection -> {phase, data: null, code?}
 *   404                                   -> "not_found"
 *   network / timeout / gateway 502-504   -> "network" (error_network + retry)
 *   anything else (e.g. 500)              -> "error" with the machine code or HTTP status
 */
export function outcomeFromError(err) {
  if (err instanceof ApiError) {
    if (err.status === 404 || err.code === "result_not_found") return { phase: "not_found", data: null };
    if (err.kind === "network" || err.kind === "timeout" || GATEWAY_DOWN.has(Number(err.status))) {
      return { phase: "network", data: null };
    }
    return { phase: "error", data: null, code: err.code || (err.status ? String(err.status) : "unknown") };
  }
  return { phase: "error", data: null, code: "unknown" };
}

/**
 * Which completed-result screen to show (spec 8.3 S2):
 *   "ai_unavailable" state 5 (grey card)  - decided by the ai_unavailable boolean only
 *   "unverifiable"   state 7 (yellow)     - risk_type UNVERIFIABLE (crawl failed, AI not called)
 *   "success"        states 3, 4, 10
 *   "invalid"        completed without a result object (the backend treats it as analysis_failed)
 */
export function resultView(data) {
  if (data?.ai_unavailable === true) return "ai_unavailable";
  const result = data?.result;
  if (!result || typeof result !== "object") return "invalid";
  if (result.risk_type === "UNVERIFIABLE") return "unverifiable";
  return "success";
}

/**
 * Source rows the page may list (FR-16): items of result.sources whose tier is 1 or 2. Anything else
 * (tier 3, missing tier, non-objects) is skipped defensively; the Tier 3 list is never read.
 */
export function visibleSources(result) {
  const sources = Array.isArray(result?.sources) ? result.sources : [];
  return sources.filter((source) => source && typeof source === "object" && tierCaption(source.tier) !== null);
}

/** error.code of a failed task (spec 5.3), analysis_failed when the body carries none. */
export function failureCode(data) {
  const code = data?.error?.code;
  return typeof code === "string" && code ? code : "analysis_failed";
}

/** history.updateEntry patch once the result is completed (FR-08: write back risk_type / frame_type). */
export function historyPatch(data) {
  const result = data?.result && typeof data.result === "object" ? data.result : null;
  return {
    risk_type: result?.risk_type ?? null,
    frame_type: result?.frame_type ?? (data?.ai_unavailable === true ? "grey" : null),
  };
}

const THREADS_HOSTS = ["threads.net", "threads.com"];

/** true for http(s) URLs on threads.net / threads.com or their subdomains (exact suffix match). */
export function isThreadsUrl(value) {
  if (typeof value !== "string" || !value.trim()) return false;
  let url;
  try {
    url = new URL(value.trim());
  } catch {
    return false;
  }
  if (url.protocol !== "http:" && url.protocol !== "https:") return false;
  const host = url.hostname.toLowerCase().replace(/\.$/, "");
  return THREADS_HOSTS.some((base) => host === base || host.endsWith(`.${base}`));
}

/** The URL itself when value is an http(s) URL, otherwise null (only such URLs may become links). */
export function httpUrlOrNull(value) {
  if (typeof value !== "string" || !value.trim()) return null;
  try {
    const url = new URL(value.trim());
    return url.protocol === "http:" || url.protocol === "https:" ? url.href : null;
  } catch {
    return null;
  }
}

const TAIPEI_FORMAT = new Intl.DateTimeFormat("en-US", {
  timeZone: "Asia/Taipei",
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  hourCycle: "h23",
});

/** ISO timestamp -> "YYYY-MM-DD HH:mm" in Asia/Taipei (analyzed_at); "" when missing or unparsable. */
export function formatTaipeiDateTime(iso) {
  if (typeof iso !== "string" || !iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  const parts = {};
  for (const part of TAIPEI_FORMAT.formatToParts(date)) parts[part.type] = part.value;
  return `${parts.year}-${parts.month}-${parts.day} ${parts.hour}:${parts.minute}`;
}

/** Click handler body for <a href> buttons that stay inside the SPA; modified clicks open natively. */
export function followSpaLink(event, navigate, to) {
  if (!event || event.defaultPrevented || event.button !== 0) return;
  if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
  event.preventDefault();
  navigate(to);
}
