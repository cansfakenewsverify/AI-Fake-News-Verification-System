import Button from "../../components/Button.jsx";
import EmptyState from "../../components/EmptyState.jsx";
import { t } from "../../i18n.js";

// Result page error states (S-04; spec 8.3 S2 states 2 and 6; 8.7 error_* / btn_*).
// kind:
//   "timeout"  error_timeout + "refresh" (onRetry restarts polling; the id stays in the URL)
//   "network"  error_title + error_network + btn_retry (onRetry resumes polling)
//   "error"    error_title + error_server({code}) + btn_retry (unexpected HTTP error while polling)
//   "failed"   error_title + error_server({code}) + btn_reanalyze (status=failed: resend the same input,
//              or go home with the preview prefilled when the input was not stored; see useReanalyze)
// The title is the page's single <h1>. reanalyze = {reanalyze, submitting, message} from useReanalyze.

function ReanalyzeAction({ reanalyze }) {
  const { submitting, message } = reanalyze;
  return (
    <div className="flex flex-col items-center" style={{ gap: 8 }}>
      <Button onClick={reanalyze.reanalyze} loading={submitting} fullWidth={false} style={{ minWidth: 160 }}>
        {submitting ? t("btn_analyzing") : t("btn_reanalyze")}
      </Button>
      <div aria-live="polite" className="flex flex-col" style={{ gap: 2, maxWidth: 480 }}>
        {(message || []).map((line) => (
          <p key={line} className="t-sub m-0" style={{ color: "var(--c-ink-2)", overflowWrap: "anywhere" }}>
            {line}
          </p>
        ))}
      </div>
    </div>
  );
}

export default function ResultError({ kind, code, onRetry, reanalyze }) {
  if (kind === "timeout") {
    return (
      <EmptyState
        mark="exclamation"
        titleAs="h1"
        title={t("error_timeout")}
        action={
          <Button onClick={onRetry} fullWidth={false} style={{ minWidth: 160 }}>
            {t("btn_refresh")}
          </Button>
        }
      />
    );
  }

  if (kind === "failed") {
    return (
      <EmptyState
        mark="close"
        titleAs="h1"
        title={t("error_title")}
        body={t("error_server", { code: code || "analysis_failed" })}
        action={reanalyze ? <ReanalyzeAction reanalyze={reanalyze} /> : null}
      />
    );
  }

  return (
    <EmptyState
      mark={kind === "network" ? "exclamation" : "close"}
      titleAs="h1"
      title={t("error_title")}
      body={kind === "network" ? t("error_network") : t("error_server", { code: code || "unknown" })}
      action={
        <Button onClick={onRetry} fullWidth={false} style={{ minWidth: 160 }}>
          {t("btn_retry")}
        </Button>
      }
    />
  );
}
