import { useId } from "react";
import SourceRow from "../../components/SourceRow.jsx";
import { t } from "../../i18n.js";
import { showNoSourceBanner } from "../../lib/verdict.js";
import { visibleSources } from "./resultState.js";

// Fact-check sources (S-05, S-07; FR-16; spec 5.3, 8.3 S2 element 4 / state 10; Result.dc.html section 3,
// ResultStates.dc.html "not verified").
// - Unverified result (same condition as the banner): h2 + sources_empty in a dashed box, and no source
//   rows at all, even if the payload carries some.
// - Otherwise one P-15 SourceRow per item of result.sources (13px tier caption "fact-check organisation" /
//   "media fact-check report" + title + domain + external icon). Tier 3 items (the "related discussions"
//   list) are never rendered on the P0 page; entries whose tier is not 1 or 2 are skipped defensively
//   (visibleSources), so no empty list item is left behind.
// - Verified / rule result with nothing listable (e.g. a gold-labelled row without links): the section is
//   left out instead of claiming that no fact-checker verified it.

export default function SourcesSection({ result }) {
  const titleId = useId();
  const unverified = showNoSourceBanner(result);
  const sources = unverified ? [] : visibleSources(result);
  if (!unverified && sources.length === 0) return null;

  return (
    <section aria-labelledby={titleId} className="flex flex-col" style={{ gap: 8 }}>
      <h2 id={titleId} className="t-h2 m-0" style={{ color: "var(--c-ink)" }}>
        {t("section_sources")}
      </h2>
      {unverified ? (
        <div
          className="flex items-center justify-center text-center"
          style={{
            minHeight: 64,
            padding: 16,
            background: "var(--c-bg)",
            border: "1px dashed var(--c-line)",
            borderRadius: "var(--radius-card)",
          }}
        >
          <p className="t-sub m-0" style={{ color: "var(--c-ink-2)" }}>
            {t("sources_empty")}
          </p>
        </div>
      ) : (
        <ul className="m-0 list-none p-0">
          {sources.map((source, index) => (
            <li key={`${index}-${source.url ?? ""}`}>
              <SourceRow source={source} />
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
