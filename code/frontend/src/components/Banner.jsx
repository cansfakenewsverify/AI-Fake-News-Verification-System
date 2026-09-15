import Icon from "./Icon.jsx";

// 橫幅（brief §3.11；Primitives.dc.html「3.11 橫幅」）
// tone="warning"：全寬 --c-yellow-soft 底、14px --c-yellow 字、左側「!」圖示、role="status"。
// 單行：<Banner>{t("backend_down")}</Banner>
// 兩行：<Banner title={t("no_verified_source_title")} body={t("no_verified_source_body")} />

const TONES = {
  warning: { background: "var(--c-yellow-soft)", color: "var(--c-yellow)" },
};

export default function Banner({ tone = "warning", title, body, children, className = "", style }) {
  const palette = TONES[tone] || TONES.warning;
  const twoLine = title != null && body != null;
  return (
    <div
      role="status"
      className={`flex w-full ${twoLine ? "items-start" : "items-center"} ${className}`}
      style={{
        gap: 8,
        padding: "10px 16px",
        fontSize: 14,
        lineHeight: "20px",
        ...palette,
        ...style,
      }}
    >
      <Icon name="alert" size={16} style={twoLine ? { marginTop: 2 } : undefined} />
      {twoLine ? (
        <div className="flex min-w-0 flex-col">
          <strong style={{ fontWeight: 700 }}>{title}</strong>
          <span>{body}</span>
        </div>
      ) : (
        <span className="min-w-0">{children ?? title ?? body}</span>
      )}
    </div>
  );
}
