import { Outlet, useMatches } from "react-router-dom";
import { t } from "../../i18n.js";
import Banner from "../Banner.jsx";
import { ToastProvider } from "../Toast.jsx";
import DesktopNav from "./DesktopNav.jsx";
import Footer from "./Footer.jsx";
import TabBar from "./TabBar.jsx";
import TopBar from "./TopBar.jsx";
import { useBackendStatus } from "./useBackendStatus.js";
import { useIsDesktop } from "./useIsDesktop.js";

// 應用外殼（P-14；spec §8.2、§8.5、§8.6；brief §3.1、§3.2）
// - 路由 handle.topbar（"brand" | "back"）決定手機頂欄變體；handle.tab 決定當前分頁
// - <768px：TopBar ＋ 固定底部 TabBar，內容底部預留 88px（sticky 動作列＋分頁列）與安全區
// - ≥768px：DesktopNav 取代兩者
// - 手機／桌機以 matchMedia 只渲染其中一組導覽，確保 aria-current="page" 只出現一次
// - 後端不可用：頂欄下方統一顯示 backend_down 橫幅（各畫面不自行顯示）
// - 版面變數 --tabbar-h（手機 56px／桌機 0px）供 sticky 動作列（S-08）與 Toast（P-17）貼齊分頁列之上
// - ToastProvider 包在根元素內，Toast 才能繼承 --tabbar-h（P-17）

function routeHandle(matches) {
  for (let i = matches.length - 1; i >= 0; i -= 1) {
    if (matches[i].handle) return matches[i].handle;
  }
  return {};
}

export default function AppShell() {
  const handle = routeHandle(useMatches());
  const isDesktop = useIsDesktop();
  const { down } = useBackendStatus();

  return (
    <div
      className="flex min-h-dvh flex-col bg-bg text-ink"
      style={{
        "--tabbar-h": isDesktop ? "0px" : "56px",
        paddingBottom: isDesktop ? undefined : "calc(88px + env(safe-area-inset-bottom))",
      }}
    >
      <ToastProvider>
        {isDesktop ? <DesktopNav current={handle.tab} /> : <TopBar variant={handle.topbar} />}
        {down ? (
          // 底色全寬、文字對齊 640px 內容欄
          <Banner style={{ paddingInline: "max(16px, calc((100% - 640px) / 2 + 16px))" }}>{t("backend_down")}</Banner>
        ) : null}
        <main className="mx-auto w-full max-w-[640px] flex-1 px-4">
          <Outlet />
        </main>
        <div className="mx-auto w-full max-w-[640px] px-4">
          <Footer showBotLink={!isDesktop} current={handle.tab} />
        </div>
        {isDesktop ? null : <TabBar current={handle.tab} />}
      </ToastProvider>
    </div>
  );
}
