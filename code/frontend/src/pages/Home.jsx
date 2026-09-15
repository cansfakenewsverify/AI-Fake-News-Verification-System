import { useEffect, useRef, useState } from "react";
import Card from "../components/Card.jsx";
import ConfirmDialog from "../components/ConfirmDialog.jsx";
import Icon from "../components/Icon.jsx";
import InputCard from "../components/InputCard.jsx";
import { t } from "../i18n.js";
import { clearAll, isAvailable, listRecent } from "../lib/history.js";
import { useDocumentTitle } from "../lib/useDocumentTitle.js";
import { validateInput } from "../lib/validateInput.js";
import BotHowtoCard from "./home/BotHowtoCard.jsx";
import ExampleChips from "./home/ExampleChips.jsx";
import RecentHistory from "./home/RecentHistory.jsx";
import { useSubmitAnalysis } from "./home/useSubmitAnalysis.js";

// Home page "/" (spec 8.3 S1, 8.5 mobile order; Main.dc.html "S1").
// Order: title (h1 home_tagline + home_sub) -> input card (+ quota card) -> examples (only without
// history) -> Threads card -> recent checks (only with history).
// - Input modes are text and url only: the image tab stays hidden until S-13 (FR-03 is P1),
//   a deviation from Main.dc.html pending owner confirmation in O-01.
// - Validation runs before submit; errors render inline inside InputCard (never a browser dialog)
//   and the submit button stays enabled.
// - Submit (S-02, useSubmitAnalysis): button spinner + live announcement while posting, then
//   /r/{id}. 422/429 feedback is inline; 429 daily_cap_reached shows the quota card; network errors
//   rely on the AppShell backend_down banner. The typed input is never cleared on failure.
// - Example chips fill the text box through InputCard.fill() and never submit.
// - Recent checks (S-03): the latest 5 localStorage entries. With entries, the examples and
//   history_empty are hidden; clearing asks ConfirmDialog (confirm_clear) first and then moves focus
//   to the empty-state line, because the clear button it came from no longer exists. Without usable
//   storage the empty-state line reads history_unavailable and everything else keeps working.
// - All user-visible text comes from i18n.js (this file must stay free of Han characters).

const MODES = ["text", "url"];
const RECENT_LIMIT = 5;

function readHistory() {
  if (!isAvailable()) return { available: false, entries: [] };
  return { available: true, entries: listRecent(RECENT_LIMIT) };
}

function QuotaCard() {
  return (
    <Card style={{ display: "flex", alignItems: "flex-start", gap: 12, marginTop: 12 }}>
      <span
        aria-hidden="true"
        className="flex shrink-0 items-center justify-center rounded-full"
        style={{
          width: 24,
          height: 24,
          border: "1px solid var(--c-line)",
          background: "var(--c-bg)",
          color: "var(--c-ink-2)",
        }}
      >
        <Icon name="exclamation" size={16} />
      </span>
      <div className="flex min-w-0 flex-col" style={{ gap: 4 }}>
        <p className="m-0" style={{ fontSize: 16, lineHeight: "24px", fontWeight: 500, color: "var(--c-ink)" }}>
          {t("quota_exceeded_title")}
        </p>
        <p className="t-sub m-0" style={{ color: "var(--c-ink-2)" }}>
          {t("quota_exceeded_body")}
        </p>
      </div>
    </Card>
  );
}

export default function Home() {
  useDocumentTitle();
  const inputRef = useRef(null);
  const [mode, setMode] = useState("text");
  const [value, setValue] = useState("");
  const [error, setError] = useState(null);
  const [quotaReached, setQuotaReached] = useState(false);
  const { submit, submitting } = useSubmitAnalysis();

  const [history, setHistory] = useState(readHistory);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const emptyStatusRef = useRef(null);
  const focusEmptyStatusRef = useRef(false);

  // Runs after ConfirmDialog (a child) has closed its modal in the same commit, so focus can land.
  useEffect(() => {
    if (!focusEmptyStatusRef.current) return;
    focusEmptyStatusRef.current = false;
    emptyStatusRef.current?.focus();
  });

  function handleModeChange(next) {
    setMode(next);
    setError(null);
  }

  function handleChange(next) {
    setValue(next);
    setError(null);
  }

  async function handleSubmit({ mode: submitMode, value: submitValue }) {
    const errorKey = validateInput(submitMode, submitValue);
    if (errorKey) {
      setError(t(errorKey));
      inputRef.current?.focus();
      return;
    }
    setError(null);
    setQuotaReached(false);

    const outcome = await submit({ mode: submitMode, value: submitValue });
    if (!outcome || outcome.ok) return;
    if (outcome.feedback.type === "inline") setError(outcome.feedback.message);
    else if (outcome.feedback.type === "quota") setQuotaReached(true);
  }

  function handleConfirmClear() {
    clearAll();
    setConfirmOpen(false);
    focusEmptyStatusRef.current = true;
    setHistory(readHistory());
  }

  const hasEntries = history.entries.length > 0;

  return (
    <div className="flex flex-col" style={{ gap: 24, padding: "24px 0" }}>
      <div className="flex flex-col" style={{ gap: 6 }}>
        <h1 className="t-h1 m-0" style={{ color: "var(--c-ink)" }}>
          {t("home_tagline")}
        </h1>
        <p className="t-body m-0" style={{ color: "var(--c-ink-2)" }}>
          {t("home_sub")}
        </p>
      </div>

      <div className="flex flex-col">
        <InputCard
          ref={inputRef}
          modes={MODES}
          mode={mode}
          onModeChange={handleModeChange}
          value={value}
          onChange={handleChange}
          onSubmit={handleSubmit}
          submitting={submitting}
          error={error}
        />
        <div aria-live="polite">{quotaReached ? <QuotaCard /> : null}</div>
      </div>

      {hasEntries ? null : (
        <div className="flex flex-col" style={{ gap: 8 }}>
          <ExampleChips onPick={(text) => inputRef.current?.fill(text)} />
          <p ref={emptyStatusRef} tabIndex={-1} className="t-sub m-0" style={{ color: "var(--c-ink-2)" }}>
            {t(history.available ? "history_empty" : "history_unavailable")}
          </p>
        </div>
      )}

      <BotHowtoCard />

      <RecentHistory entries={history.entries} onClearRequest={() => setConfirmOpen(true)} />

      <ConfirmDialog open={confirmOpen} onConfirm={handleConfirmClear} onCancel={() => setConfirmOpen(false)} />
    </div>
  );
}
