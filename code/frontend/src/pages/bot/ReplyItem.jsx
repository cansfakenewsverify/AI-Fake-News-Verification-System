import { Link } from "react-router-dom";
import Disclosure from "../../components/Disclosure.jsx";
import DotRow from "../../components/DotRow.jsx";
import Icon from "../../components/Icon.jsx";
import { t } from "../../i18n.js";

// One bot reply (S-11; Bot.dc.html "latest replies"): verdict dot (stored frame_type) + the post excerpt + who and
// when; the full reply text in a collapsed Disclosure (pre-wrap keeps the traffic-light emoji and line breaks);
// "original post" opens the Threads permalink in a new tab, "result page" goes to /r/{result_id} inside the app.

const LINK_STYLE = { gap: 4, minHeight: 44, fontSize: 14, fontWeight: 500, color: "var(--c-accent)" };

export default function ReplyItem({ row }) {
  return (
    <div className="flex flex-col" style={{ gap: 8 }}>
      <DotRow item={row.item} title={row.title} meta={row.meta} />
      {row.replyText ? (
        <Disclosure summary={t("threads_reply_full")}>
          <p className="t-body m-0" style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere", color: "var(--c-ink)" }}>
            {row.replyText}
          </p>
        </Disclosure>
      ) : null}
      {row.permalink || row.resultTo ? (
        <div className="flex flex-wrap items-center" style={{ columnGap: 16 }}>
          {row.permalink ? (
            <a href={row.permalink} target="_blank" rel="noopener" className="inline-flex items-center no-underline" style={LINK_STYLE}>
              {t("btn_view_post")}
              <Icon name="external" size={16} />
            </a>
          ) : null}
          {row.resultTo ? (
            <Link to={row.resultTo} className="inline-flex items-center no-underline" style={LINK_STYLE}>
              {t("btn_view_result")}
            </Link>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
