// 導覽項目（spec §8.2）：手機底部分頁列 3 格；桌機頂部導覽另加「機器人」。
// `tab` 對應 routes.jsx 各路由的 handle.tab，外殼據此決定當前分頁（aria-current="page"）。

export const NAV_TABS = [
  { tab: "home", to: "/", labelKey: "nav_home", icon: "verify" },
  { tab: "trending", to: "/trending", labelKey: "nav_trending", icon: "trending" },
  { tab: "knowledge", to: "/knowledge", labelKey: "nav_knowledge", icon: "knowledge" },
];

export const NAV_BOT = { tab: "bot", to: "/bot", labelKey: "nav_bot" };

// 手機 / 桌機切換點（與 spec §8.2「<768 px 底部分頁列」一致）
export const DESKTOP_QUERY = "(min-width: 768px)";
