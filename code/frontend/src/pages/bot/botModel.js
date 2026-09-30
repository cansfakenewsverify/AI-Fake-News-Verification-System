import { t } from "../../i18n.js";
import { httpUrl } from "../../lib/httpUrl.js";
import { formatTaipeiDateTime } from "../result/resultState.js";

// Bot status page model (S-11; FR-11 P0 read-only version; spec 8.3 S6, 5.3 threads/status and threads/replies).
// Pure helpers so the page stays thin and every state is unit-tested (bot.test.js).
// - badgeKey: token_invalid wins over the mode; unknown modes fall back to "off".
// - lastPollText / lastErrorText / backoffText: the status card lines; last_error is shown in red by the page.
// - replyRows: DotRow input for the latest replies (colour from the stored frame_type; links only to http(s)
//   Threads permalinks and to /r/{result_id} for ids that look like ids).

export const STATUS_POLL_MS = 2000;
export const REPLIES_LIMIT = 10;
export const KNOWN_ERRORS = [
  "token_invalid",
  "rate_limited",
  "transient_error",
  "mention_failed",
  "ai_unavailable",
  "threads_not_configured",
];
const MODE_KEYS = { live: "threads_mode_live", sim: "threads_mode_sim", off: "threads_mode_off" };
const RESULT_ID = /^[A-Za-z0-9_.-]{1,64}$/;

function count(value) {
  const n = Number(value);
  return Number.isFinite(n) && n >= 0 ? Math.floor(n) : 0;
}

export function isOff(status) {
  return !status || status.enabled === false || !(status.mode in MODE_KEYS) || status.mode === "off";
}

export function badgeKey(status) {
  if (!status) return null;
  if (status.last_error === "token_invalid") return "threads_mode_invalid";
  return MODE_KEYS[status.mode] || "threads_mode_off";
}

export function lastPollText(status) {
  if (!status?.last_poll_at) return t("threads_never_polled");
  const stats = status.last_poll_stats || {};
  return t("threads_last_poll", {
    time: formatTaipeiDateTime(status.last_poll_at) || String(status.last_poll_at),
    checked: count(stats.checked),
    replied: count(stats.replied),
    skipped: count(stats.skipped),
    errors: count(stats.errors),
  });
}

export function lastErrorText(status) {
  const code = status?.last_error;
  if (!code) return null;
  return KNOWN_ERRORS.includes(code) ? t(`threads_error_${code}`) : t("threads_error_other", { code: String(code) });
}

/** "Polling paused until ..." while backoff_until is still in the future; otherwise null. */
export function backoffText(status, now = Date.now()) {
  const until = status?.backoff_until;
  if (!until) return null;
  const at = new Date(until).getTime();
  if (!Number.isFinite(at) || at <= now) return null;
  return t("threads_backoff", { time: formatTaipeiDateTime(until) || String(until) });
}

export function replyRows(records) {
  if (!Array.isArray(records)) return [];
  return records
    .filter((record) => record && typeof record === "object")
    .map((record, index) => {
      const permalink = httpUrl(record.permalink);
      const resultId = typeof record.result_id === "string" && RESULT_ID.test(record.result_id) ? record.result_id : null;
      const username = typeof record.username === "string" ? record.username.replace(/^@/, "") : "";
      return {
        key: `${index}-${record.reply_id ?? record.mention_id ?? ""}`,
        item: { frame_type: record.frame_type, risk_type: record.risk_type },
        title: typeof record.source_text_preview === "string" ? record.source_text_preview : "",
        meta: [username ? t("from_threads", { username }) : "", formatTaipeiDateTime(record.replied_at)],
        replyText: typeof record.reply_text === "string" ? record.reply_text : "",
        permalink: permalink ? permalink.href : null,
        resultTo: resultId ? `/r/${resultId}` : null,
      };
    });
}
