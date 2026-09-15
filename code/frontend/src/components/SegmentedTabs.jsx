// 分段模式 tab（brief §3.5；Primitives.dc.html「3.5 輸入卡」；spec §8.6 tablist、方向鍵）
// 軌道 --c-line 底、內距 3、間距 2、10px 圓角；每格 44 高、8px 圓角、15/500；
// 選中 --c-bg 底 --c-ink 字＋--shadow-card，未選透明底 --c-ink-2 字。
// role="tablist"／role="tab"／aria-selected／aria-controls；roving tabindex：
// ←／→ 切換並移動焦點（循環），Home／End 到首尾（自動啟用：焦點所到即選取）。
// tabs: [{ value, label }]；tab 的 id 為 `${idBase}-tab-${value}`，供 tabpanel 的 aria-labelledby 使用。

function focusTab(tablist, index) {
  const tab = tablist?.querySelectorAll('[role="tab"]')[index];
  if (tab) tab.focus();
}

export default function SegmentedTabs({ tabs, value, onChange, label, idBase, panelId, className = "", style }) {
  const selectedIndex = Math.max(
    0,
    tabs.findIndex((tab) => tab.value === value),
  );

  function select(index, tablist) {
    const next = (index + tabs.length) % tabs.length;
    if (tabs[next].value !== value) onChange?.(tabs[next].value);
    focusTab(tablist, next);
  }

  function handleKeyDown(event, index) {
    const tablist = event.currentTarget.parentElement;
    if (event.key === "ArrowRight") select(index + 1, tablist);
    else if (event.key === "ArrowLeft") select(index - 1, tablist);
    else if (event.key === "Home") select(0, tablist);
    else if (event.key === "End") select(tabs.length - 1, tablist);
    else return;
    event.preventDefault();
  }

  return (
    <div
      role="tablist"
      aria-label={label}
      className={`grid ${className}`}
      style={{
        gridTemplateColumns: `repeat(${tabs.length}, minmax(0, 1fr))`,
        gap: 2,
        padding: 3,
        background: "var(--c-line)",
        borderRadius: "var(--radius-btn)",
        ...style,
      }}
    >
      {tabs.map((tab, index) => {
        const selected = index === selectedIndex;
        return (
          <button
            key={tab.value}
            type="button"
            role="tab"
            id={`${idBase}-tab-${tab.value}`}
            aria-selected={selected}
            aria-controls={panelId}
            tabIndex={selected ? 0 : -1}
            onClick={() => {
              if (!selected) onChange?.(tab.value);
            }}
            onKeyDown={(event) => handleKeyDown(event, index)}
            className="flex h-11 min-w-0 cursor-pointer items-center justify-center px-2"
            style={{
              borderRadius: 8,
              fontSize: 15,
              lineHeight: "20px",
              fontWeight: 500,
              background: selected ? "var(--c-bg)" : "transparent",
              color: selected ? "var(--c-ink)" : "var(--c-ink-2)",
              boxShadow: selected ? "var(--shadow-card)" : "none",
            }}
          >
            <span className="truncate">{tab.label}</span>
          </button>
        );
      })}
    </div>
  );
}
