import { useEffect, useState } from "react";
import Button from "../components/Button.jsx";
import Card from "../components/Card.jsx";
import Chip from "../components/Chip.jsx";
import EmptyState from "../components/EmptyState.jsx";
import Skeleton from "../components/Skeleton.jsx";
import { t } from "../i18n.js";
import { getHealth, getTrending } from "../lib/api.js";
import { useDocumentTitle } from "../lib/useDocumentTitle.js";
import TrendingCard from "./trending/TrendingCard.jsx";
import { TRENDING_COPY } from "./trending/copy.js";
import {
  TRENDING_FILTERS,
  TRENDING_LIMIT,
  applyTrendingFilter,
  formatDateTime,
  latestCreatedAt,
  schedulerStateText,
} from "./trending/trendingModel.js";

// Trending wall "/trending" (S-09; spec 8.3 S3, 8.4 S3 row, FR-06; Trending.dc.html "S3").
// - Header: h1 trending_title + trending_sub ({scheduler_state} from GET /api/health scheduler block)
//   + trending_updated (newest created_at). There is no manual update control (FR-06 acceptance 3).
// - Report-week cut (tickets 0.5): filter chips "all" / "pending" only. One GET /api/trending?limit=20
//   (no risk_type) feeds both; "pending" filters on the client (trendingModel.isUnverifiedRecord).
// - States: loading = 6 skeleton cards; error = backend_down + retry (never the empty state);
//   no records = trending_empty; filter leaves nothing = filter_empty.
// - Requests are aborted on unmount; "retry" starts a new attempt for both requests.
// - All user-visible text comes from i18n.js or ./trending/copy.js.

const SKELETON_CARDS = 6;
const LIST_CLASS = "m-0 flex list-none flex-col p-0";

export default function Trending() {
  const title = t("trending_title");
  useDocumentTitle(title);

  const [filter, setFilter] = useState("all");
  const [attempt, setAttempt] = useState(0);
  const [list, setList] = useState({ attempt: -1, status: "loading", records: [] });
  const [health, setHealth] = useState(null);

  useEffect(() => {
    const controller = new AbortController();
    const { signal } = controller;
    getHealth({ signal }).then(
      (data) => setHealth(data),
      () => {},
    );
    getTrending({ limit: TRENDING_LIMIT }, { signal }).then(
      (data) => setList({ attempt, status: "ok", records: Array.isArray(data?.records) ? data.records : [] }),
      () => {
        if (!signal.aborted) setList({ attempt, status: "error", records: [] });
      },
    );
    return () => controller.abort();
  }, [attempt]);

  const status = list.attempt === attempt ? list.status : "loading";
  const records = status === "ok" ? list.records : [];
  const visible = applyTrendingFilter(records, filter);
  const updated = latestCreatedAt(records);
  const hasRecords = records.length > 0;

  return (
    <div className="flex flex-col" style={{ gap: 16, padding: "24px 0" }}>
      <div className="flex flex-col" style={{ gap: 6 }}>
        <h1 className="t-h1 m-0" style={{ color: "var(--c-ink)" }}>
          {title}
        </h1>
        <p className="t-body m-0" style={{ color: "var(--c-ink-2)" }}>
          {t("trending_sub", { scheduler_state: schedulerStateText(health) })}
        </p>
        {updated ? (
          <p className="t-caption m-0" style={{ color: "var(--c-ink-3)" }}>
            {t("trending_updated", { time: formatDateTime(updated) })}
          </p>
        ) : null}
      </div>

      {status === "loading" || hasRecords ? (
        <div
          role="group"
          aria-label={TRENDING_COPY.filter_group_label}
          className="flex flex-wrap items-center"
          style={{ columnGap: 8 }}
        >
          {TRENDING_FILTERS.map((item) => (
            <Chip key={item.id} variant="filter" selected={filter === item.id} onClick={() => setFilter(item.id)}>
              {t(item.labelKey)}
            </Chip>
          ))}
        </div>
      ) : null}

      {/* Block (not flex) wrapper: the empty live region adds no gap above the list. */}
      <div>
        <div aria-live="polite">
          {status === "error" ? (
            <EmptyState
              mark="exclamation"
              title={t("backend_down")}
              action={
                <Button variant="secondary" onClick={() => setAttempt((n) => n + 1)}>
                  {t("btn_retry")}
                </Button>
              }
            />
          ) : null}
          {status === "ok" && !hasRecords ? <EmptyState title={t("trending_empty")} /> : null}
          {status === "ok" && hasRecords && visible.length === 0 ? <EmptyState title={t("filter_empty")} /> : null}
        </div>

        {status === "loading" ? (
          <ul aria-busy="true" className={LIST_CLASS} style={{ gap: 12 }}>
            {Array.from({ length: SKELETON_CARDS }, (_, index) => (
              <li key={index}>
                <Card>
                  <Skeleton lines={3} />
                </Card>
              </li>
            ))}
          </ul>
        ) : null}

        {visible.length > 0 ? (
          <ul className={LIST_CLASS} style={{ gap: 12 }}>
            {visible.map((record, index) => (
              <li key={record?.id ?? index}>
                <TrendingCard record={record} />
              </li>
            ))}
          </ul>
        ) : null}
      </div>
    </div>
  );
}
