import { useId } from "react";
import { Link } from "react-router-dom";
import Button from "../../components/Button.jsx";
import DotRow from "../../components/DotRow.jsx";
import { t } from "../../i18n.js";
import { relativeTime } from "../../lib/history.js";

// Home page "recent checks" list (S-03; spec 8.3 S1 element 4, FR-08; Main.dc.html "recent").
// - Header: h2 EXTRA.home_recent_title + 8.7 history_sub (13px ink-3) + text button btn_clear_history.
//   The button only asks for confirmation (onClearRequest); the page owns the ConfirmDialog.
// - Rows: DotRow (8px dot + verdict text from listVerdict: frame_type when written back, otherwise the
//   grey chip_pending text) + preview (2 lines) + relative time; the whole row is one >= 44px link to
//   /r/{id} ending in an underlined "view" label (the accent is ink black, so links are underlined).
// - Renders nothing for an empty list: the page shows the examples + history_empty instead.
// - All user-visible text comes from i18n.js (this folder must stay free of Han characters).

export default function RecentHistory({ entries, onClearRequest, className = "", style }) {
  const titleId = useId();
  if (!entries?.length) return null;

  return (
    <section aria-labelledby={titleId} className={`flex flex-col ${className}`} style={{ gap: 4, ...style }}>
      <div className="flex items-center justify-between" style={{ gap: 12, minHeight: 44 }}>
        <div className="flex min-w-0 flex-col" style={{ gap: 2 }}>
          <h2 id={titleId} className="t-h2 m-0" style={{ color: "var(--c-ink)" }}>
            {t("home_recent_title")}
          </h2>
          <p className="t-caption m-0" style={{ color: "var(--c-ink-3)" }}>
            {t("history_sub")}
          </p>
        </div>
        <Button
          variant="text"
          onClick={onClearRequest}
          className="shrink-0"
          style={{ minHeight: 44, padding: "0 8px", fontSize: 15, lineHeight: "20px" }}
        >
          {t("btn_clear_history")}
        </Button>
      </div>

      <ul className="m-0 flex list-none flex-col p-0">
        {entries.map((entry, index) => (
          <li
            key={entry.id}
            style={{ borderBottom: index < entries.length - 1 ? "1px solid var(--c-line)" : "none" }}
          >
            <Link
              to={`/r/${encodeURIComponent(entry.id)}`}
              className="flex items-start text-ink no-underline"
              style={{ gap: 12, minHeight: 44, padding: "10px 0" }}
            >
              <DotRow
                item={entry}
                title={entry.preview}
                meta={relativeTime(entry.created_at)}
                className="min-w-0 flex-1"
              />
              <span
                className="inline-flex shrink-0 items-center"
                style={{
                  minHeight: 44,
                  padding: "0 4px",
                  fontSize: 15,
                  lineHeight: "20px",
                  fontWeight: 500,
                  color: "var(--c-accent)",
                  textDecoration: "underline",
                  textUnderlineOffset: 2,
                }}
              >
                {t("home_recent_view")}
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}
