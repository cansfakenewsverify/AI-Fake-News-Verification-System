// 深淺色主題（spec §8.1）：localStorage `fcc_theme` → prefers-color-scheme。
// 所有 storage／matchMedia 存取皆 try/catch（隱私模式、被封鎖的 site data 會拋錯）。
// index.html head 的 inline script 以相同規則在首繪前設定 data-theme，避免閃白。

export const THEME_KEY = "fcc_theme";

function defaultStorage() {
  try {
    return globalThis.localStorage;
  } catch {
    return undefined;
  }
}

function defaultMatchMedia() {
  return typeof globalThis.matchMedia === "function"
    ? globalThis.matchMedia.bind(globalThis)
    : undefined;
}

export function getSystemTheme(matchMedia = defaultMatchMedia()) {
  try {
    return matchMedia && matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  } catch {
    return "light";
  }
}

export function getStoredTheme(storage = defaultStorage()) {
  try {
    const v = storage && storage.getItem(THEME_KEY);
    return v === "dark" || v === "light" ? v : null;
  } catch {
    return null;
  }
}

export function getInitialTheme({ storage = defaultStorage(), matchMedia = defaultMatchMedia() } = {}) {
  return getStoredTheme(storage) || getSystemTheme(matchMedia);
}

export function applyTheme(theme, root = globalThis.document?.documentElement) {
  const value = theme === "dark" ? "dark" : "light";
  if (root) root.setAttribute("data-theme", value);
  return value;
}

export function getCurrentTheme(root = globalThis.document?.documentElement, opts) {
  const v = root && root.getAttribute("data-theme");
  return v === "dark" || v === "light" ? v : getInitialTheme(opts);
}

// 切換並記住；storage 寫入失敗時只影響本次瀏覽，不拋例外。
export function toggleTheme({ root = globalThis.document?.documentElement, storage = defaultStorage(), matchMedia } = {}) {
  const current = getCurrentTheme(root, { storage, matchMedia: matchMedia ?? defaultMatchMedia() });
  const next = applyTheme(current === "dark" ? "light" : "dark", root);
  try {
    if (storage) storage.setItem(THEME_KEY, next);
  } catch {
    /* storage 不可用時略過 */
  }
  return next;
}
