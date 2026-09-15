import { useEffect } from "react";
import { useParams } from "react-router-dom";
import { t } from "../i18n.js";
import { updateEntry } from "../lib/history.js";
import { useDocumentTitle } from "../lib/useDocumentTitle.js";
import ResultAiUnavailable from "./result/ResultAiUnavailable.jsx";
import ResultError from "./result/ResultError.jsx";
import ResultLoading from "./result/ResultLoading.jsx";
import ResultNotFound from "./result/ResultNotFound.jsx";
import ResultSuccess from "./result/ResultSuccess.jsx";
import ResultUnverifiable from "./result/ResultUnverifiable.jsx";
import { failureCode, historyPatch, resultView } from "./result/resultState.js";
import { useReanalyze } from "./result/useReanalyze.js";
import { useResultPolling } from "./result/useResultPolling.js";

// Result page /r/:id (FR-04; spec 5.3, 8.3 S2).
// - Keyed by id: opening another /r/{id} (e.g. after "reanalyze") remounts with a fresh polling round.
// - Phases come from useResultPolling (loading / timeout / not_found / network / error / failed / completed).
// - Completed results are dispatched by resultView(): the ai_unavailable boolean -> grey card (never the
//   summary prefix), risk_type UNVERIFIABLE -> yellow "cannot verify", everything else -> success.
// - Completed results write risk_type / frame_type back to the local history and set the tab title to
//   "{frame_label}｜{BRAND}".
// - A persistent polite live region announces loading, the verdict and errors (spec 8.6).
// - All user-visible text comes from i18n.js.

export default function Result() {
  const { id = "" } = useParams();
  return <ResultPage key={id} id={id} />;
}

function announcementFor(phase, view, data, code) {
  if (phase === "loading") return t("result_loading");
  if (phase === "timeout") return t("error_timeout");
  if (phase === "not_found") return t("result_not_found_title");
  if (phase === "network") return t("error_network");
  if (phase === "error") return t("error_server", { code: code || "unknown" });
  if (phase === "failed" || view === "invalid") return t("error_server", { code: failureCode(data) });
  return view === "ai_unavailable" ? t("frame_grey") : data?.result?.frame_label || "";
}

function titleFor(phase, view, data) {
  // brand only while the verdict is not known yet (loading, or still pending after 90 s)
  if (phase === "loading" || phase === "timeout") return undefined;
  if (phase === "not_found") return t("result_not_found_title");
  if (phase === "completed" && view === "ai_unavailable") return t("frame_grey");
  if (phase === "completed" && view !== "invalid") return data?.result?.frame_label || undefined;
  return t("error_title");
}

function ResultPage({ id }) {
  const { phase, data, code, restart } = useResultPolling(id);
  const reanalyze = useReanalyze(id, data);
  const view = phase === "completed" ? resultView(data) : null;

  useEffect(() => {
    if (phase === "completed" && view !== "invalid") updateEntry(id, historyPatch(data));
  }, [id, phase, view, data]);

  useDocumentTitle(titleFor(phase, view, data));

  let content;
  if (phase === "loading") {
    content = <ResultLoading />;
  } else if (phase === "not_found") {
    content = <ResultNotFound />;
  } else if (phase === "timeout" || phase === "network" || phase === "error") {
    content = <ResultError kind={phase} code={code} onRetry={restart} />;
  } else if (phase === "failed" || view === "invalid") {
    content = <ResultError kind="failed" code={failureCode(data)} reanalyze={reanalyze} />;
  } else if (view === "ai_unavailable") {
    content = <ResultAiUnavailable data={data} reanalyze={reanalyze} />;
  } else if (view === "unverifiable") {
    content = <ResultUnverifiable data={data} />;
  } else {
    content = <ResultSuccess data={data} />;
  }

  return (
    <>
      <p className="sr-only" aria-live="polite">
        {announcementFor(phase, view, data, code)}
      </p>
      {content}
    </>
  );
}
