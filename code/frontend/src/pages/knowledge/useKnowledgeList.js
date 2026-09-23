import { useCallback, useEffect, useState } from "react";
import { isBackendDownError, useRetryWhenBackendUp } from "../../components/shell/useBackendStatus.js";
import { getKnowledge } from "../../lib/api.js";
import { knowledgeQuery, visibleKnowledgeRecords } from "./knowledgeModel.js";

// Knowledge list request (S-10; spec 5.1 GET /api/knowledge, 8.3 S4 states).
// Report-week cut: a single request (limit=60, offset=0) per { q, riskType }; no pagination.
// - status "loading" | "ok" | "error"; "loading" is derived (the stored result belongs to an older
//   request key), so no state is set synchronously inside the effect.
// - A new q / riskType / retry aborts the previous request; an aborted request never touches state.
// - Any failure (network, timeout, 5xx, 4xx) is "error": the page shows backend_down + retry.
//   A failure to reach the backend (cold start) is retried on its own once the backend answers again.

export function useKnowledgeList({ q = "", riskType = "" } = {}) {
  const [attempt, setAttempt] = useState(0);
  const [result, setResult] = useState({ key: null, status: "loading", records: [] });
  const key = JSON.stringify([attempt, q, riskType]);

  useEffect(() => {
    const controller = new AbortController();
    getKnowledge(knowledgeQuery({ q, riskType }), { signal: controller.signal }).then(
      (data) => setResult({ key, status: "ok", records: visibleKnowledgeRecords(data, riskType) }),
      (err) => {
        if (!controller.signal.aborted) {
          setResult({ key, status: "error", records: [], down: isBackendDownError(err) });
        }
      },
    );
    return () => controller.abort();
  }, [key, q, riskType]);

  const retry = useCallback(() => setAttempt((n) => n + 1), [setAttempt]);
  const current = result.key === key;
  useRetryWhenBackendUp(current && result.status === "error" && result.down === true, retry);
  return {
    status: current ? result.status : "loading",
    records: current ? result.records : [],
    retry,
  };
}
