import { useEffect, useId, useRef, useState } from "react";
import Card from "../../components/Card.jsx";
import Icon from "../../components/Icon.jsx";
import { t } from "../../i18n.js";
import { httpUrlOrNull } from "./resultState.js";

// "What you checked" excerpt card (S-05; spec 8.3 S2 element 2; Result.dc.html section 1).
// - h2 section_input + card with input_preview (the backend sends <=200 chars; URLs in full).
// - More than 3 lines: clamped to 3 lines plus the mockup's 44px chevron toggle (aria-expanded /
//   aria-controls, label EXTRA.excerpt_expand) that reveals the full text. P-17 Disclosure is not used
//   here because it hides its content entirely while collapsed, and the card must keep showing the first
//   3 lines. The toggle only appears when the text really overflows (measured with ResizeObserver;
//   without ResizeObserver the text is never clamped).
// - URL input breaks anywhere (word-break: break-all) and stays plain text: the submitted URL may be the
//   scam itself, so it is never turned into a link.
// - platform_post (Threads origin): from_threads "@username" links to the original post permalink
//   (target=_blank rel=noopener; http(s) only, otherwise plain text).

const CAN_MEASURE = typeof ResizeObserver !== "undefined";

export default function InputExcerpt({ data }) {
  const titleId = useId();
  const textId = useId();
  const textRef = useRef(null);
  const [expanded, setExpanded] = useState(false);
  const [overflows, setOverflows] = useState(false);

  const preview = typeof data?.input_preview === "string" ? data.input_preview : "";
  const isUrl = data?.input_type === "url";
  const post = data?.platform_post && typeof data.platform_post === "object" ? data.platform_post : null;
  const username = typeof post?.username === "string" && post.username ? post.username : null;
  const permalink = httpUrlOrNull(post?.permalink);

  // Measure only while clamped; once expanded the toggle must stay so the text can be collapsed again.
  useEffect(() => {
    const el = textRef.current;
    if (!CAN_MEASURE || expanded || !el) return undefined;
    const observer = new ResizeObserver(() => setOverflows(el.scrollHeight - el.clientHeight > 1));
    observer.observe(el);
    return () => observer.disconnect();
  }, [preview, expanded]);

  const clamped = CAN_MEASURE && !expanded;
  const showToggle = expanded || overflows;

  return (
    <section aria-labelledby={titleId} className="flex flex-col" style={{ gap: 8 }}>
      <h2 id={titleId} className="t-h2 m-0" style={{ color: "var(--c-ink)" }}>
        {t("section_input")}
      </h2>
      <Card style={{ display: "flex", flexDirection: "column", gap: 4 }}>
        <p
          id={textId}
          ref={textRef}
          className={`t-body m-0 ${clamped ? "line-clamp-3" : ""}`}
          style={{
            color: "var(--c-ink)",
            whiteSpace: "pre-line",
            overflowWrap: "anywhere",
            wordBreak: isUrl ? "break-all" : undefined,
          }}
        >
          {preview}
        </p>

        {username || showToggle ? (
          <div className="flex items-center justify-between" style={{ gap: 12 }}>
            {username ? (
              permalink ? (
                <a
                  href={permalink}
                  target="_blank"
                  rel="noopener"
                  className="inline-flex min-h-11 min-w-0 items-center"
                  style={{ gap: 4, fontSize: 14, lineHeight: "20px", overflowWrap: "anywhere" }}
                >
                  <span className="min-w-0">{t("from_threads", { username })}</span>
                  <Icon name="external" size={16} />
                </a>
              ) : (
                <span className="t-sub" style={{ color: "var(--c-ink-2)", overflowWrap: "anywhere" }}>
                  {t("from_threads", { username })}
                </span>
              )
            ) : (
              <span />
            )}
            {showToggle ? (
              <button
                type="button"
                aria-expanded={expanded}
                aria-controls={textId}
                aria-label={t("excerpt_expand")}
                onClick={() => setExpanded((value) => !value)}
                className="-mr-3 inline-flex h-11 w-11 shrink-0 cursor-pointer items-center justify-center"
                style={{ color: "var(--c-ink-2)" }}
              >
                <Icon name="chevron" size={20} style={{ transform: expanded ? "rotate(180deg)" : undefined }} />
              </button>
            ) : null}
          </div>
        ) : null}
      </Card>
    </section>
  );
}
