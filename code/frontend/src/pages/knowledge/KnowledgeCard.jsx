import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import Card from "../../components/Card.jsx";
import Chip from "../../components/Chip.jsx";
import Disclosure from "../../components/Disclosure.jsx";
import DotRow from "../../components/DotRow.jsx";
import { t } from "../../i18n.js";
import { labelSourceKey } from "../../lib/verdict.js";
import { firstVerifiedSourceDomain, hitCountOf, knowledgeLink } from "./knowledgeModel.js";

// Knowledge result card (S-10 step 3; spec 8.3 S4, FR-07 acceptance 4, FR-16; Knowledge.dc.html card).
// - DotRow (dot + verdict word from listVerdict) with raw_content clamped to 3 lines.
// - summary: 15px --c-ink-2, 2 lines.
// - Meta row: hit_count chip (white outline chip, as in the mockup) + label_source as 13px --c-ink-3 text
//   (never a chip, brief 7-4) on the left; the first Tier 1/2 source host (13px, break-all) on the right.
// - last_result_id -> the whole card links to /r/{id}. Otherwise the card is an <article> whose
//   Disclosure (section_summary) expands the full summary in place; while it is open the clamped
//   2-line summary is hidden (group-has on the card), so the text is not shown twice.
//   The Disclosure only renders when the 2-line summary is really cut off (useIsClamped); a summary
//   that already fits is shown in full and has nothing to expand. Without ResizeObserver it always renders.
// - data-kb-id on the card root (used by the de-duplication console check).

const SUMMARY_TEXT = { fontSize: 15, lineHeight: "22px", overflowWrap: "anywhere" };
const SMALL_TEXT = { fontSize: 13, lineHeight: "16px", color: "var(--c-ink-3)" };

/**
 * true while the element's text overflows its line clamp. Re-measured whenever the element resizes
 * (viewport or font changes); while the element is hidden (Disclosure open) the last answer is kept,
 * so opening the Disclosure never removes it.
 */
function useIsClamped(ref, text) {
  const [clamped, setClamped] = useState(() => typeof ResizeObserver === "undefined");
  useEffect(() => {
    const element = ref.current;
    if (!element || typeof ResizeObserver === "undefined") return undefined;
    const observer = new ResizeObserver(() => {
      if (element.getClientRects().length === 0) return;
      setClamped(element.scrollHeight - element.clientHeight > 1);
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, [ref, text]);
  return clamped;
}

export default function KnowledgeCard({ record }) {
  const to = knowledgeLink(record);
  const summary = typeof record?.summary === "string" ? record.summary.trim() : "";
  const labelKey = labelSourceKey(record?.label_source);
  const hits = hitCountOf(record);
  const domain = firstVerifiedSourceDomain(record?.sources);
  const cardStyle = { display: "flex", flexDirection: "column", gap: 8 };
  const summaryRef = useRef(null);
  const summaryClamped = useIsClamped(summaryRef, summary);

  const content = (
    <>
      <DotRow item={{ risk_type: record?.risk_type }} title={record?.raw_content || ""} lines={3} />
      {summary ? (
        <p
          ref={summaryRef}
          className="m-0 line-clamp-2 group-has-[[aria-expanded=true]]/kb:hidden"
          style={{ ...SUMMARY_TEXT, color: "var(--c-ink-2)" }}
        >
          {summary}
        </p>
      ) : null}
      {hits !== null || labelKey || domain ? (
        <div className="flex flex-wrap items-center justify-between" style={{ columnGap: 8, rowGap: 4 }}>
          <span className="flex min-w-0 flex-wrap items-center" style={{ gap: 8 }}>
            {hits !== null ? <Chip variant="live">{t("hit_count", { n: hits })}</Chip> : null}
            {labelKey ? (
              <span data-label-source="" style={SMALL_TEXT}>
                {t(labelKey)}
              </span>
            ) : null}
          </span>
          {domain ? <span style={{ ...SMALL_TEXT, wordBreak: "break-all" }}>{domain}</span> : null}
        </div>
      ) : null}
    </>
  );

  if (to) {
    return (
      <Card as={Link} to={to} data-kb-id={record?.id} className="cursor-pointer no-underline" style={cardStyle}>
        {content}
      </Card>
    );
  }

  return (
    <Card as="article" data-kb-id={record?.id} className="group/kb" style={cardStyle}>
      {content}
      {summary && summaryClamped ? (
        // the card edge already closes the row: drop the Disclosure's own bottom rule
        <Disclosure summary={t("section_summary")} className="[&>button]:border-b-0">
          <p className="m-0" style={{ ...SUMMARY_TEXT, color: "var(--c-ink)" }}>
            {summary}
          </p>
        </Disclosure>
      ) : null}
    </Card>
  );
}
