import { t } from "../../i18n.js";
import { httpUrl } from "../../lib/httpUrl.js";

// Evidence-based confidence (FR-22) and "similar checks in the knowledge base" (spec 8.3 S2 element 5,
// FR-02 similar_news). Rules and thresholds: docs/rebuild/ (confidence method document) and
// code/backend/app/services/evidence.py.
// - similarNewsItems(result): at most 3 rows for DotRow. Hidden on cache hits (the result *is* that row) and when
//   the backend sent nothing. Only http(s) fact-check URLs become links. Colour comes from the backend frame_type.
// - confidenceNoteLines(result): basis sentence, the nearest fact-checked case (similarity and angle) when it is
//   the reason for the level, and one line on how the level is produced. Results stored before the evidence
//   change carry no confidence_basis and keep the old "model self-assessment" note.

export const CONFIDENCE_BASES = [
  "factchecked",
  "similar_case",
  "pattern",
  "cited_source",
  "conflict",
  "safe_source",
  "unverifiable",
  "ai_only",
  "ai_unavailable",
];
export const SIMILAR_NEWS_MAX = 3;

function finite(value) {
  if (value === null || value === undefined || value === "") return null;
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

/** Angle between two vectors from their cosine similarity, in degrees. */
export function angleOf(similarity) {
  const sim = Math.max(-1, Math.min(1, similarity));
  return (Math.acos(sim) * 180) / Math.PI;
}

/** "similarity 0.72 / angle about 44 degrees" (the angle is derived when the backend did not send it). */
export function similarityText(similarity, degrees) {
  const sim = finite(similarity);
  if (sim === null) return "";
  const deg = finite(degrees) ?? angleOf(sim);
  return t("similar_item", { similarity: sim.toFixed(2), degrees: Math.round(deg) });
}

export function similarNewsItems(result) {
  if (!result || result.cached === true || !Array.isArray(result.similar_news)) return [];
  return result.similar_news
    .filter((item) => item && typeof item.title === "string" && item.title.trim())
    .slice(0, SIMILAR_NEWS_MAX)
    .map((item, index) => {
      const url = httpUrl(item.url);
      return {
        key: `${index}-${item.kb_id ?? item.url ?? item.title}`,
        item: { frame_type: item.frame_type, risk_type: item.risk_type },
        title: item.title.trim(),
        href: url ? url.href : null,
        meta: [typeof item.source === "string" ? item.source : "", similarityText(item.similarity, item.degrees)],
      };
    });
}

export function confidenceNoteLines(result) {
  const basis = result?.confidence_basis;
  if (!CONFIDENCE_BASES.includes(basis)) return [t("confidence_note")];
  const lines = [t(`confidence_basis_${basis}`)];
  const evidence = result.evidence || {};
  const similarity = finite(evidence.nearest_similarity);
  const degrees = finite(evidence.nearest_degrees);
  if ((basis === "similar_case" || basis === "conflict") && similarity !== null && degrees !== null) {
    lines.push(t("confidence_evidence", { similarity: similarity.toFixed(2), degrees: Math.round(degrees) }));
  }
  lines.push(t("confidence_method"));
  return lines;
}
