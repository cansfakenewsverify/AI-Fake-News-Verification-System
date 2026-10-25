// What to record on the live site for the scenario drama (phone width, light theme).
//
// The three messages are the ones in presentations/2026-11_第二次簡報/01_情境劇劇本.md, word for word.
// All three were checked on the live site on 2026-10-26 and answer from the cache (hash layer), so the
// takes spend no AI call and the results on screen are the same ones the actors' phones will show.
export const SITE = "https://fakenewsverify.vercel.app";

export const MSG_MISINFO = "雲林縣從四月六日開始，晚上十點至清晨六點停水，所以晚上早點洗澡，洗衣，儲水備用，早上停水的時間較短，對大家比較不影響。";
export const MSG_SCAM = "您的網購刷卡分期設定錯誤將連續扣款12期，請立即聯繫客服人員協助解除";
export const MSG_UNVERIFIABLE = "台中市政府交通局宣布，下個月起市區公車將新增三條夜間路線，行駛到凌晨一點，詳細時刻表將公布在交通局官網。";

const INPUT = { sel: "textarea[aria-label]" };
const SUBMIT = { text: "開始查證" };
const RESULT_READY = { waitFor: { target: { text: "你查的內容" }, timeout: 120 } };

/** home → paste → submit → result top; the reading part differs per message. */
const check = (name, text, reading) => ({
  name,
  device: "phone",
  aiCalls: 0,
  steps: [
    { goto: "/" },
    { wait: 1.4 },
    { mark: "home" },
    { paste: { target: INPUT, text }, after: 900 },
    { mark: "pasted" },
    { click: SUBMIT, after: 200 },
    { mark: "submitted" },
    RESULT_READY,
    { wait: 1.4 },
    { mark: "result_top" },
    { capture: { as: "result_url", js: "location.href" } },
    { capture: { as: "verdict", js: "window.__cap.text({sel:'main h1'})" } },
    { capture: { as: "chip", js: "[...document.querySelectorAll('main span,main div')].map(e=>e.textContent.trim()).filter(t=>/快取命中|AI 即時判定/.test(t)&&t.length<20)[0]||null" } },
    ...reading,
  ],
});

export const TAKES = [
  check("site_misinfo", MSG_MISINFO, [
    { scroll: { text: "查核來源" }, ms: 1500, offset: 200 },
    { wait: 2.4 },
    { mark: "sources" },
  ]),
  check("site_scam", MSG_SCAM, [
    { scroll: { text: "判讀摘要" }, ms: 1100, offset: 160 },
    { wait: 1.4 },
    { mark: "summary" },
    { click: { text: "詳細說明" }, after: 900 },
    { wait: 1.2 },
    { mark: "explanation_open" },
    { scroll: { text: "查核來源" }, ms: 1400, offset: 200 },
    { wait: 2.2 },
    { mark: "sources" },
  ]),
  check("site_unverifiable", MSG_UNVERIFIABLE, [
    { wait: 1.2 },
    { scroll: { text: "判讀摘要" }, ms: 1200, offset: 200 },
    { wait: 2.4 },
    { mark: "summary" },
  ]),
];
