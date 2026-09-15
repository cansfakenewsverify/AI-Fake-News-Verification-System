import { t } from "../i18n.js";
import { useDocumentTitle } from "../lib/useDocumentTitle.js";

// 佔位頁（P-07）：正式畫面由 screens lane 實作。
export default function NotFound() {
  const title = t("result_not_found_title");
  useDocumentTitle(title);
  return (
    <div style={{ padding: "24px 0" }}>
      <h1>{title}</h1>
      <p>此頁由 screens lane 實作</p>
    </div>
  );
}
