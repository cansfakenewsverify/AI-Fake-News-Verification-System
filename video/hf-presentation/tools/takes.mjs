// What to record on the live site, take by take.
//
// Budget rule: `aiCalls` is how many NEW AI verifications the take spends on the production site
// (hash / vector cache hits are free). capture.mjs refuses to exceed 12 in total.
//
// Input choices (docs/demo/demo_posts.md §3, and the cloud knowledge base read on 2026-09-20):
//   - SCAM_EXAMPLE is the site's own example chip, so scene 2 needs no typing and the cold-open
//     message and the first verification are the same message.
//   - VECTOR_REWRITE rewords a row that really is in the cloud knowledge base WITH a MyGoPen
//     verdict ("搭飛機拍到巴威颱風眼的影片", 5 hits) — the vector layer only matches verified rows.
//   - The knowledge search uses 健保: its six rows all cite 健保署 / 衛福部 / 警政署 pages, none of
//     the 24 rows whose only "source" is an unverified Cofacts submission.
export const SITE = "https://fakenewsverify.vercel.app";

export const SCAM_EXAMPLE = "健保卡即日起停用，請點連結重新驗證";
export const VECTOR_REWRITE = "網傳有人搭飛機的時候拍到巴威颱風的颱風眼畫面，這是真的嗎";
// A real MyGoPen fact-check report. The system reads the page and answers 「此為已被查核的假訊息：
// 「歐洲熱浪導致義大利、德國的紅綠燈開始融化的影片」」, which is the clearest URL output the live
// site produces. Checked 2026-09-20: it answers from the URL cache, so the take costs no AI call.
export const FACTCHECK_URL = "https://www.mygopen.com/2026/07/traffic-light.html";
export const BAD_URL = "健保卡停用";

const TAB_TEXT = { sel: "[role=tab]", nth: 0 };
const TAB_URL = { sel: "[role=tab]", nth: 1 };
const INPUT = { sel: "textarea[aria-label]" };
const URL_INPUT = { placeholder: "貼上新聞或貼文網址" };
const SUBMIT = { text: "開始查證" };

/** Wait until the result page has left the three-step loader. */
const RESULT_READY = { waitFor: { target: { text: "你查的內容" }, timeout: 120 } };

