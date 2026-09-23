import { useCallback, useEffect, useState } from "react";
import Button from "../../components/Button.jsx";
import Card from "../../components/Card.jsx";
import EmptyState from "../../components/EmptyState.jsx";
import Skeleton from "../../components/Skeleton.jsx";
import { isBackendDownError, useRetryWhenBackendUp } from "../../components/shell/useBackendStatus.js";
import { t } from "../../i18n.js";
import { getKnowledgeHot } from "../../lib/api.js";
import KnowledgeCard from "../knowledge/KnowledgeCard.jsx";
import { HOT_LIMIT, hotCountText } from "./hotModel.js";

// "本站熱門查證" tab of /trending: GET /api/knowledge/hot?limit=10.
// - Same card as the knowledge page (KnowledgeCard); the chip shows recent demand (hotCountText).
// - States: loading = skeleton cards; error = backend_down + retry; no records = hot_empty.
//   A failure to reach the backend (cold start) is retried on its own once the backend answers again.
// - The backend lists verified rows only, ranked by time-decayed demand (app/services/hot_claims.py).

const SKELETON_CARDS = 4;
const LIST_CLASS = "m-0 flex list-none flex-col p-0";

export default function HotList() {
  const [attempt, setAttempt] = useState(0);
  const [list, setList] = useState({ attempt: -1, status: "loading", records: [] });

  useEffect(() => {
    const controller = new AbortController();
    const { signal } = controller;
    getKnowledgeHot({ limit: HOT_LIMIT }, { signal }).then(
      (data) => setList({ attempt, status: "ok", records: Array.isArray(data?.records) ? data.records : [] }),
      (err) => {
        if (!signal.aborted) setList({ attempt, status: "error", records: [], down: isBackendDownError(err) });
      },
    );
    return () => controller.abort();
  }, [attempt]);

  const retry = useCallback(() => setAttempt((n) => n + 1), [setAttempt]);
  const status = list.attempt === attempt ? list.status : "loading";
  useRetryWhenBackendUp(status === "error" && list.down === true, retry);
  const records = status === "ok" ? list.records : [];

  return (
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
        {status === "ok" && records.length === 0 ? <EmptyState title={t("hot_empty")} /> : null}
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

      {records.length > 0 ? (
        <ol className={LIST_CLASS} style={{ gap: 12 }}>
          {records.map((record, index) => (
            <li key={record?.id ?? index}>
              <KnowledgeCard record={record} countText={hotCountText(record)} />
            </li>
          ))}
        </ol>
      ) : null}
    </div>
  );
}
