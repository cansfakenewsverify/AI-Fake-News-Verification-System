import { Link } from "react-router-dom";
import { BRAND, t } from "../../i18n.js";
import ThemeToggle from "../ThemeToggle.jsx";
import { NAV_BOT, NAV_TABS } from "./navItems.js";

// 桌機頂部導覽（≥768px；spec §8.2）：品牌名（連回 /）＋查證／熱門／知識庫＋機器人＋主題切換，
// 取代手機的 TopBar 與 TabBar。與內容欄同寬 640px 置中。
// 當前項 --c-accent 字＋下緣 2px 線（手機分頁列上緣線的鏡像，貼齊內容側）＋字重 500＋aria-current="page"。

const ITEMS = [...NAV_TABS, NAV_BOT];

export default function DesktopNav({ current }) {
  return (
    <header className="h-14 border-b border-line bg-bg">
      <div className="mx-auto flex h-full max-w-[640px] items-center gap-4 px-4">
        <Link
          to="/"
          className="inline-flex min-h-11 shrink-0 items-center text-ink no-underline"
          style={{ fontSize: 16, lineHeight: "24px", fontWeight: 500 }}
        >
          {BRAND}
        </Link>
        <nav aria-label={t("nav_main_label")} className="h-full min-w-0 flex-1">
          <ul className="m-0 flex h-full list-none items-stretch p-0">
            {ITEMS.map((item) => {
              const active = item.tab === current;
              return (
                <li key={item.tab} className="flex">
                  <Link
                    to={item.to}
                    aria-current={active ? "page" : undefined}
                    className="flex min-w-11 items-center justify-center px-3 no-underline focus-visible:-outline-offset-2"
                    style={{
                      borderBottom: `2px solid ${active ? "var(--c-accent)" : "transparent"}`,
                      borderTop: "2px solid transparent",
                      color: active ? "var(--c-accent)" : "var(--c-ink-2)",
                      fontSize: 15,
                      lineHeight: "20px",
                      fontWeight: active ? 500 : 400,
                    }}
                  >
                    {t(item.labelKey)}
                  </Link>
                </li>
              );
            })}
          </ul>
        </nav>
        <ThemeToggle className="-mr-3" />
      </div>
    </header>
  );
}
