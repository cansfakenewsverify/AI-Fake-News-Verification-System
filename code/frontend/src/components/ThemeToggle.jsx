import { useState } from "react";
import { t } from "../i18n.js";
import { getCurrentTheme, toggleTheme } from "../lib/theme.js";

// 頂欄右側文字鈕（brief §3-1）：顯示「可切換到」的主題名稱。
export default function ThemeToggle({ className = "" }) {
  const [theme, setTheme] = useState(() => getCurrentTheme());
  return (
    <button
      type="button"
      aria-label="切換深淺色"
      onClick={() => setTheme(toggleTheme())}
      className={`t-sub inline-flex min-h-11 min-w-11 items-center justify-center px-3 text-ink-2 ${className}`}
    >
      {theme === "dark" ? t("theme_light") : t("theme_dark")}
    </button>
  );
}
