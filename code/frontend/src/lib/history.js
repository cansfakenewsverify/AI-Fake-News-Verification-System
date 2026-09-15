// 查證歷史（spec FR-08、§8.3 S1 元件 4、§12 R7）：只存在瀏覽器 localStorage，無伺服器副本。
// 格式：key `fcc_history_v1`，值 [{id, input_type, preview(≤80 字), risk_type|null, frame_type|null, created_at}]，
// 最多 50 筆、最新在前。所有讀寫包 try/catch（無痕模式、被封鎖的 site data 會拋錯），
// storage 以參數注入（預設 globalThis.localStorage），方便 node --test。

import { t } from "../i18n.js";

export const HISTORY_KEY = "fcc_history_v1";
export const MAX_ENTRIES = 50;
export const PREVIEW_MAX = 80;

function defaultStorage() {
  try {
    return globalThis.localStorage;
  } catch {
    return undefined;
  }
}

function isEntry(x) {
  return x != null && typeof x === "object" && typeof x.id === "string" && x.id !== "";
}

// 讀出陣列；storage 不可用時回 []。JSON 損毀或非陣列 → 視為空陣列並覆寫。
function readAll(storage) {
  let raw;
  try {
    if (!storage) return [];
    raw = storage.getItem(HISTORY_KEY);
  } catch {
    return [];
  }
  if (raw == null) return [];
  try {
    const parsed = JSON.parse(raw);
    if (Array.isArray(parsed)) return parsed.filter(isEntry);
  } catch {
    /* 損毀 JSON，落到下方覆寫 */
  }
  writeAll(storage, []);
  return [];
}

function writeAll(storage, list) {
  try {
    if (!storage) return false;
    storage.setItem(HISTORY_KEY, JSON.stringify(list));
    return true;
  } catch {
    return false;
  }
}

// 以 code point 截斷，避免把 surrogate pair 切半。
function truncate(text, max) {
  const chars = Array.from(String(text ?? ""));
  return chars.length > max ? chars.slice(0, max).join("") : chars.join("");
}

export function isAvailable(storage = defaultStorage()) {
  try {
    if (!storage) return false;
    const probe = "__fcc_probe__";
    storage.setItem(probe, "1");
    storage.getItem(probe);
    if (typeof storage.removeItem === "function") storage.removeItem(probe);
    return true;
  } catch {
    return false;
  }
}

// 送出查證時寫入；同 id 去重後放最前，上限 50 筆。回傳寫入後的清單（寫入失敗時回傳記憶體中的結果）。
export function addEntry({ id, input_type, preview, created_at } = {}, storage = defaultStorage()) {
  if (typeof id !== "string" || id === "") return listAll(storage);
  const entry = {
    id,
    input_type: input_type ?? null,
    preview: truncate(preview, PREVIEW_MAX),
    risk_type: null,
    frame_type: null,
    created_at: created_at ?? new Date().toISOString(),
  };
  const next = [entry, ...readAll(storage).filter((e) => e.id !== id)].slice(0, MAX_ENTRIES);
  writeAll(storage, next);
  return next;
}

// 結果頁完成後回寫 risk_type／frame_type；找不到 id 時不變。
export function updateEntry(id, { risk_type, frame_type } = {}, storage = defaultStorage()) {
  const list = readAll(storage);
  let changed = false;
  const next = list.map((e) => {
    if (e.id !== id) return e;
    changed = true;
    return {
      ...e,
      ...(risk_type !== undefined ? { risk_type } : {}),
      ...(frame_type !== undefined ? { frame_type } : {}),
    };
  });
  if (changed) writeAll(storage, next);
  return changed;
}

export function listAll(storage = defaultStorage()) {
  return readAll(storage);
}

export function listRecent(limit = 5, storage = defaultStorage()) {
  return readAll(storage).slice(0, Math.max(0, limit));
}

export function clearAll(storage = defaultStorage()) {
  try {
    if (!storage) return false;
    if (typeof storage.removeItem === "function") storage.removeItem(HISTORY_KEY);
    else storage.setItem(HISTORY_KEY, "[]");
    return true;
  } catch {
    return false;
  }
}

// 「最近查證」時間顯示：剛剛／N 分鐘前／N 小時前／M/D（本地時區）。字串取自 i18n.js EXTRA（rel_*）。
export function relativeTime(iso, now = new Date()) {
  const then = new Date(iso);
  const nowMs = now instanceof Date ? now.getTime() : Number(now);
  if (Number.isNaN(then.getTime()) || Number.isNaN(nowMs)) return "";
  const diff = nowMs - then.getTime();
  const minute = 60 * 1000;
  const hour = 60 * minute;
  if (diff < minute) return t("rel_just_now"); // 含未來時間（時鐘誤差）
  if (diff < hour) return t("rel_minutes_ago", { n: Math.floor(diff / minute) });
  if (diff < 24 * hour) return t("rel_hours_ago", { n: Math.floor(diff / hour) });
  return t("rel_month_day", { m: then.getMonth() + 1, d: then.getDate() });
}
