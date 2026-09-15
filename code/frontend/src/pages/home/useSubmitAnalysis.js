import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { t } from "../../i18n.js";
import { ApiError, analyzeText, analyzeUrl } from "../../lib/api.js";
import { addEntry } from "../../lib/history.js";

// Home page submit flow (S-02; spec 8.3 S1 states "submitting", "429", "backend down"; 5.2; 5.7).
// submit({mode, value}) -> Promise of
//   { ok: true, id }                  task created: history entry written, input saved, navigated
//   { ok: false, feedback }           feedback: {type:"inline", message} | {type:"quota"} | {type:"backend_down"}
//   null                              ignored (already submitting) or aborted because the page unmounted
// - text mode posts the value as typed; url mode posts it trimmed (the backend strips it too)
// - on success: history.addEntry({id, input_type, preview, created_at}),
//   sessionStorage["fcc_input_{id}"] = JSON {input_type, content} for "reanalyze" on /r/{id} (S-04/S-06),
//   then navigate("/r/{id}") right away (FR-04: the result page polls by itself)
// - network/timeout and gateway 502/503/504 -> no inline message: api.js dispatches fcc:backend-down and
//   AppShell shows the backend_down banner; the caller keeps the input and the button becomes clickable
// - All user-visible text comes from i18n.js (this folder must stay free of Han characters).

export const INPUT_KEY_PREFIX = "fcc_input_";
export const DEFAULT_RETRY_AFTER_SECONDS = 60;

const GATEWAY_DOWN = new Set([502, 503, 504]);

export function inputStorageKey(id) {
  return `${INPUT_KEY_PREFIX}${id}`;
}

function defaultSessionStorage() {
  try {
    return globalThis.sessionStorage;
  } catch {
    return undefined;
  }
}

/** Saves the full submitted input for a later resend; returns false when storage is unavailable. */
export function saveSubmittedInput(id, { input_type, content } = {}, storage = defaultSessionStorage()) {
  try {
    if (!storage || typeof id !== "string" || !id) return false;
    storage.setItem(inputStorageKey(id), JSON.stringify({ input_type, content }));
    return true;
  } catch {
    return false;
  }
}

/** Reads what saveSubmittedInput stored: {input_type: "text"|"url", content} or null. */
export function loadSubmittedInput(id, storage = defaultSessionStorage()) {
  try {
    const raw = storage?.getItem(inputStorageKey(id));
    if (!raw) return null;
    const data = JSON.parse(raw);
    const validType = data?.input_type === "text" || data?.input_type === "url";
    return validType && typeof data.content === "string" && data.content !== "" ? data : null;
  } catch {
    return null;
  }
}

// Home prefill (S-04 "reanalyze" without a stored input, e.g. a /r/{id} link opened from Threads):
// the result page navigates to "/" with router state {prefill: {mode, value}}; Home fills the input card
// from it and never submits by itself. Router state keeps the text out of the URL.

/** Router state for navigate("/", {state}) that prefills the home input; null for image or empty input. */
export function homePrefillState(inputType, content) {
  const mode = inputType === "url" ? "url" : inputType === "text" ? "text" : null;
  if (!mode || typeof content !== "string" || content.trim() === "") return null;
  return { prefill: { mode, value: content } };
}

/** Reads homePrefillState() back from location.state: {mode: "text"|"url", value} or null. */
export function readHomePrefill(state) {
  const prefill = state && typeof state === "object" ? state.prefill : null;
  if (!prefill || (prefill.mode !== "text" && prefill.mode !== "url")) return null;
  return typeof prefill.value === "string" && prefill.value !== "" ? { mode: prefill.mode, value: prefill.value } : null;
}

/** One-line history preview: whitespace runs collapse to a single space (history.js caps it at 80). */
export function previewOf(content) {
  return String(content ?? "").replace(/\s+/g, " ").trim();
}

/** result_id (spec 5.2) with task_id as a fallback; null when the response carries neither. */
export function resultIdOf(response) {
  for (const key of ["result_id", "task_id"]) {
    const value = response?.[key];
    if (typeof value === "string" && value !== "") return value;
  }
  return null;
}

function retrySeconds(retryAfter) {
  const n = Number(retryAfter);
  return Number.isFinite(n) && n > 0 ? Math.ceil(n) : DEFAULT_RETRY_AFTER_SECONDS;
}

function inline(message) {
  return { type: "inline", message };
}

// ApiError falls back to the code, kind or "HTTP {status}" when the body has no readable message.
function readableMessage(err) {
  const message = typeof err.message === "string" ? err.message.trim() : "";
  if (!message || message === err.code || message === err.kind || /^HTTP \d+$/.test(message)) return "";
  return message;
}

/** Maps a failed analyze request to home page feedback (spec 5.7 error codes). */
export function submitErrorFeedback(err) {
  if (!(err instanceof ApiError)) return inline(t("error_server", { code: "unknown" }));
  if (err.kind === "network" || err.kind === "timeout") return { type: "backend_down" };

  const status = Number(err.status);
  if (GATEWAY_DOWN.has(status)) return { type: "backend_down" };

  if (status === 422) {
    if (err.code === "invalid_url") return inline(t("err_invalid_url"));
    if (err.code === "blocked_url") return inline(t("err_blocked_url"));
    if (err.code === "validation_error" && readableMessage(err)) return inline(readableMessage(err));
  }
  if (status === 429) {
    if (err.code === "daily_cap_reached") return { type: "quota" };
    return inline(t("err_rate", { n: retrySeconds(err.retryAfter) }));
  }
  return inline(t("error_server", { code: err.code || status || "unknown" }));
}

export function useSubmitAnalysis() {
  const navigate = useNavigate();
  const [submitting, setSubmitting] = useState(false);
  const controllerRef = useRef(null);

  // Leaving the page mid-request aborts it, so a late response cannot navigate away from the new page.
  useEffect(() => () => controllerRef.current?.abort(), []);

  const submit = useCallback(
    async ({ mode, value } = {}) => {
      if (controllerRef.current) return null;
      const inputType = mode === "url" ? "url" : "text";
      const raw = String(value ?? "");
      const content = inputType === "url" ? raw.trim() : raw;

      const controller = new AbortController();
      controllerRef.current = controller;
      setSubmitting(true);

      const fail = (feedback) => {
        controllerRef.current = null;
        setSubmitting(false);
        return { ok: false, feedback };
      };

      let response;
      try {
        const call = inputType === "url" ? analyzeUrl : analyzeText;
        response = await call(content, { signal: controller.signal });
      } catch (err) {
        if (controller.signal.aborted) return null;
        return fail(submitErrorFeedback(err));
      }
      if (controller.signal.aborted) return null;

      const id = resultIdOf(response);
      if (!id) return fail(inline(t("error_server", { code: "invalid_response" })));

      addEntry({ id, input_type: inputType, preview: previewOf(content), created_at: new Date().toISOString() });
      saveSubmittedInput(id, { input_type: inputType, content });
      // submitting stays true until the page unmounts, so the button never flashes back before navigation
      navigate(`/r/${encodeURIComponent(id)}`);
      return { ok: true, id };
    },
    [navigate],
  );

  return { submit, submitting };
}
