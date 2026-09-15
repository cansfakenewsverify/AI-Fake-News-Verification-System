import { useId } from "react";
import Icon from "../../components/Icon.jsx";
import VerdictBlock from "../../components/VerdictBlock.jsx";
import { useIsDesktop } from "../../components/shell/useIsDesktop.js";
import { t } from "../../i18n.js";
import InputExcerpt from "./InputExcerpt.jsx";
import ResultActions from "./ResultActions.jsx";
import ResultFooter from "./ResultFooter.jsx";
import { isThreadsUrl } from "./resultState.js";

// Unverifiable (S-06; FR-02 acceptance 3-5; spec 5.3 exception, 8.3 S2 state 7;
// ResultStates.dc.html "cannot verify (threads URL hint)").
// risk_type UNVERIFIABLE means the content could not be read, so the AI was never asked:
// - Yellow verdict block with the backend frame_type / frame_label ("cannot verify"). No confidence or
//   "AI live" chip and no category line: none of them is meaningful without an AI verdict.
// - unverifiable_body, then the backend explanation (the specific reason, e.g. video links are not
//   supported), then unverifiable_threads_hint when source_url (or input_preview) is a threads.net /
//   threads.com URL.
// - The sources section and the "not verified by fact-checkers" banner are hidden on purpose
//   (spec 5.3: "cannot read the content" and "no fact-check source" must not show together).
// - Keeps the excerpt card and the fine print (without label_source); sharing is kept (S-08 ResultActions,
//   share_text_yellow from the backend): a row under the verdict block on desktop, sticky on mobile.

function HintNote({ children }) {
  return (
    <div
      role="note"
      className="flex items-start"
      style={{ gap: 8, padding: 12, background: "var(--c-accent-soft)", borderRadius: "var(--radius-btn)" }}
    >
      <Icon name="info" size={16} style={{ color: "var(--c-accent)", marginTop: 2 }} />
      <p className="t-sub m-0 min-w-0" style={{ color: "var(--c-ink)" }}>
        {children}
      </p>
    </div>
  );
}

export default function ResultUnverifiable({ data }) {
  const titleId = useId();
  const isDesktop = useIsDesktop();
  const result = data.result;
  const body = t("unverifiable_body");
  const explanation = typeof result.explanation === "string" ? result.explanation.trim() : "";
  const showThreadsHint = isThreadsUrl(data.source_url) || isThreadsUrl(data.input_preview);

  return (
    <div className="flex flex-col">
      <VerdictBlock
        className="-mx-4"
        style={{ width: "auto" }}
        frameType={result.frame_type}
        frameLabel={result.frame_label || t("frame_yellow_unverifiable")}
      />

      <div className="flex flex-col" style={{ gap: 24, padding: "24px 0" }}>
        {isDesktop ? <ResultActions share={data.share} /> : null}
        <InputExcerpt data={data} />
        <section aria-labelledby={titleId} className="flex flex-col" style={{ gap: 8 }}>
          <h2 id={titleId} className="t-h2 m-0" style={{ color: "var(--c-ink)" }}>
            {t("section_summary")}
          </h2>
          <p className="t-body m-0" style={{ color: "var(--c-ink)" }}>
            {body}
          </p>
          {explanation && explanation !== body ? (
            <p className="t-body m-0" style={{ color: "var(--c-ink-2)", overflowWrap: "anywhere" }}>
              {explanation}
            </p>
          ) : null}
          {showThreadsHint ? <HintNote>{t("unverifiable_threads_hint")}</HintNote> : null}
        </section>
        <ResultFooter completedAt={data.completed_at ?? result.analyzed_at} />
      </div>
      {isDesktop ? null : <ResultActions share={data.share} sticky />}
    </div>
  );
}
