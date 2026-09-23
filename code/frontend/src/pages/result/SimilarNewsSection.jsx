import { useId } from "react";
import DotRow from "../../components/DotRow.jsx";
import { t } from "../../i18n.js";
import { similarNewsItems } from "./similarNews.js";

// "Similar checks in the knowledge base" (spec 8.3 S2 element 5; FR-02 similar_news): the closest cases that fact-
// checkers have already verified, each with its verdict dot (backend frame_type), the claim, the fact-checker and
// the similarity / angle. Rows link to the fact-check article in a new tab. Not rendered on cache hits or when the
// backend found nothing close enough (similarNewsItems returns []).

export default function SimilarNewsSection({ result }) {
  const titleId = useId();
  const items = similarNewsItems(result);
  if (items.length === 0) return null;

  return (
    <section aria-labelledby={titleId} className="flex flex-col" style={{ gap: 8 }}>
      <div className="flex flex-col" style={{ gap: 4 }}>
        <h2 id={titleId} className="t-h2 m-0" style={{ color: "var(--c-ink)" }}>
          {t("section_similar")}
        </h2>
        <p className="t-sub m-0" style={{ color: "var(--c-ink-2)" }}>
          {t("similar_sub")}
        </p>
      </div>
      <ul className="m-0 list-none p-0">
        {items.map((row) => (
          <li key={row.key} className="border-b border-line" style={{ padding: "10px 0" }}>
            <DotRow item={row.item} title={row.title} meta={row.meta} href={row.href ?? undefined} />
          </li>
        ))}
      </ul>
    </section>
  );
}
