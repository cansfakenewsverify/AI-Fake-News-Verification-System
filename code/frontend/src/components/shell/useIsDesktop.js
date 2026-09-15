import { useSyncExternalStore } from "react";
import { DESKTOP_QUERY } from "./navItems.js";

// Desktop layout flag (>= 768px, spec 8.2 / 8.5) shared by AppShell (top nav vs tab bar) and the result
// page action bar (S-08: sticky above the tab bar on mobile, a plain button row on desktop).
// matchMedia through useSyncExternalStore, so every user switches in the same commit.

function subscribeDesktop(callback) {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") return () => {};
  const mql = window.matchMedia(DESKTOP_QUERY);
  if (typeof mql.addEventListener === "function") {
    mql.addEventListener("change", callback);
    return () => mql.removeEventListener("change", callback);
  }
  mql.addListener(callback); // Safari < 14
  return () => mql.removeListener(callback);
}

function getDesktopSnapshot() {
  return typeof window !== "undefined" && typeof window.matchMedia === "function"
    ? window.matchMedia(DESKTOP_QUERY).matches
    : false;
}

export function useIsDesktop() {
  return useSyncExternalStore(subscribeDesktop, getDesktopSnapshot, () => false);
}
