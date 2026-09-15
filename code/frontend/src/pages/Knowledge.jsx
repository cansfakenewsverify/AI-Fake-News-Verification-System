import { t } from "../i18n.js";
import { useDocumentTitle } from "../lib/useDocumentTitle.js";

// 佔位頁（P-07）：正式畫面由 screens lane 實作。
export default function Knowledge() {
  const title = t("knowledge_title");
  useDocumentTitle(title);
  return (
    <main style={{ padding: "24px 16px", maxWidth: 720, margin: "0 auto" }}>
      <h1>{title}</h1>
      <p>此頁由 screens lane 實作</p>
    </main>
  );
}
