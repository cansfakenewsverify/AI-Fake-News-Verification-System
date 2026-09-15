import { useEffect, useState, useSyncExternalStore } from "react";
import Card from "../../components/Card.jsx";
import Icon from "../../components/Icon.jsx";
import Skeleton from "../../components/Skeleton.jsx";
import { t } from "../../i18n.js";

// Result page loading state (S-04; spec 8.3 S2 state 1, 8.6 aria-busy; ResultStates.dc.html "loading").
// - P-13 Skeleton (3 bars) in a card where the verdict block will appear
// - Three-step indicator "check cache -> read content -> AI review": a purely time-based animation that
//   moves one step every 2 s and loops; with prefers-reduced-motion it stays on the first step.
//   Done steps: filled ink circle with a check; current: accent ring + dot, aria-current="step";
//   upcoming: outlined circle, ink-3 label.
// - result_loading is the page's single <h1> while loading; the container carries aria-busy="true".

const STEP_KEYS = ["result_step_1", "result_step_2", "result_step_3"];
const STEP_MS = 2000;
const REDUCED_MOTION_QUERY = "(prefers-reduced-motion: reduce)";

function subscribeReducedMotion(callback) {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") return () => {};
  const mql = window.matchMedia(REDUCED_MOTION_QUERY);
  if (typeof mql.addEventListener === "function") {
    mql.addEventListener("change", callback);
    return () => mql.removeEventListener("change", callback);
  }
  mql.addListener(callback);
  return () => mql.removeListener(callback);
}

function prefersReducedMotion() {
  return typeof window !== "undefined" && typeof window.matchMedia === "function"
    ? window.matchMedia(REDUCED_MOTION_QUERY).matches
    : false;
}

function StepMark({ status }) {
  const base = { width: 24, height: 24, borderRadius: "50%" };
  if (status === "done") {
    return (
      <span
        aria-hidden="true"
        className="relative z-10 flex items-center justify-center"
        style={{ ...base, background: "var(--c-ink)", color: "var(--c-ink-inverse)" }}
      >
        <Icon name="check" size={16} />
      </span>
    );
  }
  if (status === "current") {
    return (
      <span
        aria-hidden="true"
        className="relative z-10 flex items-center justify-center"
        style={{ ...base, background: "var(--c-bg)", border: "2px solid var(--c-accent)" }}
      >
        <span style={{ width: 8, height: 8, borderRadius: "50%", background: "var(--c-accent)" }} />
      </span>
    );
  }
  return (
    <span
      aria-hidden="true"
      className="relative z-10 block"
      style={{ ...base, background: "var(--c-bg)", border: "1px solid var(--c-line)" }}
    />
  );
}

const LABEL_COLOR = { done: "var(--c-ink)", current: "var(--c-accent)", upcoming: "var(--c-ink-3)" };

export default function ResultLoading() {
  const reducedMotion = useSyncExternalStore(subscribeReducedMotion, prefersReducedMotion, () => false);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    if (reducedMotion) return undefined;
    const timer = setInterval(() => setTick((n) => n + 1), STEP_MS);
    return () => clearInterval(timer);
  }, [reducedMotion]);

  const active = reducedMotion ? 0 : tick % STEP_KEYS.length;

  return (
    <div aria-busy="true" className="flex flex-col" style={{ gap: 12, padding: "16px 0 24px" }}>
      <Card>
        <Skeleton lines={3} />
      </Card>

      <Card style={{ display: "flex", flexDirection: "column", gap: 16 }}>
        <ol aria-label={t("result_steps_label")} className="m-0 grid list-none grid-cols-3 p-0">
          {STEP_KEYS.map((key, index) => {
            const status = index < active ? "done" : index === active ? "current" : "upcoming";
            return (
              <li
                key={key}
                aria-current={status === "current" ? "step" : undefined}
                className="relative flex min-w-0 flex-col items-center"
                style={{ gap: 6 }}
              >
                {index > 0 ? (
                  // connector from the previous circle's edge to this circle's edge
                  <span
                    aria-hidden="true"
                    className="absolute"
                    style={{
                      top: 11,
                      height: 2,
                      left: "calc(-50% + 16px)",
                      right: "calc(50% + 16px)",
                      background: index <= active ? "var(--c-ink)" : "var(--c-line)",
                    }}
                  />
                ) : null}
                <StepMark status={status} />
                <span
                  className="max-w-full text-center"
                  style={{ fontSize: 13, lineHeight: "16px", fontWeight: 500, color: LABEL_COLOR[status] }}
                >
                  {t(key)}
                </span>
              </li>
            );
          })}
        </ol>
        <h1 className="t-sub m-0 text-center" style={{ color: "var(--c-ink-2)" }}>
          {t("result_loading")}
        </h1>
      </Card>
    </div>
  );
}
