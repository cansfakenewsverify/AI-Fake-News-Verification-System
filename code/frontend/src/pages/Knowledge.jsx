import { useState } from "react";
import Button from "../components/Button.jsx";
import Card from "../components/Card.jsx";
import Chip from "../components/Chip.jsx";
import EmptyState from "../components/EmptyState.jsx";
import Skeleton from "../components/Skeleton.jsx";
import { t } from "../i18n.js";
import { useDocumentTitle } from "../lib/useDocumentTitle.js";
import KnowledgeCard from "./knowledge/KnowledgeCard.jsx";
import SearchBar from "./knowledge/SearchBar.jsx";
import { KNOWLEDGE_COPY } from "./knowledge/copy.js";
import { KNOWLEDGE_FILTERS, emptyMessage, toggleRiskFilter } from "./knowledge/knowledgeModel.js";
import { useKnowledgeList } from "./knowledge/useKnowledgeList.js";

// Knowledge base "/knowledge" (S-10; spec 8.3 S4, 8.4 S4 row, FR-07, FR-17; Knowledge.dc.html "S4").
// - Header: h1 knowledge_title + knowledge_sub + knowledge_verified_note (the page only lists
//   verified rows; the server filters, visibleKnowledgeRecords guards).
// - Search: SearchBar submits the trimmed keyword (Enter or button); submitting the same keyword again
//   retries. q is URL-encoded by api.js (URLSearchParams).
// - Filter chips: SCAM / MISINFO / SAFE / UNVERIFIABLE, single select, clicking the selected chip clears
//   it. Search and filter changes start a new request.
// - Report-week cut (tickets 0.5): one request with limit=60 (no "load more", no four-number stats bar).
// - States: loading = skeleton cards; error = backend_down + retry; no rows = knowledge_no_match (with a
//   keyword) / filter_empty (filter only) / knowledge_empty.
// - All user-visible text comes from i18n.js or ./knowledge/copy.js.

const SKELETON_CARDS = 4;
const LIST_CLASS = "m-0 flex list-none flex-col p-0";

export default function Knowledge() {
  const title = t("knowledge_title");
  useDocumentTitle(title);

  const [draft, setDraft] = useState("");
  const [q, setQ] = useState("");
  const [riskType, setRiskType] = useState("");
  const { status, records, retry } = useKnowledgeList({ q, riskType });

  function handleSearch(value) {
    const keyword = String(value ?? "").trim();
    if (keyword === q) retry();
    else setQ(keyword);
  }

  const empty = status === "ok" && records.length === 0 ? emptyMessage({ q, riskType }) : null;

  return (
    <div className="flex flex-col" style={{ gap: 24, padding: "24px 0" }}>
      <div className="flex flex-col" style={{ gap: 6 }}>
        <h1 className="t-h1 m-0" style={{ color: "var(--c-ink)" }}>
          {title}
        </h1>
        <p className="t-body m-0" style={{ color: "var(--c-ink-2)" }}>
          {t("knowledge_sub")}
        </p>
        <p className="t-caption m-0" style={{ color: "var(--c-ink-3)" }}>
          {t("knowledge_verified_note")}
        </p>
      </div>

      <div className="flex flex-col" style={{ gap: 4 }}>
        <SearchBar value={draft} onChange={setDraft} onSubmit={handleSearch} />
        <div
          role="group"
          aria-label={KNOWLEDGE_COPY.filter_group_label}
          className="flex flex-wrap items-center"
          style={{ columnGap: 8 }}
        >
          {KNOWLEDGE_FILTERS.map((item) => (
            <Chip
              key={item.riskType}
              variant="filter"
              selected={riskType === item.riskType}
              onClick={() => setRiskType((current) => toggleRiskFilter(current, item.riskType))}
            >
              {t(item.labelKey)}
            </Chip>
          ))}
        </div>
      </div>

      {/* Block (not flex) wrapper: the empty live region adds no gap above the list. */}
      <div>
        <div aria-live="polite">
          {status === "error" ? (
            <EmptyState
              mark="exclamation"
              title={t("backend_down")}
              action={
                <Button variant="secondary" onClick={retry}>
                  {t("btn_retry")}
                </Button>
              }
            />
          ) : null}
          {empty ? <EmptyState title={t(empty.key, empty.params)} /> : null}
        </div>

        {status === "loading" ? (
          <ul aria-busy="true" className={LIST_CLASS} style={{ gap: 12 }}>
            {Array.from({ length: SKELETON_CARDS }, (_, index) => (
              <li key={index}>
                <Card>
                  <Skeleton lines={4} />
                </Card>
              </li>
            ))}
          </ul>
        ) : null}

        {status === "ok" && records.length > 0 ? (
          <ul className={LIST_CLASS} style={{ gap: 12 }}>
            {records.map((record, index) => (
              <li key={record.id || index}>
                <KnowledgeCard record={record} />
              </li>
            ))}
          </ul>
        ) : null}
      </div>
    </div>
  );
}
