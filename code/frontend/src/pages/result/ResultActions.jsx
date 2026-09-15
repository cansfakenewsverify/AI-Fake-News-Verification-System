import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import Button from "../../components/Button.jsx";
import Icon from "../../components/Icon.jsx";
import { useToast } from "../../components/Toast.jsx";
import { t } from "../../i18n.js";
import { buildThreadsIntent } from "./buildThreadsIntent.js";
import { followSpaLink } from "./resultState.js";

// Result action bar (S-08; FR-05; spec 5.3 share, 7.7, 8.3 S2 element 6 / state 8, 8.5; Result.dc.html).
// - "Share to Threads": a real <a target="_blank" rel="noopener"> to the Threads Web Intent (no scripted
//   popup, which in-app browsers block), rendered only when the backend sent a usable share object. On
//   click the label turns into btn_share_opened for 3 s and the toast_share toast appears.
// - "Copy link": navigator.clipboard.writeText(share.url ?? location.href) -> btn_copied for 3 s; when the
//   API is missing or throws, the URL is shown under the buttons as selectable text (user-select: all).
// - "Check another": link to "/".
// - sticky (mobile): sticks above the bottom tab bar (bottom = --tabbar-h + safe area) and publishes its
//   height as --action-bar-h on :root so toasts stay above it; placed last in the page so, once scrolled to
//   the end, it rests after the fine print and never covers it. Desktop renders a plain row.

const FEEDBACK_MS = 3000;

export default function ResultActions({ share, sticky = false }) {
  const navigate = useNavigate();
  const toast = useToast();
  const barRef = useRef(null);
  const shareTimer = useRef(null);
  const copyTimer = useRef(null);
  const [shareOpened, setShareOpened] = useState(false);
  const [copied, setCopied] = useState(false);
  const [fallbackUrl, setFallbackUrl] = useState(null);

  const intent = buildThreadsIntent(share);
  const shareUrl = typeof share?.url === "string" && share.url ? share.url : null;

  useEffect(
    () => () => {
      clearTimeout(shareTimer.current);
      clearTimeout(copyTimer.current);
    },
    [],
  );

  useEffect(() => {
    const el = barRef.current;
    if (!sticky || !el) return undefined;
    const root = document.documentElement;
    const publish = () => root.style.setProperty("--action-bar-h", `${Math.ceil(el.getBoundingClientRect().height)}px`);
    publish();
    const observer = typeof ResizeObserver !== "undefined" ? new ResizeObserver(publish) : null;
    observer?.observe(el);
    return () => {
      observer?.disconnect();
      root.style.removeProperty("--action-bar-h");
    };
  }, [sticky]);

  function handleShare() {
    setShareOpened(true);
    toast.show("toast_share");
    clearTimeout(shareTimer.current);
    shareTimer.current = setTimeout(() => setShareOpened(false), FEEDBACK_MS);
  }

  async function handleCopy() {
    const url = shareUrl ?? window.location.href;
    try {
      const clipboard = navigator.clipboard;
      if (!clipboard || typeof clipboard.writeText !== "function") throw new Error("clipboard unavailable");
      await clipboard.writeText(url);
      setFallbackUrl(null);
      setCopied(true);
      clearTimeout(copyTimer.current);
      copyTimer.current = setTimeout(() => setCopied(false), FEEDBACK_MS);
    } catch {
      setCopied(false);
      setFallbackUrl(url);
    }
  }

  const content = (
    <div className="flex flex-col" style={{ gap: 8 }}>
      {intent ? (
        <Button
          as="a"
          href={intent}
          target="_blank"
          data-testid="share-threads"
          icon={<Icon name="share" />}
          onClick={handleShare}
        >
          {shareOpened ? t("btn_share_opened") : t("btn_share_threads")}
        </Button>
      ) : null}
      <div className="grid grid-cols-2" style={{ gap: 8 }}>
        <Button variant="secondary" fullWidth data-testid="copy-link" icon={<Icon name="copy" />} onClick={handleCopy}>
          {copied ? t("btn_copied") : t("btn_copy_link")}
        </Button>
        <Button
          as="a"
          href="/"
          variant="text"
          fullWidth
          onClick={(event) => followSpaLink(event, navigate, "/")}
          style={{ textDecoration: "underline", textUnderlineOffset: 2 }}
        >
          {t("btn_check_another")}
        </Button>
      </div>
      {fallbackUrl ? (
        <p
          data-testid="copy-fallback"
          className="m-0"
          style={{
            padding: "8px 12px",
            border: "1px solid var(--c-line)",
            borderRadius: "var(--radius-btn)",
            background: "var(--c-surface)",
            color: "var(--c-ink)",
            fontSize: 15,
            lineHeight: "22px",
            wordBreak: "break-all",
            userSelect: "all",
            WebkitUserSelect: "all",
          }}
        >
          {fallbackUrl}
        </p>
      ) : null}
      <span className="sr-only" aria-live="polite">
        {copied ? t("btn_copied") : ""}
      </span>
    </div>
  );

  if (!sticky) return content;

  return (
    <div
      ref={barRef}
      className="sticky z-30 -mx-4 border-t border-line bg-bg"
      style={{ bottom: "calc(var(--tabbar-h, 0px) + env(safe-area-inset-bottom))", padding: "12px 16px" }}
    >
      {content}
    </div>
  );
}
