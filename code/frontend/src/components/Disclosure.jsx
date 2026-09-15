import { useId, useState } from "react";
import Icon from "./Icon.jsx";

// 折疊區（P-17；spec §8.3 S2 explanation 折疊、長摘錄展開、S6 回覆全文；§8.6 觸控不靠 hover）
// <button aria-expanded aria-controls> ＋ 內容區；點擊、Enter、Space 切換（原生按鈕行為），不依賴 hover。
// 摘要列：全寬、≥48 高、上下 1px --c-line、16/500、右側 chevron（展開時旋轉 180°）。對齊 Result.dc.html「詳細說明」。

export default function Disclosure({ summary, children, defaultOpen = false, className = "", style }) {
  const [open, setOpen] = useState(Boolean(defaultOpen));
  const contentId = useId();

  return (
    <div className={className} style={style}>
      <button
        type="button"
        aria-expanded={open}
        aria-controls={contentId}
        onClick={() => setOpen((value) => !value)}
        className="flex w-full cursor-pointer items-center justify-between border-y border-line text-left text-ink"
        style={{ minHeight: 48, gap: 12, fontSize: 16, lineHeight: "24px", fontWeight: 500 }}
      >
        <span className="min-w-0">{summary}</span>
        <Icon
          name="chevron"
          size={20}
          style={{ color: "var(--c-ink-2)", transform: open ? "rotate(180deg)" : undefined }}
        />
      </button>
      <div id={contentId} hidden={!open} style={{ paddingTop: 12 }}>
        {children}
      </div>
    </div>
  );
}
