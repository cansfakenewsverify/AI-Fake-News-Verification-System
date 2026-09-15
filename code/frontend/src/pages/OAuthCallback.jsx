import { useState } from "react";
import { useLocation } from "react-router-dom";
import { t } from "../i18n.js";
import { useDocumentTitle } from "../lib/useDocumentTitle.js";
import Card from "../components/Card.jsx";
import Button from "../components/Button.jsx";
import Icon from "../components/Icon.jsx";

// S7 /oauth/callback（S-12；spec §7.3 步驟 1、§8.3 S7）
// Meta 授權完成後導回此頁：只顯示 ?code= 讓負責人複製回終端機（scripts/threads_auth.py）。
// 授權碼不外流：本頁不發網路請求、不寫瀏覽器儲存、不輸出到主控台。
// location.search 不含 hash，Meta 追加的 "#_" 自然被排除。

const codeStyle = {
  display: "block",
  marginTop: 16,
  padding: 12,
  borderRadius: "var(--radius-btn)",
  border: "1px solid var(--c-line)",
  background: "var(--c-bg)",
  color: "var(--c-ink)",
  fontFamily: 'ui-monospace, "SFMono-Regular", Consolas, monospace',
  fontSize: 14,
  lineHeight: "20px",
  wordBreak: "break-all",
  userSelect: "all",
  WebkitUserSelect: "all",
};

export default function OAuthCallback() {
  const { search } = useLocation();
  const params = new URLSearchParams(search);
  const code = params.get("code");
  const error = params.get("error");
  const errorDescription = params.get("error_description");

  const [copied, setCopied] = useState(false);
  const title = code ? t("oauth_cb_title") : t("error_title");
  useDocumentTitle(title);

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
    } catch {
      // 複製失敗（權限或非安全來源）：保留 <code> 可全選文字，使用者手動複製。
      setCopied(false);
    }
  }

  return (
    <main style={{ padding: "24px 16px", maxWidth: 640, margin: "0 auto" }}>
      <Card>
        <h1 className="t-h1" style={{ margin: 0 }}>{title}</h1>
        {code ? (
          <>
            <p style={{ margin: "8px 0 0", fontSize: 15, lineHeight: "24px", color: "var(--c-ink-2)" }}>
              {t("oauth_cb_body")}
            </p>
            <code style={codeStyle}>{code}</code>
            <div style={{ marginTop: 16 }}>
              <Button onClick={handleCopy} icon={<Icon name="copy" />} aria-live="polite">
                {copied ? t("btn_copied") : t("btn_copy_code")}
              </Button>
            </div>
          </>
        ) : (
          (error || errorDescription) && (
            <dl style={{ margin: "12px 0 0", fontSize: 15, lineHeight: "24px", color: "var(--c-ink-2)" }}>
              {error && (
                <div>
                  <dt style={{ display: "inline" }}>error: </dt>
                  <dd style={{ display: "inline", margin: 0, wordBreak: "break-all" }}>{error}</dd>
                </div>
              )}
              {errorDescription && (
                <div>
                  <dt style={{ display: "inline" }}>error_description: </dt>
                  <dd style={{ display: "inline", margin: 0, wordBreak: "break-all" }}>{errorDescription}</dd>
                </div>
              )}
            </dl>
          )
        )}
      </Card>
    </main>
  );
}
