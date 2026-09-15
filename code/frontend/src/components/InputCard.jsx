import { useEffect, useId, useImperativeHandle, useLayoutEffect, useRef } from "react";
import { t } from "../i18n.js";
import { MAX_CHARS, countChars } from "../lib/validateInput.js";
import Button from "./Button.jsx";
import Card from "./Card.jsx";
import SegmentedTabs from "./SegmentedTabs.jsx";

// 首頁輸入卡（P-16；brief §3.5；Main.dc.html、Primitives.dc.html「3.5 輸入卡」；spec §8.3 S1 元件 2）
// 受控元件：mode／value 由呼叫端持有；onChange(nextValue: string)、onModeChange(mode)、onSubmit({mode, value})。
// - modes 預設 ["text","url"]；圖片 tab 由 S-13 加入（隱藏圖片 tab 屬偏離 mockup，已列 O-01 待確認）
// - 文字模式 textarea：最少 4 行、自動長高到 6 行後捲動（spec §8.5「textarea 4–6 行」、送出鈕留在首屏），
//   右下 `{n}/20000`（code point 計數，與後端一致）
// - 網址模式 <input type="url" inputmode="url">；form noValidate，不跳瀏覽器原生驗證泡泡
// - error：已翻譯的錯誤文字（呼叫端以 t(validateInput(...)) 或伺服器訊息傳入），
//   以 inline 紅字、aria-live="polite"、aria-describedby 連到輸入框顯示，不跳瀏覽器對話框
// - 主按鈕維持可按；submitting 時 disabled＋spinner＋「查證中…」，另以 sr-only live region 宣告
// - ref 方法：fill(text) 切到文字模式並填入（範例 chip 用，不送出）；focus() 聚焦目前輸入框

const SUPPORTED_MODES = ["text", "url"];
const LINE = 24;
const PAD = 12;
const BORDER = 1;
const MIN_ROWS = 4;
const MAX_ROWS = 6;
const MIN_HEIGHT = MIN_ROWS * LINE + 2 * PAD + 2 * BORDER;
const MAX_HEIGHT = MAX_ROWS * LINE + 2 * PAD + 2 * BORDER;

const fieldStyle = {
  display: "block",
  width: "100%",
  background: "var(--c-bg)",
  color: "var(--c-ink)",
  border: `${BORDER}px solid var(--c-line)`,
  borderRadius: "var(--radius-btn)",
  padding: PAD,
  fontFamily: "inherit",
  fontSize: 16,
  lineHeight: `${LINE}px`,
};

function autoGrow(el) {
  if (!el) return;
  el.style.height = "auto";
  const next = Math.min(Math.max(el.scrollHeight + 2 * BORDER, MIN_HEIGHT), MAX_HEIGHT);
  el.style.height = `${next}px`;
}

export default function InputCard({
  ref,
  modes = SUPPORTED_MODES,
  mode = "text",
  onModeChange,
  value = "",
  onChange,
  onSubmit,
  submitting = false,
  error,
  className = "",
  style,
}) {
  const base = useId();
  const textareaRef = useRef(null);
  const urlRef = useRef(null);

  const available = modes.filter((m) => SUPPORTED_MODES.includes(m));
  const tabModes = available.length ? available : SUPPORTED_MODES;
  const activeMode = tabModes.includes(mode) ? mode : tabModes[0];
  const isUrl = activeMode === "url";

  const panelId = `${base}-panel`;
  const errorId = `${base}-error`;
  const countId = `${base}-count`;
  const describedBy = [error ? errorId : null, isUrl ? null : countId].filter(Boolean).join(" ") || undefined;

  useImperativeHandle(
    ref,
    () => ({
      fill(text) {
        onModeChange?.("text");
        onChange?.(String(text ?? ""));
      },
      focus() {
        (isUrl ? urlRef : textareaRef).current?.focus();
      },
    }),
    [onModeChange, onChange, isUrl],
  );

  // 內容或模式變動時重新量測高度；視窗寬度改變（旋轉）時換行數也會變
  useLayoutEffect(() => {
    autoGrow(textareaRef.current);
  }, [value, activeMode]);

  useEffect(() => {
    const onResize = () => autoGrow(textareaRef.current);
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  function handleSubmit(event) {
    event.preventDefault();
    if (submitting) return;
    onSubmit?.({ mode: activeMode, value });
  }

  const tabs = tabModes.map((m) => ({ value: m, label: t(`tab_${m}`) }));
  const fieldA11y = {
    "aria-label": t("input_label"),
    "aria-invalid": error ? true : undefined,
    "aria-describedby": describedBy,
  };

  return (
    <Card className={className} style={style}>
      <form noValidate onSubmit={handleSubmit} className="flex flex-col" style={{ gap: 12 }}>
        <SegmentedTabs
          tabs={tabs}
          value={activeMode}
          onChange={(next) => onModeChange?.(next)}
          label={t("input_mode_label")}
          idBase={base}
          panelId={panelId}
        />

        <div
          role="tabpanel"
          id={panelId}
          aria-labelledby={`${base}-tab-${activeMode}`}
          className="flex flex-col"
          style={{ gap: 6 }}
        >
          {isUrl ? (
            <input
              ref={urlRef}
              type="url"
              inputMode="url"
              autoComplete="url"
              autoCapitalize="none"
              autoCorrect="off"
              spellCheck={false}
              value={value}
              onChange={(event) => onChange?.(event.target.value)}
              placeholder={t("input_placeholder_url")}
              className="placeholder:text-ink-3"
              style={{ ...fieldStyle, height: 48, paddingBlock: 0 }}
              {...fieldA11y}
            />
          ) : (
            <textarea
              ref={textareaRef}
              rows={MIN_ROWS}
              value={value}
              onChange={(event) => onChange?.(event.target.value)}
              placeholder={t("input_placeholder_text")}
              className="placeholder:text-ink-3"
              style={{ ...fieldStyle, resize: "none", minHeight: MIN_HEIGHT, maxHeight: MAX_HEIGHT, overflowY: "auto" }}
              {...fieldA11y}
            />
          )}

          <div className="flex items-start justify-between" style={{ gap: 12 }}>
            <p
              id={errorId}
              aria-live="polite"
              className="m-0 min-w-0 flex-1"
              style={{ fontSize: 14, lineHeight: "20px", color: "var(--c-red)" }}
            >
              {error || ""}
            </p>
            {isUrl ? null : (
              <span id={countId} className="shrink-0" style={{ fontSize: 13, lineHeight: "20px", color: "var(--c-ink-3)" }}>
                {`${countChars(value)}/${MAX_CHARS}`}
              </span>
            )}
          </div>
        </div>

        <Button type="submit" loading={submitting}>
          {submitting ? t("btn_analyzing") : t("btn_analyze")}
        </Button>
        <span className="sr-only" aria-live="polite">
          {submitting ? t("btn_analyzing") : ""}
        </span>
        <p className="t-sub m-0" style={{ color: "var(--c-ink-2)" }}>
          {t("analyze_note")}
        </p>
      </form>
    </Card>
  );
}
