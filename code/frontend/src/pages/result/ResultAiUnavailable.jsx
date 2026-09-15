import { useNavigate } from "react-router-dom";
import Button from "../../components/Button.jsx";
import Icon from "../../components/Icon.jsx";
import VerdictBlock from "../../components/VerdictBlock.jsx";
import { t } from "../../i18n.js";
import InputExcerpt from "./InputExcerpt.jsx";
import ResultFooter from "./ResultFooter.jsx";
import { followSpaLink } from "./resultState.js";

// AI unavailable (S-06; spec 5.3 / 5.5, 8.3 S2 state 5; ResultStates.dc.html "AI unavailable").
// Chosen by the page only when data.ai_unavailable === true (never by the summary text).
// - Grey verdict block ("!" mark + frame_grey) holding a card with ai_unavailable_title / _body and the
//   "reanalyze" button (same resend logic as the failed state, see useReanalyze).
// - No confidence / cache chips, no share or copy, no sources, no "not verified" banner.
// - Keeps the excerpt card, a "check another" link (mockup) and the fine print; label_source is left out
//   of the fine print because no verdict was produced.

export default function ResultAiUnavailable({ data, reanalyze }) {
  const navigate = useNavigate();
  const { submitting, message } = reanalyze;

  return (
    <div className="flex flex-col">
      <VerdictBlock className="-mx-4" style={{ width: "auto" }} frameType="grey" frameLabel={t("frame_grey")}>
        <div
          className="flex w-full flex-col"
          style={{
            gap: 12,
            padding: 16,
            background: "var(--c-bg)",
            border: "1px solid var(--c-line)",
            borderRadius: "var(--radius-card)",
          }}
        >
          <div className="flex items-start" style={{ gap: 10 }}>
            <Icon name="alert" size={20} style={{ color: "var(--c-ink-2)", marginTop: 2 }} />
            <div className="flex min-w-0 flex-col" style={{ gap: 4 }}>
              <p className="m-0" style={{ fontSize: 16, lineHeight: "24px", fontWeight: 700, color: "var(--c-ink)" }}>
                {t("ai_unavailable_title")}
              </p>
              <p className="t-sub m-0" style={{ color: "var(--c-ink-2)" }}>
                {t("ai_unavailable_body")}
              </p>
            </div>
          </div>
          <Button onClick={reanalyze.reanalyze} loading={submitting}>
            {submitting ? t("btn_analyzing") : t("btn_reanalyze")}
          </Button>
          <div aria-live="polite" className="flex flex-col" style={{ gap: 2 }}>
            {(message || []).map((line) => (
              <p key={line} className="t-sub m-0" style={{ color: "var(--c-ink-2)", overflowWrap: "anywhere" }}>
                {line}
              </p>
            ))}
          </div>
        </div>
      </VerdictBlock>

      <div className="flex flex-col" style={{ gap: 24, padding: "24px 0" }}>
        <InputExcerpt data={data} />
        <Button
          as="a"
          href="/"
          variant="text"
          onClick={(event) => followSpaLink(event, navigate, "/")}
          style={{ textDecoration: "underline", textUnderlineOffset: 2 }}
        >
          {t("btn_check_another")}
        </Button>
        <ResultFooter completedAt={data.completed_at ?? data.result?.analyzed_at} />
      </div>
    </div>
  );
}
