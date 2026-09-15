// 按鈕（brief §3.4；Primitives.dc.html「3.4 按鈕」）
// primary：全寬 48 高、--c-ink 底 --c-ink-inverse 字 16/500、10px 圓角。
// secondary：--c-bg 底 1px --c-line 線框、--c-ink 字。
// text：透明底、--c-accent 字。
// 三種皆 48 高（對齊 mockup，≥44px 觸控目標）；loading 時 disabled＋spinner＋aria-busy，文字由呼叫端傳入（如 t("btn_analyzing")）。
// as="a" 供分享等外連：傳 href；target="_blank" 時自動補 rel="noopener"。

const VARIANT = {
  primary: {
    background: "var(--c-ink)",
    color: "var(--c-ink-inverse)",
    border: "1px solid var(--c-ink)",
  },
  secondary: {
    background: "var(--c-bg)",
    color: "var(--c-ink)",
    border: "1px solid var(--c-line)",
  },
  text: {
    background: "transparent",
    color: "var(--c-accent)",
    border: "1px solid transparent",
  },
};

function Spinner() {
  return (
    <svg
      width="18"
      height="18"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      aria-hidden="true"
      focusable="false"
      className="animate-spin shrink-0"
    >
      <circle cx="12" cy="12" r="9" opacity="0.25" />
      <path d="M21 12a9 9 0 0 0-9-9" />
    </svg>
  );
}

export default function Button({
  as = "button",
  variant = "primary",
  loading = false,
  disabled = false,
  fullWidth,
  icon = null,
  className = "",
  style,
  children,
  ...rest
}) {
  const isLink = as === "a";
  const Tag = isLink ? "a" : "button";
  const inactive = disabled || loading;
  const wide = fullWidth ?? variant === "primary";

  const common = {
    "aria-busy": loading ? true : undefined,
    className: `inline-flex items-center justify-center gap-2 no-underline select-none ${
      wide ? "w-full" : ""
    } ${inactive ? "cursor-default" : "cursor-pointer"} ${className}`,
    style: {
      minHeight: 48,
      padding: "0 16px",
      borderRadius: "var(--radius-btn)",
      fontFamily: "inherit",
      fontSize: 16,
      lineHeight: "24px",
      fontWeight: 500,
      textDecoration: "none",
      opacity: inactive ? 0.5 : 1,
      ...VARIANT[variant],
      ...style,
    },
  };

  const content = (
    <>
      {loading ? <Spinner /> : icon}
      {children != null && <span>{children}</span>}
    </>
  );

  if (isLink) {
    const { target, rel, href, onClick, ...linkRest } = rest;
    const safeRel = target === "_blank" ? [rel, "noopener"].filter(Boolean).join(" ") : rel;
    return (
      <Tag
        {...linkRest}
        {...common}
        href={inactive ? undefined : href}
        target={target}
        rel={safeRel}
        aria-disabled={inactive ? true : undefined}
        onClick={inactive ? (e) => e.preventDefault() : onClick}
      >
        {content}
      </Tag>
    );
  }

  return (
    <Tag type={rest.type || "button"} {...rest} {...common} disabled={inactive}>
      {content}
    </Tag>
  );
}
