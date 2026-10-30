// Writes the voice-over script the narrator reads from: every storyboard line with a "rec" (V1 …), grouped by
// recording, numbered in film order. build.mjs cuts each recording at the pauses between sentences and gives
// the pieces to these lines in the same order, so the sheet and the storyboard must never disagree.
//
// Usage (from video/hf-scenario):  node tools/rec_sheet.mjs
// Writes: presentations/2026-11_第二次簡報/04_配音稿.md
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const OUT = path.resolve(ROOT, "..", "..", "presentations", "2026-11_第二次簡報", "04_配音稿.md");
const board = JSON.parse(fs.readFileSync(path.join(ROOT, "data", "storyboard.json"), "utf8"));
const voiceLen = JSON.parse(fs.readFileSync(path.join(ROOT, "data", "lines.json"), "utf8"));

const TITLE = { V1: "開場＋情境一（家族群組的停水謠言）", V2: "情境二（解除分期詐騙簡訊）", V3: "情境三（Threads 上吵成一團）", V4: "查不到的時候＋結尾" };
const PAUSE = 2;

const recs = {};
for (const s of board.shots) {
  (s.lines ?? []).forEach((l, n) => {
    if (!l.rec) return;
    const text = Array.isArray(l.text) ? l.text.join("") : l.text;
    (recs[l.rec] ??= []).push({ text, secs: voiceLen[`${s.id}_${n}`]?.dur ?? text.length / 4.5 });
  });
}

const minutes = (lines) => Math.max(1, Math.round((lines.reduce((t, l) => t + l.secs * 1.15 + PAUSE, 0)) / 60));
const out = [
  "# 情境劇配音稿（旁白：廖晢勛）",
  "",
  "> 由 `video/hf-scenario/tools/rec_sheet.mjs` 從分鏡 `data/storyboard.json` 產生，不要手改；台詞要改就改分鏡再重跑。",
  "> 2026-10-30 起情境劇不拍組員畫面：旁白全部是負責人的聲音，阿嬤、爸爸、網友的台詞用 AI 語音。",
  "",
  `錄 ${Object.keys(recs).length} 個檔，每個 ${Math.min(...Object.values(recs).map(minutes))}～${Math.max(...Object.values(recs).map(minutes))} 分鐘；連重錄大約 20 分鐘。`,
  "",
  "## 怎麼錄",
  "",
  "1. 用手機的錄音 App（iPhone「語音備忘錄」、Android「錄音機」）。安靜的房間，關掉電扇與冷氣，手機離嘴巴約 20 公分。",
  `2. 每個檔從第 1 句念到最後一句，**每句念完停 ${PAUSE} 秒**再念下一句。程式靠這個停頓把句子切開、對到畫面。`,
  "3. 念錯了就整個檔重錄（每個檔只有 1～2 分鐘）。不要在中間重念同一句，會多出一句、對不上畫面。",
  "4. 同一句裡面可以正常換氣。語氣像在跟朋友解釋，不用趕。",
  "5. 檔名改成 `V1`、`V2`、`V3`、`V4`（副檔名照手機給的，例如 `V1.m4a`），放進 `video/hf-scenario/raw/`，然後跟 Claude 說「錄好了」。",
  "",
];
for (const [rec, lines] of Object.entries(recs)) {
  out.push(`## ${rec}：${TITLE[rec] ?? ""}（${lines.length} 句，約 ${minutes(lines)} 分鐘）`, "");
  lines.forEach((l, i) => out.push(`${i + 1}. ${l.text}`));
  out.push("");
}
fs.writeFileSync(OUT, out.join("\n"), "utf8");
console.log(`${path.relative(process.cwd(), OUT)}: ${Object.entries(recs).map(([r, l]) => `${r} ${l.length}`).join(", ")}`);
