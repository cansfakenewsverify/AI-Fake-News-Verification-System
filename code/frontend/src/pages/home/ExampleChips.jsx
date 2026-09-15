import { useId } from "react";
import Chip from "../../components/Chip.jsx";
import { t } from "../../i18n.js";

// Home page example messages (S-01; spec 8.3 S1 state "empty"; Main.dc.html "examples").
// - Section caption is EXTRA.home_examples_title; chip texts are 8.7 example_1..3 (verbatim).
// - Clicking a chip calls onPick(text): the page fills the text box via InputCard.fill()
//   and never submits.
// - Chip with onClick renders a <button> whose transparent hit area is >= 44px around the
//   28px pill (brief 7-4). The "live" palette (white pill, 1px line border) is used because
//   the "filter" palette would add aria-pressed, and these chips are not toggles.
// - All user-visible text comes from i18n.js (this folder must stay free of Han characters).

const EXAMPLE_KEYS = ["example_1", "example_2", "example_3"];

export default function ExampleChips({ onPick, className = "", style }) {
  const captionId = useId();

  return (
    <section aria-labelledby={captionId} className={`flex flex-col ${className}`} style={{ gap: 4, ...style }}>
      <p id={captionId} className="t-sub m-0" style={{ fontWeight: 500, color: "var(--c-ink-2)" }}>
        {t("home_examples_title")}
      </p>
      <ul className="m-0 flex list-none flex-wrap items-center p-0" style={{ columnGap: 8, rowGap: 0 }}>
        {EXAMPLE_KEYS.map((key) => {
          const text = t(key);
          return (
            <li key={key} className="min-w-0 max-w-full">
              <Chip variant="live" onClick={() => onPick?.(text)}>
                {text}
              </Chip>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
