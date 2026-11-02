// What to record on the live site for the scenario drama (phone width, light theme).
//
// The messages are the ones in presentations/2026-11_第二次簡報/01_真人劇本.md, word for word.
// build.mjs cuts every take into the tutorial's steps at the marks below (home, pasted, submitted, ...).
// site_egg (情境一, 2026-11-02) needs the school's AI gateway the first time it is checked (one AI call, about
// USD 0.0014); after that it answers from the cache. site_unverifiable was checked on 2026-10-26 and has
// answered from the cache (hash layer) ever since, so it can be recorded even while the gateway is down.
//
// 2026-11-03: the school closed embedding, so a paraphrase cannot reach the fact-check. When raw/site_egg_text.txt
// exists (not in git) site_egg pastes it instead: the fact-check center's rumour text exactly as the knowledge base
// stores it, which hits the hash layer with no AI call and no embedding.
import fs from "node:fs";
import { fileURLToPath } from "node:url";

export const SITE = "https://fakenewsverify.vercel.app";

const EGG_TEXT_FILE = fileURLToPath(new URL("../raw/site_egg_text.txt", import.meta.url));
export const MSG_EGG = fs.existsSync(EGG_TEXT_FILE)
  ? fs.readFileSync(EGG_TEXT_FILE, "utf8")
  : "你媽從小教你冷水煮蛋？一顆雞蛋就這樣煮成垃圾！冷水下鍋，蛋黃表面會出現一層灰綠色的硫化亞鐵，雞蛋的營養直接流失40%，以後一定要等水滾再放蛋。";
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
  { ...check("site_egg", MSG_EGG, [
    { wait: 1.4 },
    { mark: "scroll_summary" },
    { scroll: { text: "判讀摘要" }, ms: 1200, offset: 160 },
    { wait: 2.2 },
    { mark: "summary" },
    { wait: 0.8 },
    { mark: "scroll_sources" },
    { scroll: { text: "查核來源" }, ms: 1500, offset: 200 },
    { wait: 2.6 },
    { mark: "sources" },
    // Headless Edge has no clipboard to write to, so the page would fall back to printing the URL.
    // Stand in for the OS clipboard (the page and its data are untouched) so the button shows 已複製.
    { js: "navigator.clipboard.writeText = () => Promise.resolve()" },
    { mark: "to_copy" },
    { click: { text: "複製連結" }, after: 200 },
    { mark: "copied" },
    { wait: 1.8 },
    { mark: "copied_end" },
  ]), aiCalls: 1 },
  check("site_unverifiable", MSG_UNVERIFIABLE, [
    { wait: 1.2 },
    { mark: "scroll_summary" },
    { scroll: { text: "判讀摘要" }, ms: 1200, offset: 200 },
    { wait: 2.4 },
    { mark: "summary" },
  ]),
];
