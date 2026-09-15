import { t } from "../../i18n.js";
import { labelSourceKey } from "../../lib/verdict.js";
import { formatTaipeiDateTime } from "./resultState.js";

// Result fine print (S-05; spec 8.3 S2 element 7; Result.dc.html section 5), 13px ink-3:
//   line 1: analyzed_at ("{datetime}" = completed time in Asia/Taipei) ・ label_source_{label_source}
//   line 2: disclaimer_short
// Parts that are missing (no parsable time, unknown or omitted label_source) are left out.

export default function ResultFooter({ completedAt, labelSource }) {
  const datetime = formatTaipeiDateTime(completedAt);
  const labelKey = labelSourceKey(labelSource);
  const first = [datetime ? t("analyzed_at", { datetime }) : null, labelKey ? t(labelKey) : null]
    .filter(Boolean)
    .join("・");

  return (
    <div className="flex flex-col" style={{ gap: 4 }}>
      {first ? (
        <p className="t-caption m-0" style={{ color: "var(--c-ink-3)" }}>
          {first}
        </p>
      ) : null}
      <p className="t-caption m-0" style={{ color: "var(--c-ink-3)" }}>
        {t("disclaimer_short")}
      </p>
    </div>
  );
}
