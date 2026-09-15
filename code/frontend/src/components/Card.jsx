// 卡片（brief §3.3；Primitives.dc.html「3.3 卡片」）
// --c-surface 底、1px --c-line、12px 圓角、16 內距、--shadow-card。
// as="a" | "button" 時整張卡可點（button 預設 type="button"）。

export default function Card({ as = "div", className = "", style, children, ...rest }) {
  const Tag = as;
  const extra = as === "button" ? { type: rest.type || "button" } : {};
  const interactive = as === "a" || as === "button";
  return (
    <Tag
      {...rest}
      {...extra}
      className={`block w-full border border-line bg-surface text-left text-ink ${
        interactive ? "cursor-pointer no-underline" : ""
      } ${className}`}
      style={{
        borderRadius: "var(--radius-card)",
        padding: 16,
        boxShadow: "var(--shadow-card)",
        color: "var(--c-ink)",
        ...style,
      }}
    >
      {children}
    </Tag>
  );
}
