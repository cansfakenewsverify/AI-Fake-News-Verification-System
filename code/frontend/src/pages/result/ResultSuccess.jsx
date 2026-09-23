import { useId, useState } from "react";
import Chip from "../../components/Chip.jsx";
import Disclosure from "../../components/Disclosure.jsx";
import Icon from "../../components/Icon.jsx";
import VerdictBlock from "../../components/VerdictBlock.jsx";
import { useIsDesktop } from "../../components/shell/useIsDesktop.js";
import { t } from "../../i18n.js";
import { cacheChipKey, confidenceChipKey } from "../../lib/verdict.js";
import InputExcerpt from "./InputExcerpt.jsx";
import NoVerifiedSourceBanner from "./NoVerifiedSourceBanner.jsx";
import ResultActions from "./ResultActions.jsx";
import ResultFooter from "./ResultFooter.jsx";
import SimilarNewsSection from "./SimilarNewsSection.jsx";
import SourcesSection from "./SourcesSection.jsx";
import { confidenceNoteLines } from "./similarNews.js";

// Completed result (S-05; spec 8.3 S2 elements 1-4 and 7, states 3 and 4; Result.dc.html,
// ResultStates.dc.html "cache hit").
// 1. VerdictBlock flush under the top bar (-mx-4): dot + frame_label (the page <h1>) + category_label,
//    colours only from the backend frame_type. Chips: "confidence high/mid/low" toggles the evidence note
//    (confidenceNoteLines: basis, nearest fact-checked case, how the level is produced; FR-22);
//    a cached result shows chip_cache_{url|hash|vector} which toggles cache_hint, otherwise chip_live.
//    The notes open inside the verdict block (one at a time) and are plain taps, never hover.
// S-07: NoVerifiedSourceBanner right under the verdict block (above the summary) for unverified results.
// 2. InputExcerpt  3. summary in bold + explanation in a collapsed P-17 Disclosure
// 4. SourcesSection (result.sources only; sources_empty when unverified)
// 5. SimilarNewsSection: similar checks in the knowledge base (FR-02 similar_news; hidden on cache hits)
// 7. ResultFooter (analyzed_at, label_source, disclaimer).
// 6. S-08 ResultActions: >= 768px a plain row under the verdict area; mobile sticky at the end of the page.

function ChipNote({ id, open, children }) {
  return (
    <div
      id={id}
      role="note"
      hidden={!open}
      className="flex items-start"
      style={{
        gap: 8,
        padding: 12,
        background: "var(--c-bg)",
        border: "1px solid var(--c-line)",
        borderRadius: "var(--radius-btn)",
      }}
    >
      <Icon name="info" size={16} style={{ color: "var(--c-accent)", marginTop: 2 }} />
      <p className="t-sub m-0 min-w-0" style={{ color: "var(--c-ink-2)" }}>
        {children}
      </p>
    </div>
  );
}

function SummarySection({ result }) {
  const titleId = useId();
  const summary = typeof result.summary === "string" ? result.summary.trim() : "";
  const explanation = typeof result.explanation === "string" ? result.explanation.trim() : "";
  if (!summary && !explanation) return null;

  return (
    <section aria-labelledby={titleId} className="flex flex-col" style={{ gap: 12 }}>
      <div className="flex flex-col" style={{ gap: 8 }}>
        <h2 id={titleId} className="t-h2 m-0" style={{ color: "var(--c-ink)" }}>
          {t("section_summary")}
        </h2>
        {summary ? (
          <p className="t-body m-0" style={{ fontWeight: 700, color: "var(--c-ink)", overflowWrap: "anywhere" }}>
            {summary}
          </p>
        ) : null}
      </div>
      {explanation ? (
        <Disclosure summary={t("section_explanation")}>
          <p className="t-body m-0" style={{ color: "var(--c-ink)", whiteSpace: "pre-line", overflowWrap: "anywhere" }}>
            {explanation}
          </p>
        </Disclosure>
      ) : null}
    </section>
  );
}

export default function ResultSuccess({ data }) {
  const result = data.result;
  const isDesktop = useIsDesktop();
  const [openNote, setOpenNote] = useState(null); // "confidence" | "cache" | null
  const confidenceNoteId = useId();
  const cacheNoteId = useId();

  const confidenceKey = confidenceChipKey(result.confidence_level);
  const cacheKey = result.cached === true ? cacheChipKey(result.cache_layer) : "chip_live";
  const isCacheHit = cacheKey !== "chip_live";
  const toggle = (name) => setOpenNote((current) => (current === name ? null : name));

  const chips = (
    <>
      {confidenceKey ? (
        <Chip
          variant="confidence"
          onClick={() => toggle("confidence")}
          expanded={openNote === "confidence"}
          controls={confidenceNoteId}
        >
          {t(confidenceKey)}
        </Chip>
      ) : null}
      {isCacheHit ? (
        <Chip variant="cache" onClick={() => toggle("cache")} expanded={openNote === "cache"} controls={cacheNoteId}>
          {t(cacheKey)}
        </Chip>
      ) : (
        <Chip variant="live">{t("chip_live")}</Chip>
      )}
    </>
  );

  return (
    <div className="flex flex-col">
      <VerdictBlock
        className="-mx-4"
        style={{ width: "auto" }}
        frameType={result.frame_type}
        frameLabel={result.frame_label}
        categoryLabel={result.category_label}
        chips={chips}
      >
        <div className="w-full" hidden={openNote === null}>
          {confidenceKey ? (
            <ChipNote id={confidenceNoteId} open={openNote === "confidence"}>
              {confidenceNoteLines(result).map((line) => (
                <span key={line} className="block">
                  {line}
                </span>
              ))}
            </ChipNote>
          ) : null}
          {isCacheHit ? (
            <ChipNote id={cacheNoteId} open={openNote === "cache"}>
              {t("cache_hint")}
            </ChipNote>
          ) : null}
        </div>
      </VerdictBlock>

      <div className="flex flex-col" style={{ gap: 24, padding: "24px 0" }}>
        <NoVerifiedSourceBanner result={result} />
        {isDesktop ? <ResultActions share={data.share} /> : null}
        <InputExcerpt data={data} />
        <SummarySection result={result} />
        <SourcesSection result={result} />
        <SimilarNewsSection result={result} />
        <ResultFooter completedAt={data.completed_at ?? result.analyzed_at} labelSource={result.label_source} />
      </div>
      {isDesktop ? null : <ResultActions share={data.share} sticky />}
    </div>
  );
}
