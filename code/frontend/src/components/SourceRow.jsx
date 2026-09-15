import { t } from "../i18n.js";
import { tierCaption } from "../lib/verdict.js";
import Icon from "./Icon.jsx";

// 來源列（brief §3.9；Primitives.dc.html「3.9 來源列」；spec §8.3 S2 元件 4、FR-16）
// tierCaption(tier) 為 null（Tier 3 或缺值）時不渲染 → Tier 3 絕不外露。
// 13px --c-ink-2 小標（查核機構／媒體查核報導）＋標題 16 --c-ink＋網域 13 --c-ink-3（break-all）
// ＋外連圖示 16px；整列 ≥44 高、底線 1px；外連 target="_blank" rel="noopener"。
// 只接受 http(s) 網址作為連結（其他協定只顯示文字，不產生可點連結）。

function httpUrl(value) {
  if (typeof value !== "string" || !value.trim()) return null;
  try {
    const url = new URL(value.trim());
    return url.protocol === "http:" || url.protocol === "https:" ? url : null;
  } catch {
    return null;
  }
}

export default function SourceRow({ source, className = "", style }) {
  const captionKey = tierCaption(source?.tier);
  if (!captionKey) return null;

  const url = httpUrl(source.url);
  const domain = url ? url.hostname.replace(/^www\./, "") : "";
  const title = source.title || domain || source.url || "";

  const content = (
    <>
      <span className="flex min-w-0 flex-1 flex-col" style={{ gap: 2 }}>
        <span style={{ fontSize: 13, lineHeight: "16px", color: "var(--c-ink-2)" }}>{t(captionKey)}</span>
        <span style={{ fontSize: 16, lineHeight: "24px", color: "var(--c-ink)", overflowWrap: "anywhere" }}>{title}</span>
        {domain ? (
          <span style={{ fontSize: 13, lineHeight: "16px", color: "var(--c-ink-3)", wordBreak: "break-all" }}>
            {domain}
          </span>
        ) : null}
      </span>
      {url ? <Icon name="external" size={16} style={{ color: "var(--c-ink-3)" }} /> : null}
    </>
  );

  const rowClass = `flex min-h-11 items-center border-b border-line ${className}`;
  const rowStyle = { gap: 12, padding: "10px 0", ...style };

  if (!url) {
    return (
      <div className={rowClass} style={rowStyle}>
        {content}
      </div>
    );
  }
  return (
    <a href={url.href} target="_blank" rel="noopener" className={`${rowClass} text-ink no-underline`} style={rowStyle}>
      {content}
    </a>
  );
}
