import { useId } from "react";
import Card from "../../components/Card.jsx";
import Icon from "../../components/Icon.jsx";
import { t } from "../../i18n.js";

// Threads how-to card on the home page (S-01; spec 8.3 S1 element 3; Main.dc.html "Threads card").
// - Title: EXTRA.home_threads_card_title (h2 18/26/700).
// - Body: 8.7 bot_howto; {BOT_HANDLE} is filled by t(), {n} is the reply window below.
// - Dev-mode line: the first sentence of 8.7 dev_mode_notice (the card shows one sentence, as in
//   Main.dc.html and the /api/threads/status dev_mode_notice), with a neutral info icon.
// - Neutral colours only: red/yellow/green are reserved for verdicts (spec 8.1).

// Minutes promised in bot_howto: mirrors the backend THREADS_POLL_MINUTES default (config.py = 5;
// Main.dc.html shows 5). The demo week polls every minute, which still keeps the promise.
const BOT_REPLY_MINUTES = 5;

// U+3002 ideographic full stop, written as an escape so this file stays free of Han characters.
const SENTENCE_END = "。";

function firstSentence(text) {
  const end = text.indexOf(SENTENCE_END);
  return end === -1 ? text : text.slice(0, end + 1);
}

export default function BotHowtoCard({ className = "", style }) {
  const titleId = useId();

  return (
    <Card
      as="section"
      aria-labelledby={titleId}
      className={className}
      style={{ display: "flex", flexDirection: "column", gap: 8, ...style }}
    >
      <h2 id={titleId} className="t-h2 m-0" style={{ color: "var(--c-ink)" }}>
        {t("home_threads_card_title")}
      </h2>
      <p className="t-body m-0" style={{ color: "var(--c-ink)", overflowWrap: "anywhere" }}>
        {t("bot_howto", { n: BOT_REPLY_MINUTES })}
      </p>
      <div className="flex items-start" style={{ gap: 8 }}>
        <Icon name="info" size={16} style={{ marginTop: 2, color: "var(--c-ink-3)" }} />
        <p className="t-sub m-0 min-w-0" style={{ color: "var(--c-ink-2)", overflowWrap: "anywhere" }}>
          {firstSentence(t("dev_mode_notice"))}
        </p>
      </div>
    </Card>
  );
}
