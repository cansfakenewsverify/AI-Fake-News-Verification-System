import { useEffect, useRef, useState } from "react";
import { getThreadsReplies, getThreadsStatus } from "../../lib/api.js";
import { REPLIES_LIMIT, STATUS_POLL_MS } from "./botModel.js";

// Bot status polling (S-11; FR-11): GET /api/threads/status once on mount, then every 2 s while the page is visible
// (a tab opened in the background still shows its data; hidden tabs stop polling); the replies list is
// re-read only when last_poll_at changes (a new poll round finished). Requests are aborted on unmount; a failed status
// request shows backend_down and the next successful round recovers on its own. Read-only: no admin token anywhere.
// Returns { phase: "loading" | "ok" | "error", status, replies }.

export function useBotStatus({ intervalMs = STATUS_POLL_MS } = {}) {
  const [state, setState] = useState({ phase: "loading", status: null, replies: [] });
  const lastPoll = useRef(undefined);

  useEffect(() => {
    let alive = true;
    let busy = false;
    const controller = new AbortController();
    const { signal } = controller;

    async function tick(force = false) {
      if (busy || (!force && typeof document !== "undefined" && document.hidden)) return;
      busy = true;
      try {
        const status = await getThreadsStatus({ signal });
        let replies = null;
        if (status?.last_poll_at !== lastPoll.current) {
          const body = await getThreadsReplies(REPLIES_LIMIT, { signal });
          replies = Array.isArray(body?.records) ? body.records : [];
          lastPoll.current = status?.last_poll_at;
        }
        if (alive) {
          setState((prev) => ({ phase: "ok", status, replies: replies ?? prev.replies }));
        }
      } catch {
        if (alive && !signal.aborted) setState((prev) => ({ ...prev, phase: "error" }));
      } finally {
        busy = false;
      }
    }

    tick(true);
    const timer = setInterval(() => tick(), intervalMs);
    const onVisible = () => {
      if (!document.hidden) tick();
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      alive = false;
      controller.abort();
      clearInterval(timer);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [intervalMs]);

  return state;
}
