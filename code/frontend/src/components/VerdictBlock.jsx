import { useId } from "react";
import { t } from "../i18n.js";
import { toneOf } from "../lib/verdict.js";
import Icon from "./Icon.jsx";

// 燈號區塊（brief §3.7；Primitives.dc.html「3.7 燈號區塊」；spec §7.8、§8.3 S2 元件 1）
// 顏色只經 toneOf(frameType) 取 CSS 變數，絕不由風險類別推算；文字只顯示後端 frame_label。
// 全寬、-soft 底、無邊框、上下內距 24；12px 實心圓點＋frame_label（頁面唯一 <h1>，24/700 同色）
// ＋category_label 14 --c-ink-2；右上 chips 插槽（手機寬度不足時整組換到下一行）。
// grey（AI 不可用）以「!」圖示取代圓點；載入時 fade-in ≤200ms（reduced-motion 關閉）。
// children（選填）：標題列之下的整列內容（S-05 點 chip 展開的 confidence_note／cache_hint、S-06 灰卡內文），
// 由呼叫端自帶 w-full；隱藏時請在外層加 hidden，避免多出一行 flex 間距。
// 注意：red 在 red-soft 上只有 3:1，僅限此處 24px 粗體大字使用。

const FALLBACK_LABEL_KEY = {
  red: "frame_red_other",
  yellow: "frame_yellow",
  green: "frame_green",
  grey: "frame_grey",
};

export default function VerdictBlock({
  frameType,
  frameLabel,
  categoryLabel,
  chips,
  children,
  className = "",
  style,
}) {
  const { tone, fg, soft } = toneOf(frameType);
  const headingId = useId();
  // 後端契約保證 frame_label 有值；缺值時才以同色系通用文案保底
  const label = frameLabel || t(FALLBACK_LABEL_KEY[tone]);

  return (
    <section
      aria-labelledby={headingId}
      className={`fade-in flex w-full flex-wrap items-start justify-between ${className}`}
      style={{ gap: 12, padding: "24px 16px", background: soft, ...style }}
    >
      <div className="flex min-w-0 flex-col" style={{ gap: 4 }}>
        <div className="flex items-center" style={{ gap: 10 }}>
          {tone === "grey" ? (
            <Icon name="alert" size={20} style={{ color: fg }} />
          ) : (
            <span aria-hidden="true" className="shrink-0 rounded-full" style={{ width: 12, height: 12, background: fg }} />
          )}
          <h1 id={headingId} className="t-h1 m-0" style={{ color: fg, overflowWrap: "anywhere" }}>
            {label}
          </h1>
        </div>
        {categoryLabel ? (
          <p className="t-sub m-0" style={{ color: "var(--c-ink-2)" }}>
            {categoryLabel}
          </p>
        ) : null}
      </div>
      {chips ? (
        // 可點 chip 的 hit area 為 44px：列高固定 ≥44 並上移 6px，讓 28px 膠囊與 32px 標題行置中對齊
        <div className="flex min-h-11 max-w-full flex-wrap items-center" style={{ columnGap: 8, marginTop: -6 }}>
          {chips}
        </div>
      ) : null}
      {children}
    </section>
  );
}
