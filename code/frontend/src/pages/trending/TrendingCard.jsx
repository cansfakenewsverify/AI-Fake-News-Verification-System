import { Link } from "react-router-dom";
import Card from "../../components/Card.jsx";
import Chip from "../../components/Chip.jsx";
import DotRow from "../../components/DotRow.jsx";
import { t } from "../../i18n.js";
import { labelSourceKey } from "../../lib/verdict.js";
import { sourceOrgName } from "./sourceOrgName.js";
import { formatDate, isUnverifiedRecord, parseServerTime, trendingLink, trendingTitle } from "./trendingModel.js";

// Trending card (S-09 step 3/4; spec 8.3 S3, FR-06 acceptance 2/5/6; Trending.dc.html card).
// - DotRow: 8px dot + verdict word (listVerdict) + title (2 lines). The item handed to DotRow carries only
//   risk_type and verified, so a stray frame_type can never paint an unverified card.
// - Meta row: "organisation + date" (13px --c-ink-2) on the left; label_source as 13px --c-ink-3 text
//   (never a chip, brief 7-4) and, for unverified records, the grey chip_pending on the right.
// - Whole card is the link: result_id -> <Link to="/r/{id}">; else source_url in a new tab
//   (target="_blank" rel="noopener"); no usable target -> plain block.
// - All user-visible text comes from i18n.js or ./copy.js (organisation names).

const META_TEXT = { fontSize: 13, lineHeight: "20px", color: "var(--c-ink-2)", overflowWrap: "anywhere" };
const LABEL_SOURCE_TEXT = { fontSize: 13, lineHeight: "16px", color: "var(--c-ink-3)" };

export default function TrendingCard({ record }) {
  const unverified = isUnverifiedRecord(record);
  const link = trendingLink(record);
  const date = formatDate(parseServerTime(record?.created_at));
  const meta = [sourceOrgName(record?.source_url), date].filter(Boolean).join("・");
  const labelKey = labelSourceKey(record?.label_source);

  const content = (
    <>
      <DotRow item={{ risk_type: record?.risk_type, verified: record?.verified }} title={trendingTitle(record)} />
      {meta || labelKey || unverified ? (
        <div className="flex flex-wrap items-center justify-between" style={{ columnGap: 8, rowGap: 4, minHeight: 20 }}>
          <span className="min-w-0" style={META_TEXT}>
            {meta}
          </span>
          <span className="flex shrink-0 items-center" style={{ gap: 8 }}>
            {labelKey ? (
              <span data-label-source="" style={LABEL_SOURCE_TEXT}>
                {t(labelKey)}
              </span>
            ) : null}
            {unverified ? <Chip variant="pending">{t("chip_pending")}</Chip> : null}
          </span>
        </div>
      ) : null}
    </>
  );

  const cardStyle = { display: "flex", flexDirection: "column", gap: 10 };
  const common = { "data-trending-id": record?.id ?? undefined, style: cardStyle };

  if (link?.to) {
    return (
      <Card as={Link} to={link.to} className="cursor-pointer no-underline" {...common}>
        {content}
      </Card>
    );
  }
  if (link?.href) {
    return (
      <Card as="a" href={link.href} target="_blank" rel="noopener" {...common}>
        {content}
      </Card>
    );
  }
  return <Card {...common}>{content}</Card>;
}