export const TAKES = [
  // ---------------------------------------------------------------- 1. home
  {
    name: "home",
    device: "desktop",
    aiCalls: 0,
    steps: [
      { goto: "/" },
      { wait: 1.2 },
      { mark: "hero" },
      { move: TAB_TEXT, ms: 800 },
      { move: TAB_URL, ms: 600 },
      { wait: 0.6 },
      { move: TAB_TEXT, ms: 600 },
      { wait: 0.5 },
      { mark: "tabs_shown" },
      { move: INPUT, ms: 700 },
      { wait: 0.8 },
      { mark: "counter" },
      { scroll: { text: "試試看" }, ms: 1200, offset: 220 },
      { wait: 1.0 },
      { move: { text: "網傳吃香蕉配優格會中毒" }, ms: 700 },
      { wait: 1.2 },
      { mark: "examples" },
      { scroll: { text: "Threads 查核機器人" }, ms: 1100, offset: 200 },
      { wait: 1.6 },
      { mark: "bot_card" },
      { scroll: { text: "隱私政策" }, ms: 1000, offset: 420 },
      { wait: 1.6 },
      { mark: "footer" },
    ],
  },

  // ------------------------------------------- 2. the core flow (1 AI call)
  {
    name: "text_flow",
    device: "desktop",
    aiCalls: 1,
    steps: [
      { goto: "/" },
      { wait: 1.0 },
      { scroll: { text: "試試看" }, ms: 900, offset: 240 },
      { wait: 0.5 },
      { click: { text: SCAM_EXAMPLE }, after: 900 },
      { mark: "example_filled" },
      { scroll: 0, ms: 700 },
      { wait: 1.0 },
      { mark: "input_filled" },
      { click: SUBMIT, after: 200 },
      { mark: "submitted" },
      { wait: 2.0 },
      { mark: "steps_visible" },
      RESULT_READY,
      { wait: 1.6 },
      { mark: "result_top" },
      { capture: { as: "result_url", js: "location.href" } },
      { capture: { as: "verdict", js: "window.__cap.text({sel:'main h1'})" } },
      { capture: { as: "chips", js: "[...document.querySelectorAll('main span,main div')].map(e=>e.textContent.trim()).filter(t=>/快取命中|AI 即時判定|信心 /.test(t)&&t.length<20).slice(0,4)" } },
      { capture: { as: "has_no_source_banner", js: "!!window.__cap.find({text:'尚無查核機構證實'})" } },
    ],
  },

  // ------------------------------------ 3. reading the result page top→bottom
  {
    name: "result_walk",
    device: "desktop",
    aiCalls: 0,
    needsResultFrom: "text_flow",
    steps: [
      { wait: 1.4 },
      { mark: "verdict_block" },
      { scroll: { text: "你查的內容" }, ms: 1100, offset: 150 },
      { wait: 1.4 },
      { mark: "input_excerpt" },
      { scroll: { text: "判讀摘要" }, ms: 900, offset: 150 },
      { wait: 1.8 },
      { mark: "summary" },
      { click: { text: "詳細說明" }, after: 900 },
      { wait: 1.6 },
      { mark: "explanation_open" },
      { scroll: { text: "查核來源" }, ms: 1000, offset: 150 },
      { wait: 2.0 },
      { mark: "sources" },
      { scroll: { text: "再查一則" }, ms: 900, offset: 260 },
      { wait: 1.0 },
      { move: { text: "分享到 Threads" }, ms: 700 },
      { wait: 0.8 },
      { mark: "share_hover" },
      { click: { text: "分享到 Threads" }, after: 1200 },
      { wait: 1.8 },
      { mark: "share_clicked" },
      { capture: { as: "threads_intent", js: "(window.__cap.blocked()[0]||{}).href || null" } },
      { click: { text: "複製連結" }, after: 900 },
      { wait: 1.8 },
      { mark: "copied_toast" },
      { move: { text: "再查一則" }, ms: 700 },
      { wait: 1.0 },
      { mark: "check_another" },
    ],
  },

  // --------------------------------------------- 4. URL tab + input validation
  {
    name: "url_check",
    device: "desktop",
    aiCalls: 1,
    steps: [
      { goto: "/" },
      { wait: 1.0 },
      { click: TAB_URL, after: 700 },
      { mark: "url_tab" },
      { wait: 0.8 },
      { paste: { target: URL_INPUT, text: BAD_URL }, after: 900 },
      { click: SUBMIT, after: 500 },
      { waitFor: { target: { text: "這不是有效的網址" }, timeout: 45 } },
      { wait: 2.6 },
      { mark: "invalid_url_error" },
      { capture: { as: "url_error", js: "window.__cap.text({text:'這不是有效的網址'})" } },
      { paste: { target: URL_INPUT, text: FACTCHECK_URL }, after: 1200 },
      { wait: 1.2 },
      { mark: "good_url" },
      { click: SUBMIT, after: 200 },
      { mark: "submitted" },
      { wait: 2.2 },
      RESULT_READY,
      { wait: 1.8 },
      { mark: "url_result" },
      { capture: { as: "result_url", js: "location.href" } },
      { capture: { as: "verdict", js: "window.__cap.text({sel:'main h1'})" } },
      { capture: { as: "chip", js: "window.__cap.text({text:'快取命中'})" } },
      // Stop at the summary: scene 2 already walked the whole output, and repeating the
      // empty-sources banner here would spend seconds the 5-minute budget does not have.
      { scroll: { text: "判讀摘要" }, ms: 1000, offset: 160 },
      { wait: 2.6 },
      { mark: "url_summary" },
    ],
  },

  // ------------------------------------------------ 5. L1 cache: same content
  {
    name: "cache_hash",
    device: "desktop",
    aiCalls: 0,
    steps: [
      { goto: "/" },
      { wait: 1.0 },
      { paste: { target: INPUT, text: SCAM_EXAMPLE }, after: 800 },
      { mark: "same_text" },
      { click: SUBMIT, after: 200 },
      { mark: "submitted" },
      RESULT_READY,
      { wait: 2.2 },
      { mark: "cache_chip" },
      { capture: { as: "chip", js: "window.__cap.text({text:'快取命中'})" } },
      { capture: { as: "result_url", js: "location.href" } },
      { click: { text: "快取命中" }, after: 900 },
      { wait: 1.8 },
      { mark: "cache_hint" },
    ],
  },

  // ------------------------------------------ 6. L2 cache: semantically close
  {
    name: "cache_vector",
    device: "desktop",
    aiCalls: 1, // charged as a miss; a hit costs nothing and the log records which happened
    steps: [
      { goto: "/" },
      { wait: 1.0 },
      { paste: { target: INPUT, text: VECTOR_REWRITE }, after: 900 },
      { mark: "reworded" },
      { click: SUBMIT, after: 200 },
      { mark: "submitted" },
      RESULT_READY,
      { wait: 2.2 },
      { mark: "vector_chip" },
      { capture: { as: "chip", js: "window.__cap.text({text:'快取命中'})" } },
      { capture: { as: "live_chip", js: "window.__cap.text({text:'AI 即時判定'})" } },
      { capture: { as: "result_url", js: "location.href" } },
      { scroll: { text: "查核來源" }, ms: 1000, offset: 150 },
      { wait: 2.0 },
      { mark: "vector_sources" },
    ],
  },

  // ------------------------------------------------------- 7. trending wall
  {
    name: "trending",
    device: "desktop",
    aiCalls: 0,
    steps: [
      { goto: "/" },
      { wait: 0.8 },
      { click: { sel: "header nav a[href='/trending']" }, after: 1400 },
      { wait: 1.4 },
      { mark: "trending_top" },
      { move: { text: "全部" }, ms: 700 },
      { wait: 0.6 },
      { click: { text: "未查證" }, after: 1200 },
      { wait: 1.6 },
      { mark: "filter_pending" },
      { click: { text: "全部" }, after: 1200 },
      { wait: 1.2 },
      { mark: "filter_all" },
      { scroll: 520, ms: 2000 },
      { wait: 1.6 },
      { mark: "scrolled" },
      { scroll: 1040, ms: 1800 },
      { wait: 1.6 },
      { mark: "scrolled2" },
    ],
  },

  // ------------------------------------------------------- 8. knowledge base
  {
    name: "knowledge",
    device: "desktop",
    aiCalls: 0,
    steps: [
      { goto: "/trending" },
      { wait: 0.8 },
      { click: { sel: "header nav a[href='/knowledge']" }, after: 1400 },
      { wait: 1.6 },
      { mark: "knowledge_top" },
      { type: { target: { placeholder: "搜尋關鍵字" }, text: "健保", cps: 4 } },
      { wait: 0.5 },
      { key: "Enter", after: 1600 },
      { wait: 2.0 },
      { mark: "search_results" },
      { capture: { as: "result_count", js: "document.querySelectorAll('main li').length" } },
      { scroll: 300, ms: 1400 },
      { wait: 1.8 },
      { mark: "cards" },
      { scroll: 0, ms: 900 },
      { click: { text: "詐騙" }, after: 1400 },
      { wait: 1.8 },
      { mark: "filter_scam" },
    ],
  },

  // -------------------------------------------------------- 9. dark / light
  {
    name: "theme",
    device: "desktop",
    aiCalls: 0,
    steps: [
      { goto: "/" },
      { wait: 1.2 },
      { mark: "light" },
      { click: { sel: "header button[aria-label]" }, after: 1400 },
      { wait: 2.0 },
      { mark: "dark" },
      { scroll: 260, ms: 1200 },
      { wait: 1.4 },
      { click: { sel: "header button[aria-label]" }, after: 1400 },
      { wait: 1.6 },
      { mark: "light_again" },
    ],
  },

  // ------------------------------------------------------------- 10. phone
  {
    name: "phone",
    device: "phone",
    aiCalls: 0,
    steps: [
      { goto: "/" },
      { wait: 1.6 },
      { mark: "phone_home" },
      { scroll: 260, ms: 1400 },
      { wait: 1.4 },
      { mark: "phone_scroll" },
      { scroll: 0, ms: 900 },
      { wait: 0.8 },
      { mark: "tabbar" },
    ],
  },

  // ---------------------------------------- 11. phone result page + footer pages
  {
    name: "phone_result",
    device: "phone",
    aiCalls: 0,
    needsResultFrom: "text_flow",
    steps: [
      { wait: 1.8 },
      { mark: "phone_result_top" },
      { scroll: 320, ms: 1600 },
      { wait: 1.6 },
      { mark: "phone_summary" },
      { scroll: 700, ms: 1600 },
      { wait: 1.8 },
      { mark: "phone_sources" },
    ],
  },
  {
    name: "policy",
    device: "desktop",
    aiCalls: 0,
    steps: [
      { goto: "/privacy.html" },
      { wait: 2.0 },
      { mark: "privacy" },
      { scroll: 240, ms: 1400 },
      { wait: 1.6 },
      { goto: "/data-deletion.html" },
      { wait: 2.2 },
      { mark: "deletion" },
    ],
  },
];
