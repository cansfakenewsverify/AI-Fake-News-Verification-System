import Banner from "../../components/Banner.jsx";
import { t } from "../../i18n.js";
import { showNoSourceBanner } from "../../lib/verdict.js";

// "No fact-checker has verified this" banner (S-07; FR-16; spec 5.3, 8.3 S2 element 4 / state 10;
// ResultStates.dc.html "not verified").
// Shown below the verdict block and above the summary whenever showNoSourceBanner(result) is true
// (verification_status unverified, or missing), for red and yellow lights alike. showNoSourceBanner
// already excludes UNVERIFIABLE and AI-unavailable results (spec 5.3 exception). The light colour itself
// stays the backend frame_type: this component never recolours the verdict.

export default function NoVerifiedSourceBanner({ result }) {
  if (!showNoSourceBanner(result)) return null;
  return (
    <Banner
      title={t("no_verified_source_title")}
      body={t("no_verified_source_body")}
      style={{ padding: "12px 16px", borderRadius: "var(--radius-card)" }}
    />
  );
}
