import { Link } from "react-router-dom";
import { t } from "../../i18n.js";

// 全站頁尾（spec §8.2、FR-13；Primitives.dc.html「頁尾」）：13px --c-ink-3 置中，文案 footer 逐字。
// 「隱私政策」「資料刪除」是 public/ 下的純 HTML 靜態頁 → 必須用純 <a>（router Link 會被 SPA 的 * 路由吃掉）。
// showBotLink：手機唯一的 /bot 入口（桌機由頂部導覽提供，避免重複）。
// 連結外框 ≥44×44px 滿足觸控目標；分隔符 aria-hidden，textContent 仍與 footer 字串一致。

const linkClass = "inline-flex min-h-11 min-w-11 items-center justify-center";
const linkStyle = { color: "inherit" };

export default function Footer({ showBotLink = false, current }) {
  const [privacy = "", deletion = "", ...rest] = t("footer").split(" · ");
  const note = rest.join(" · ");

  return (
    <footer className="py-4 text-center" style={{ fontSize: 13, lineHeight: "16px", color: "var(--c-ink-3)" }}>
      <p className="m-0">
        <a href="/privacy.html" className={linkClass} style={linkStyle}>
          {privacy}
        </a>
        <span aria-hidden="true"> · </span>
        <a href="/data-deletion.html" className={linkClass} style={linkStyle}>
          {deletion}
        </a>
        {note ? (
          <>
            <span aria-hidden="true"> · </span>
            <span>{note}</span>
          </>
        ) : null}
      </p>
      {showBotLink ? (
        <p className="m-0">
          <Link
            to="/bot"
            aria-current={current === "bot" ? "page" : undefined}
            className={linkClass}
            style={linkStyle}
          >
            {t("nav_bot")}
          </Link>
        </p>
      ) : null}
    </footer>
  );
}
