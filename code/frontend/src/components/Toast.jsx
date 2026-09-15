import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { EXTRA, STRINGS, t } from "../i18n.js";

// Toast（P-17；spec FR-05 驗收 3、§8.3 S2 狀態 8、§8.6 aria-live）
// - ToastProvider 掛在 AppShell；useToast().show(textKeyOrText, { ms = 3000 })
//   參數是 i18n key（如 "toast_share"）時自動翻譯，否則視為已翻譯文字
// - 畫面底部置中；手機位於分頁列與 sticky 動作列之上：
//   bottom = --tabbar-h（AppShell 設定）＋ --action-bar-h（sticky 動作列掛載時設在 :root，預設 0）＋安全區
// - live region（role="status" aria-live="polite"）常駐 DOM，內容變動才會被輔助技術朗讀
// - 同時只顯示一則：新訊息取代舊訊息並重新計時；fade-in 在 prefers-reduced-motion 時由全域規則關閉

const ToastContext = createContext(null);
const NOOP = { show() {} };

function resolveText(textKeyOrText) {
  const text = textKeyOrText == null ? "" : String(textKeyOrText);
  const known =
    Object.prototype.hasOwnProperty.call(STRINGS, text) || Object.prototype.hasOwnProperty.call(EXTRA, text);
  return known ? t(text) : text;
}

export function ToastProvider({ children }) {
  const [toast, setToast] = useState(null);
  const timerRef = useRef(null);
  const seqRef = useRef(0);

  const show = useCallback((textKeyOrText, { ms = 3000 } = {}) => {
    const text = resolveText(textKeyOrText);
    if (!text) return;
    seqRef.current += 1;
    const id = seqRef.current;
    setToast({ id, text });
    clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => {
      setToast((current) => (current && current.id === id ? null : current));
    }, ms);
  }, []);

  useEffect(() => () => clearTimeout(timerRef.current), []);

  const value = useMemo(() => ({ show }), [show]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div
        role="status"
        aria-live="polite"
        className="pointer-events-none fixed inset-x-0 z-50 flex justify-center px-4"
        style={{
          bottom: "calc(var(--tabbar-h, 0px) + var(--action-bar-h, 0px) + env(safe-area-inset-bottom) + 16px)",
        }}
      >
        {toast ? (
          <div
            key={toast.id}
            className="fade-in"
            style={{
              maxWidth: 608,
              padding: "12px 16px",
              borderRadius: "var(--radius-btn)",
              background: "var(--c-ink)",
              color: "var(--c-ink-inverse)",
              boxShadow: "var(--shadow-card)",
              fontSize: 15,
              lineHeight: "22px",
              textAlign: "center",
              overflowWrap: "anywhere",
            }}
          >
            {toast.text}
          </div>
        ) : null}
      </div>
    </ToastContext.Provider>
  );
}

// 在 ToastProvider 外呼叫時回傳 no-op，不拋錯
// eslint-disable-next-line react-refresh/only-export-components
export function useToast() {
  return useContext(ToastContext) ?? NOOP;
}
