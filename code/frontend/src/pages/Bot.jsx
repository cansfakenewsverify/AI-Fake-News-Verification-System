import Card from "../components/Card.jsx";
import Chip from "../components/Chip.jsx";
import EmptyState from "../components/EmptyState.jsx";
import Icon from "../components/Icon.jsx";
import Skeleton from "../components/Skeleton.jsx";
import { t } from "../i18n.js";
import { useDocumentTitle } from "../lib/useDocumentTitle.js";
import ReplyItem from "./bot/ReplyItem.jsx";
import { backoffText, badgeKey, isOff, lastErrorText, lastPollText, replyRows } from "./bot/botModel.js";
import { useBotStatus } from "./bot/useBotStatus.js";

// Bot status page "/bot" (S-11; FR-11 P0 read-only version; spec 8.3 S6, 8.4 S6 row; Bot.dc.html "S6").
// - Mode badge (neutral chip): live / sim (with the mentions.json path) / off; token_invalid overrides the mode.
// - Status card: last poll (time + checked / replied / skipped / errors), backoff, latest error in red
//   (spec 8.3 states it is red: a status alert, not a verdict colour).
// - dev_mode_notice box, then the latest 10 replies (ReplyItem).
// - States: loading skeleton; off -> threads_off only; status request failed -> backend_down, recovering on the
//   next 2 s round. No inputs, no "run a poll" button and no admin token anywhere on this page.

function Section({ title, children }) {
  return (
    <section className="flex flex-col" style={{ gap: 12 }}>
      <h2 className="t-h2 m-0" style={{ color: "var(--c-ink)" }}>
        {title}
      </h2>
      {children}
    </section>
  );
}

function StatusCard({ status }) {
  const error = lastErrorText(status);
  const backoff = backoffText(status);
  return (
    <Card>
      <div className="flex flex-col" style={{ gap: 12 }}>
        <div className="flex flex-col" style={{ gap: 4 }}>
          <p className="t-caption m-0" style={{ color: "var(--c-ink-3)" }}>
            {t("threads_poll_title")}
          </p>
          <p className="t-body m-0" style={{ color: "var(--c-ink)", overflowWrap: "anywhere" }}>
            {lastPollText(status)}
          </p>
          {backoff ? (
            <p className="t-sub m-0" style={{ color: "var(--c-ink-2)" }}>
              {backoff}
            </p>
          ) : null}
        </div>
        <div className="flex flex-col" style={{ gap: 4 }}>
          <p className="t-caption m-0" style={{ color: "var(--c-ink-3)" }}>
            {t("threads_last_error_title")}
          </p>
          <p
            className="t-body m-0"
            style={{ color: error ? "var(--c-red)" : "var(--c-ink-2)", overflowWrap: "anywhere" }}
          >
            {error ?? t("threads_no_error")}
          </p>
        </div>
      </div>
    </Card>
  );
}

function Notice({ children }) {
  return (
    <div
      role="note"
      className="flex items-start"
      style={{
        gap: 8,
        padding: 12,
        background: "var(--c-bg)",
        border: "1px solid var(--c-line)",
        borderRadius: "var(--radius-btn)",
      }}
    >
      <Icon name="info" size={16} style={{ color: "var(--c-accent)", marginTop: 2 }} />
      <p className="t-sub m-0 min-w-0" style={{ color: "var(--c-ink-2)" }}>
        {children}
      </p>
    </div>
  );
}

export default function Bot() {
  const title = t("threads_title");
  useDocumentTitle(title);
  const { phase, status, replies } = useBotStatus();
  const badge = badgeKey(status);
  const rows = replyRows(replies);

  let body;
  if (phase === "loading") {
    body = (
      <Card aria-busy="true">
        <Skeleton lines={3} />
      </Card>
    );
  } else if (phase === "error" && !status) {
    body = <EmptyState mark="exclamation" title={t("backend_down")} />;
  } else if (isOff(status)) {
    body = <EmptyState title={t("threads_off")} />;
  } else {
    body = (
      <>
        <StatusCard status={status} />
        {status.dev_mode_notice ? <Notice>{status.dev_mode_notice}</Notice> : null}
        <Section title={t("threads_replies_title")}>
          {rows.length === 0 ? (
            <p className="t-body m-0" style={{ color: "var(--c-ink-2)" }}>
              {t("threads_replies_empty")}
            </p>
          ) : (
            <ul className="m-0 list-none p-0">
              {rows.map((row) => (
                <li key={row.key} className="border-b border-line" style={{ padding: "12px 0" }}>
                  <ReplyItem row={row} />
                </li>
              ))}
            </ul>
          )}
        </Section>
      </>
    );
  }

  return (
    <div className="flex flex-col" style={{ gap: 16, padding: "24px 0" }}>
      <div className="flex flex-wrap items-center" style={{ gap: 12 }}>
        <h1 className="t-h1 m-0" style={{ color: "var(--c-ink)" }}>
          {title}
        </h1>
        {badge ? <Chip variant="neutral">{t(badge)}</Chip> : null}
      </div>
      {status?.mode === "sim" && status.sim_mentions_path ? (
        <p className="t-caption m-0" style={{ color: "var(--c-ink-3)", overflowWrap: "anywhere" }}>
          {t("threads_sim_path", { path: status.sim_mentions_path })}
        </p>
      ) : null}
      {phase === "error" && status ? (
        <p className="t-sub m-0" style={{ color: "var(--c-ink-2)" }}>
          {t("backend_down")}
        </p>
      ) : null}
      {body}
    </div>
  );
}
