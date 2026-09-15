import { useEffect } from "react";
import { BRAND, t } from "../i18n.js";

// Sets document.title = title + page_title_suffix (e.g. "今日熱門查核｜全民查證公社").
// Without a title the tab shows the brand name only.
export function useDocumentTitle(title) {
  useEffect(() => {
    document.title = title ? title + t("page_title_suffix") : BRAND;
  }, [title]);
}
