import Button from "../../components/Button.jsx";
import Icon from "../../components/Icon.jsx";
import { t } from "../../i18n.js";
import { KNOWLEDGE_COPY } from "./copy.js";

// Knowledge search row (S-10 step 1; spec 8.3 S4; Knowledge.dc.html search row).
// <form role="search">: input type=search (16px text, 44px box, search icon) + submit button (44px).
// Enter and the button both submit through the form; the parent receives the raw value and owns
// trimming / request state. The input is labelled by visually hidden text, not by its placeholder.
// Focus ring: drawn around the whole input box (focus-within), the inner input has no own outline.

export default function SearchBar({ value, onChange, onSubmit, className = "", style }) {
  function handleSubmit(event) {
    event.preventDefault();
    onSubmit?.(value);
  }

  return (
    <form
      role="search"
      onSubmit={handleSubmit}
      className={`flex items-stretch ${className}`}
      style={{ gap: 8, ...style }}
    >
      <label
        className="flex min-w-0 flex-1 cursor-text items-center focus-within:[outline:2px_solid_var(--c-accent)] focus-within:[outline-offset:2px]"
        style={{
          gap: 8,
          minHeight: 44,
          padding: "0 12px",
          background: "var(--c-bg)",
          border: "1px solid var(--c-line)",
          borderRadius: "var(--radius-btn)",
        }}
      >
        <Icon name="search" size={20} style={{ color: "var(--c-ink-3)" }} />
        <span className="sr-only">{KNOWLEDGE_COPY.search_label}</span>
        <input
          type="search"
          value={value}
          onChange={(event) => onChange?.(event.target.value)}
          placeholder={t("knowledge_search_placeholder")}
          enterKeyHint="search"
          autoComplete="off"
          className="min-w-0 flex-1 bg-transparent placeholder:text-ink-3 focus-visible:[outline:none]"
          style={{
            height: 42,
            padding: 0,
            border: 0,
            fontFamily: "inherit",
            fontSize: 16,
            lineHeight: "24px",
            color: "var(--c-ink)",
          }}
        />
      </label>
      <Button type="submit" variant="primary" fullWidth={false} className="shrink-0" style={{ minHeight: 44 }}>
        {KNOWLEDGE_COPY.btn_search}
      </Button>
    </form>
  );
}
