import { useNavigate } from "react-router-dom";
import Button from "../../components/Button.jsx";
import EmptyState from "../../components/EmptyState.jsx";
import { t } from "../../i18n.js";
import { followSpaLink } from "./resultState.js";

// Result page 404 (S-04; FR-04 acceptance 3; spec 5.3 result_not_found, 8.3 S2 state 9).
// Unknown or pruned id: result_not_found_title (page <h1>) + _body + "back to home" link-button.

export default function ResultNotFound() {
  const navigate = useNavigate();
  return (
    <EmptyState
      mark="question"
      titleAs="h1"
      title={t("result_not_found_title")}
      body={t("result_not_found_body")}
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
