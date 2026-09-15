// 骨架（brief §3.10；Primitives.dc.html「3.10 骨架」）
// --c-line 底 8px 圓角條、寬度錯落、shimmer（index.css 的 reduced-motion 規則會關閉動畫）。
// 容器 aria-busy="true"；label 提供給輔助技術的載入說明（選填）。

const WIDTHS = ["55%", "100%", "85%", "60%", "92%", "70%"];

export default function Skeleton({ lines = 3, label, className = "", style }) {
  const count = Math.max(1, lines);
  return (
    <div
      aria-busy="true"
      aria-live="polite"
      className={`flex flex-col ${className}`}
      style={{ gap: 10, ...style }}
    >
      {label ? <span className="sr-only">{label}</span> : null}
      {Array.from({ length: count }, (_, i) => (
        <div
          key={i}
          aria-hidden="true"
          className="shimmer"
          style={{
            height: i === 0 ? 20 : 14,
            width: WIDTHS[i % WIDTHS.length],
            borderRadius: 8,
            backgroundColor: "var(--c-line)",
          }}
        />
      ))}
    </div>
  );
}
