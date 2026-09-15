import { useCallback, useState } from "react";
import { useNavigate } from "react-router-dom";
import { t } from "../../i18n.js";
import { homePrefillState, loadSubmittedInput, useSubmitAnalysis } from "../home/useSubmitAnalysis.js";

// "Reanalyze" on the result page (S-04 failed state, S-06 AI-unavailable card; spec 8.3 S2 states 5, 6).
// - The home submit (S-02) saved the full input in sessionStorage["fcc_input_{id}"]: resend it through
//   the same useSubmitAnalysis flow (new history entry, new stored input, navigate to the new /r/{id}).
// - Nothing stored (e.g. the link was opened from Threads): go to "/" with the input_preview prefilled
//   and do not submit.
// Returns {reanalyze, submitting, message}; message is a list of lines for 422/429 feedback
// (network errors show the AppShell backend_down banner instead, so message stays null).

/** useSubmitAnalysis feedback -> lines to show under the reanalyze button, or null. */
export function reanalyzeMessage(feedback) {
  if (!feedback) return null;
  if (feedback.type === "inline") return feedback.message ? [feedback.message] : null;
  if (feedback.type === "quota") return [t("quota_exceeded_title"), t("quota_exceeded_body")];
  return null;
}

export function useReanalyze(id, data) {
  const navigate = useNavigate();
  const { submit, submitting } = useSubmitAnalysis();
  const [message, setMessage] = useState(null);
  const inputType = data?.input_type;
  const inputPreview = data?.input_preview;

  const reanalyze = useCallback(async () => {
    setMessage(null);
    const stored = loadSubmittedInput(id);
    if (!stored) {
      navigate("/", { state: homePrefillState(inputType, inputPreview) });
      return;
    }
    const outcome = await submit({ mode: stored.input_type, value: stored.content });
    if (outcome && !outcome.ok) setMessage(reanalyzeMessage(outcome.feedback));
  }, [id, inputType, inputPreview, navigate, submit]);

  return { reanalyze, submitting, message };
}
