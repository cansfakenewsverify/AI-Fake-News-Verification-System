import { useNavigate } from "react-router-dom";
import Button from "../components/Button.jsx";
import EmptyState from "../components/EmptyState.jsx";
import { t } from "../i18n.js";
import { useDocumentTitle } from "../lib/useDocumentTitle.js";
import { followSpaLink } from "./result/resultState.js";

// 未知路由的 404（不是 /r/:id 找不到，那個是 ResultNotFound）。
export default function NotFound() {
  const navigate = useNavigate();
  const title = t("route_not_found_title");
  useDocumentTitle(title);
  return (
    <EmptyState
      mark="question"
      titleAs="h1"
      title={title}
      body={t("route_not_found_body")}
      action={
        <Button
          as="a"
          href="/"
          onClick={(event) => followSpaLink(event, navigate, "/")}
          fullWidth={false}
          style={{ minWidth: 160 }}
        >
          {t("btn_home")}
        </Button>
      }
    />
  );
}
