import { useCallback, useEffect, useState } from "react";
import { BACKEND_UP_EVENT, pollResult } from "../../lib/api.js";
import { POLL_INTERVAL_MS, POLL_MAX_MS, outcomeFromError, outcomeFromPoll } from "./resultState.js";

// Result page polling (S-04; FR-04; spec 5.3, 8.3 S2 states 1, 2, 6, 9).
// useResultPolling(id) -> {phase, data, code, restart}
//   phase "loading"    polling GET /api/result/{id} every 2 s (P-09 pollResult)
//         "completed"  data = response (result, share, ai_unavailable ...)
//         "failed"     data = response with error.code
//         "timeout"    still pending after 90 s; polling stopped (restart() starts a new 90 s round)
//         "not_found"  404 result_not_found
//         "network"    network / timeout / gateway error for the whole 90 s (a sleeping backend is retried inside
//                      pollResult first); restart() resumes polling, and so does the first successful request
//                      anywhere in the app (the shell retries /api/health every 10 s while the banner shows)
//         "error"      other HTTP errors; code = machine code or status
// Polling stops on completed / failed / 404 / errors and is aborted when the page unmounts.
// The page is keyed by id, so a new id always starts from a fresh "loading" state.

const LOADING = { phase: "loading", data: null };

export function useResultPolling(id, { intervalMs = POLL_INTERVAL_MS, maxMs = POLL_MAX_MS } = {}) {
  const [outcome, setOutcome] = useState(LOADING);
  const [round, setRound] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    pollResult(id, { intervalMs, maxMs, signal: controller.signal })
      .then((resolved) => {
        if (!controller.signal.aborted) setOutcome(outcomeFromPoll(resolved));
      })
      .catch((err) => {
        if (!controller.signal.aborted) setOutcome(outcomeFromError(err));
      });
    return () => controller.abort();
  }, [id, intervalMs, maxMs, round]);

  const restart = useCallback(() => {
    setOutcome(LOADING);
    setRound((n) => n + 1);
  }, []);

  // The backend came back (cold start finished): leave the error screen without making the user press retry.
  const phase = outcome.phase;
  useEffect(() => {
    if (phase !== "network" || typeof window === "undefined") return undefined;
    window.addEventListener(BACKEND_UP_EVENT, restart);
    return () => window.removeEventListener(BACKEND_UP_EVENT, restart);
  }, [phase, restart]);

  return { ...outcome, restart };
}
