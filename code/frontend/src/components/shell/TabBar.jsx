import { Link } from "react-router-dom";
import { t } from "../../i18n.js";
import Icon from "../Icon.jsx";
import { NAV_TABS } from "./navItems.js";

// 手機底部分頁列（<768px；brief §3.2；Primitives.dc.html「3.2 底部分頁列」）
// 固定底部、3 格各 56 高、圖示 20px＋13px 字；當前格 --c-accent 字＋上緣 2px 線＋aria-current="page"
// （強調色為墨黑時與 --c-ink-2 色差小，另以字重 500 與上緣線辨識，不只靠顏色）；
// 底部留 env(safe-area-inset-bottom)。current 取自路由 handle.tab（/r/:id 為 "home"）。

export default function TabBar({ current }) {
  return (
    <nav
      aria-label={t("nav_main_label")}
      className="fixed inset-x-0 bottom-0 z-40 border-t border-line bg-bg"
      style={{ paddingBottom: "env(safe-area-inset-bottom)" }}
    >
      <ul className="m-0 grid list-none grid-cols-3 p-0">
        {NAV_TABS.map((item) => {
          const active = item.tab === current;
          return (
            <li key={item.tab} className="min-w-0">
              <Link
                to={item.to}
                aria-current={active ? "page" : undefined}
                className="flex h-14 flex-col items-center justify-center gap-1 no-underline focus-visible:-outline-offset-2"
                style={{
                  borderTop: `2px solid ${active ? "var(--c-accent)" : "transparent"}`,
                  color: active ? "var(--c-accent)" : "var(--c-ink-2)",
                  fontSize: 13,
                  lineHeight: "16px",
                  fontWeight: active ? 500 : 400,
                }}
              >
                <Icon name={item.icon} size={20} />
                <span>{t(item.labelKey)}</span>
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
