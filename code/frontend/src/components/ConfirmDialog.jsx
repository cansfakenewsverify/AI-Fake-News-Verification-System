import { useEffect, useId, useRef } from "react";
import { t } from "../i18n.js";
import Button from "./Button.jsx";

// 二次確認對話框（P-17；spec FR-08 驗收 2、§8.6 dialog focus trap）
// 原生 <dialog> + showModal()：背景 inert、Esc 關閉；另在對話框內把 Tab／Shift+Tab 循環在按鈕之間，
// 避免焦點跳到瀏覽器網址列。開啟時焦點落在「取消」，關閉後焦點回到開啟前的觸發元素。
// 受控：open 由呼叫端持有；按取消或 Esc → onCancel()；按確認 → onConfirm()。
// 兩個回呼都必須把 open 設回 false（對話框在 Esc 時會先被瀏覽器關閉，open 需同步回去才能再次開啟）。
// 文案預設：標題 confirm_clear、確認鈕 btn_clear_history、取消鈕 btn_cancel。

const FOCUSABLE =
  'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

export default function ConfirmDialog({ open, title, body, confirmText, cancelText, onConfirm, onCancel }) {
  const dialogRef = useRef(null);
  const cancelRef = useRef(null);
  const returnFocusRef = useRef(null);
  const settledRef = useRef(false); // 這次開啟的結果是否已回報給呼叫端（避免重複 onCancel）
  const titleId = useId();
  const bodyId = useId();

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (open && !dialog.open) {
      settledRef.current = false;
      returnFocusRef.current = document.activeElement;
      dialog.showModal();
      cancelRef.current?.focus();
    } else if (!open && dialog.open) {
      dialog.close();
    }
  }, [open]);

  function reportCancel() {
    if (!open || settledRef.current) return;
    settledRef.current = true;
    onCancel?.();
  }

  function reportConfirm() {
    settledRef.current = true;
    onConfirm?.();
  }

  // Esc：瀏覽器先同步派發 cancel 再關閉 → 立即回報。
  // close 事件（Chromium 在下一個畫格才派發）是保底：頁面沒有使用者啟用時 Esc 會略過 cancel 直接關閉。
  function handleClose() {
    const target = returnFocusRef.current;
    returnFocusRef.current = null;
    if (target && target.isConnected && typeof target.focus === "function") target.focus();
    reportCancel();
  }

  function handleKeyDown(event) {
    if (event.key !== "Tab") return;
    const items = Array.from(dialogRef.current?.querySelectorAll(FOCUSABLE) ?? []);
    if (items.length === 0) return;
    const first = items[0];
    const last = items[items.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }

  return (
    <dialog
      ref={dialogRef}
      aria-labelledby={titleId}
      aria-describedby={body ? bodyId : undefined}
      onCancel={reportCancel}
      onClose={handleClose}
      onKeyDown={handleKeyDown}
      className="m-auto backdrop:bg-[var(--c-backdrop)]"
      style={{
        width: "min(400px, calc(100vw - 32px))",
        maxWidth: "none",
        padding: 20,
        border: "1px solid var(--c-line)",
        borderRadius: "var(--radius-card)",
        background: "var(--c-surface)", // 同卡片底色：深色主題下與變暗的頁面仍有層次
        color: "var(--c-ink)",
      }}
    >
      <h2 id={titleId} className="m-0" style={{ fontSize: 16, lineHeight: "24px", fontWeight: 500 }}>
        {title ?? t("confirm_clear")}
      </h2>
      {body ? (
        <p id={bodyId} className="t-sub m-0" style={{ marginTop: 8, color: "var(--c-ink-2)" }}>
          {body}
        </p>
      ) : null}
      <div className="grid grid-cols-2" style={{ gap: 8, marginTop: 20 }}>
        <Button ref={cancelRef} variant="secondary" fullWidth onClick={reportCancel}>
          {cancelText ?? t("btn_cancel")}
        </Button>
        <Button variant="primary" fullWidth onClick={reportConfirm}>
          {confirmText ?? t("btn_clear_history")}
        </Button>
      </div>
    </dialog>
  );
}
