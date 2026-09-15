// chip（brief §3.6；Primitives.dc.html「3.6 chip」）：視覺高 28、內距 0 10、13/500、圓角 999。
// variant：
//   cache       快取命中（--c-accent-soft 底 --c-accent 字）
//   live        AI 即時判定（--c-bg 底、1px --c-line 線框、--c-ink 字）
//   confidence  信心 高／中／低（同 live）
//   pending     未查證（--c-grey-soft 底 --c-grey 字）
//   filter      篩選（未選 --c-bg 底 --c-ink-2 字線框；selected 時 --c-ink 底 --c-ink-inverse 字）
//   neutral     中性小標（/bot 模式徽章等；--c-accent-soft 底 --c-ink-2 字）
// 傳 onClick → <button>：外層透明 hit area ≥44×44（brief §7-4），filter 帶 aria-pressed，
// 可展開說明的 chip 傳 expanded／controls → aria-expanded／aria-controls；焦點環畫在 28px 膠囊上。
// 無 onClick → <span>。長文字在容器內以省略號截斷，不撐出橫向捲動。

const PALETTE = {
  cache: { background: "var(--c-accent-soft)", color: "var(--c-accent)", borderColor: "transparent" },
  live: { background: "var(--c-bg)", color: "var(--c-ink)", borderColor: "var(--c-line)" },
  confidence: { background: "var(--c-bg)", color: "var(--c-ink)", borderColor: "var(--c-line)" },
  pending: { background: "var(--c-grey-soft)", color: "var(--c-grey)", borderColor: "transparent" },
  filter: { background: "var(--c-bg)", color: "var(--c-ink-2)", borderColor: "var(--c-line)" },
  filterSelected: { background: "var(--c-ink)", color: "var(--c-ink-inverse)", borderColor: "var(--c-ink)" },
  neutral: { background: "var(--c-accent-soft)", color: "var(--c-ink-2)", borderColor: "transparent" },
};

function pillStyle(palette) {
  return {
    height: 28,
    padding: "0 10px",
    gap: 6,
    borderRadius: "var(--radius-chip)",
    border: `1px solid ${palette.borderColor}`,
    background: palette.background,
    color: palette.color,
    fontSize: 13,
    lineHeight: "16px",
    fontWeight: 500,
    whiteSpace: "nowrap",
  };
}

export default function Chip({
  variant = "neutral",
  selected = false,
  expanded,
  controls,
  onClick,
  children,
  className = "",
  style,
  ...rest
}) {
  const palette = variant === "filter" && selected ? PALETTE.filterSelected : PALETTE[variant] || PALETTE.neutral;
  const label = <span className="min-w-0 truncate">{children}</span>;

  if (typeof onClick !== "function") {
    return (
      <span
        {...rest}
        className={`inline-flex max-w-full items-center align-middle ${className}`}
        style={{ ...pillStyle(palette), ...style }}
      >
        {label}
      </span>
    );
  }

  return (
    <button
      type="button"
      {...rest}
      onClick={onClick}
      aria-pressed={variant === "filter" ? Boolean(selected) : undefined}
      aria-expanded={expanded === undefined ? undefined : Boolean(expanded)}
      aria-controls={controls}
      className={`group inline-flex min-h-11 min-w-11 max-w-full cursor-pointer items-center justify-center focus-visible:[outline:none] ${className}`}
      style={style}
    >
      <span
        className="inline-flex max-w-full items-center group-focus-visible:[outline:2px_solid_var(--c-accent)] group-focus-visible:[outline-offset:2px]"
        style={pillStyle(palette)}
      >
        {label}
      </span>
    </button>
  );
}
