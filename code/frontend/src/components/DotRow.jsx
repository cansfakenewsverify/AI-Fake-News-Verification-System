import { Link } from "react-router-dom";
import { listVerdict } from "../lib/verdict.js";

// 燈號點列（brief §3.8；Primitives.dc.html「3.8 燈號點列」；熱門牆、知識庫、最近查證共用）
// 8px 實心圓點＋判定文字（listVerdict 的 label，13/500 同色，永遠顯示文字不靠顏色）
// ＋標題（16 --c-ink，最多 2 行截斷）＋可選次文字行 meta（機構・日期・label_source，13px --c-ink-3，不用 chip）。
// to → 站內 Link（/r/{id}）；href → 外連 <a target="_blank" rel="noopener">；兩者皆無 → 純區塊。
// 顏色只來自 listVerdict()（最近查證有 frame_type 時以後端 frame_type 為準）。
// lines：標題最多行數，預設 2；知識庫 raw_content 傳 3（S-10，spec §8.3 S4）。

const TITLE_CLAMP = { 2: "line-clamp-2", 3: "line-clamp-3" };

function metaText(meta) {
  return Array.isArray(meta) ? meta.filter((part) => part != null && part !== "").join("・") : meta;
}

export default function DotRow({ item, title, meta, to, href, lines = 2, className = "", style }) {
  const verdict = listVerdict(item);
  const clampClass = TITLE_CLAMP[lines] || TITLE_CLAMP[2];
  const text = title ?? item?.title ?? item?.preview ?? item?.raw_content ?? "";
  const metaContent = metaText(meta);

  const body = (
    <>
      <span className="flex items-start" style={{ gap: 8, minHeight: 24 }}>
        <span
          aria-hidden="true"
          className="shrink-0 rounded-full"
          style={{ width: 8, height: 8, marginTop: 8, background: verdict.fg }}
        />
        <span className="shrink-0" style={{ fontSize: 13, lineHeight: "24px", fontWeight: 500, color: verdict.fg }}>
          {verdict.label}
        </span>
        <span
          className={`${clampClass} min-w-0 flex-1`}
          style={{ fontSize: 16, lineHeight: "24px", color: "var(--c-ink)", overflowWrap: "anywhere" }}
        >
          {text}
        </span>
      </span>
      {metaContent ? (
        <span className="block" style={{ paddingLeft: 16, fontSize: 13, lineHeight: "16px", color: "var(--c-ink-3)" }}>
          {metaContent}
        </span>
      ) : null}
    </>
  );

  const rowStyle = { gap: 4, ...style };

  if (to) {
    return (
      <Link to={to} className={`flex min-h-11 flex-col text-ink no-underline ${className}`} style={rowStyle}>
        {body}
      </Link>
    );
  }
  if (href) {
    return (
      <a
        href={href}
        target="_blank"
        rel="noopener"
        className={`flex min-h-11 flex-col text-ink no-underline ${className}`}
        style={rowStyle}
      >
        {body}
      </a>
    );
  }
  return (
    <div className={`flex flex-col ${className}`} style={rowStyle}>
      {body}
    </div>
  );
}
