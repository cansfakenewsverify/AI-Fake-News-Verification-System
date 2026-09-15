import { Link, useNavigate } from "react-router-dom";
import { BRAND, t } from "../../i18n.js";
import Icon from "../Icon.jsx";
import ThemeToggle from "../ThemeToggle.jsx";

// 手機頂欄（brief §3.1；Primitives.dc.html「3.1 頂欄」）：56 高、底線 1px --c-line。
// variant="brand"：左側品牌名連回 /；variant="back"：左側「← 返回」。右側主題切換。
// 返回：站內有上一頁（history.state.idx > 0）→ navigate(-1)；
// 從 Threads 等外部直接開 /r/{id}（idx 為 0）→ Link 預設導向 /。

const labelStyle = { fontSize: 16, lineHeight: "24px", fontWeight: 500 };

// EXTRA.back 為「← 返回」：箭頭改由 back 線性圖示呈現（mockup Bot.dc.html），文字取其餘部分
function backText() {
  return t("back").replace(/^←\s*/, "");
}

export default function TopBar({ variant = "brand" }) {
  const navigate = useNavigate();

  function handleBack(event) {
    // 新分頁／新視窗開啟等修飾鍵交給瀏覽器
    if (event.defaultPrevented || event.button !== 0) return;
    if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    const idx = window.history.state?.idx;
    if (typeof idx === "number" && idx > 0) {
      event.preventDefault();
      navigate(-1);
    }
  }

  return (
    <header className="h-14 border-b border-line bg-bg">
      <div className="mx-auto flex h-full max-w-[640px] items-center justify-between px-4">
        {variant === "back" ? (
          <Link
            to="/"
            onClick={handleBack}
            className="inline-flex min-h-11 items-center gap-1 text-ink no-underline"
            style={labelStyle}
          >
            <Icon name="back" />
            <span>{backText()}</span>
          </Link>
        ) : (
          <Link to="/" className="inline-flex min-h-11 items-center text-ink no-underline" style={labelStyle}>
            {BRAND}
          </Link>
        )}
        <ThemeToggle className="-mr-3" />
      </div>
    </header>
  );
}
