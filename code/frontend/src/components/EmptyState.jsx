import Icon from "./Icon.jsx";

// 空狀態（P-17；spec §8.3 S1 空、S2 狀態 2／9、S3／S4 空與錯誤、S6 未啟用）
// 幾何記號（圓框內線性圖示，不用 emoji）＋標題 16/500 --c-ink＋說明 14 --c-ink-2＋可選動作（傳入 <Button>）。
// mark："close"（✕）｜"exclamation"（!）｜"check"（✓）｜"question"（?，預設）；記號為中性灰，不用紅黃綠。
// titleAs：標題標籤，預設 <p>；當空狀態就是整頁主內容時（例如結果頁 404）由呼叫端傳 "h1"，維持每頁唯一 h1。
// 供 trending_empty、filter_empty、knowledge_empty、knowledge_no_match、threads_off、
// result_not_found_*、error_timeout、error_server 共用；文案由呼叫端以 t() 帶入（含 {q} 等置換）。

const MARKS = ["close", "exclamation", "check", "question"];

export default function EmptyState({
  mark = "question",
  title,
  body,
  action,
  titleAs = "p",
  className = "",
  style,
}) {
  const TitleTag = titleAs;
  const icon = MARKS.includes(mark) ? mark : "question";
  return (
    <div
      className={`flex flex-col items-center text-center ${className}`}
      style={{ gap: 8, padding: "32px 16px", ...style }}
    >
      <span
        aria-hidden="true"
        className="flex shrink-0 items-center justify-center rounded-full"
        style={{
          width: 40,
          height: 40,
          marginBottom: 4,
          background: "var(--c-surface)",
          border: "1px solid var(--c-line)",
          color: "var(--c-ink-2)",
        }}
      >
        <Icon name={icon} size={20} />
      </span>
      {title ? (
        <TitleTag className="m-0" style={{ fontSize: 16, lineHeight: "24px", fontWeight: 500, color: "var(--c-ink)", overflowWrap: "anywhere" }}>
          {title}
        </TitleTag>
      ) : null}
      {body ? (
        <p className="t-sub m-0" style={{ maxWidth: 480, color: "var(--c-ink-2)", overflowWrap: "anywhere" }}>
          {body}
        </p>
      ) : null}
      {action ? <div style={{ marginTop: 8 }}>{action}</div> : null}
    </div>
  );
}
