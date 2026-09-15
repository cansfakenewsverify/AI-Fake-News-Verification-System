import { useParams } from "react-router-dom";
import { t } from "../i18n.js";
import { useDocumentTitle } from "../lib/useDocumentTitle.js";

// 佔位頁（P-07）：正式結果頁由 screens lane（S-04..S-08）實作。
export default function Result() {
  const { id } = useParams();
  const title = t("result_loading");
  useDocumentTitle(title);
  return (
    <main style={{ padding: "24px 16px", maxWidth: 720, margin: "0 auto" }}>
      <h1>{title}</h1>
      <p>
        <code>{id}</code>
      </p>
      <p>此頁由 screens lane 實作</p>
    </main>
  );
}
