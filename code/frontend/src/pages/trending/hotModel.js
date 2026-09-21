import { t } from "../../i18n.js";

// Pure helpers for the trending page tabs and the "本站熱門查證" tab (GET /api/knowledge/hot).
// No React, testable with node --test.

export const HOT_LIMIT = 10;

export const TRENDING_TABS = [
  { value: "feed", labelKey: "trending_tab_feed" },
  { value: "hot", labelKey: "trending_tab_hot" },
];

/** ?tab=hot opens the hot tab; anything else (missing, unknown) is the fact-checker feed. */
export function tabFromSearch(search) {
  const params = new URLSearchParams(typeof search === "string" ? search : "");
  return params.get("tab") === "hot" ? "hot" : "feed";
}

function count(value) {
  const n = Number(value);
  return Number.isFinite(n) && n >= 0 ? Math.floor(n) : 0;
}

/** Card chip text: "近 24 小時 {day} 次・近 7 天 {week} 次". Missing or malformed counts read as 0. */
export function hotCountText(record) {
  return t("hot_count", { day: count(record?.recent_24h), week: count(record?.recent_7d) });
}
