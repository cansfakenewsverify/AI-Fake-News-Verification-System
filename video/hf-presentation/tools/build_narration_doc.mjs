// Writes presentations/2026-09_進度報告/06_簡報影片旁白稿.md from the real edit.
//
// Usage (from video/hf-presentation):  node tools/build_narration_doc.mjs
//
// Generated rather than typed, so the times in the document are the times in the film: a teammate
// re-recording the voice reads the same text against the same clock.
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const plan = JSON.parse(fs.readFileSync(path.join(ROOT, "data", "plan.json"), "utf8"));
const narr = JSON.parse(fs.readFileSync(path.join(ROOT, "data", "narration.json"), "utf8"));
const timing = JSON.parse(fs.readFileSync(path.join(ROOT, "data", "timing.json"), "utf8"));
const sched = JSON.parse(fs.readFileSync(path.join(ROOT, "data", "schedule.json"), "utf8"));

const mmss = (t) => {
  const m = Math.floor(t / 60);
  const s = t - m * 60;
  return `${m}:${s.toFixed(1).padStart(4, "0")}`;
};

const ON_SCREEN = {
  1: "可疑訊息卡（網址遮蔽）→ 標題卡：正式專題名稱、系統名稱、系所、組員、指導教授、網址",
  2: "正式站首頁實錄：文字／網址分頁、字數計數、範例、Threads 說明卡、頁尾",
  3: "點第一個範例 →「開始查證」→ 三步驟進度（等待段加速並標示）→ 結果頁出現",
  4: "結果頁由上往下：判定塊、信心與「AI 即時判定」、「尚無查核機構證實」橫幅、你查的內容、判讀摘要、詳細說明展開、查核來源、三個動作與提示",
  5: "網址分頁：先貼非網址文字被擋下（錯誤訊息），再貼真實查核報導網址 → 判讀摘要",
  6: "同一則訊息再查 →「快取命中・相同內容」；換句話說 →「快取命中・語意相似」",
  7: "熱門牆（來源、篩選、捲動）→ 知識庫搜尋「健保」→ 判定篩選",
  8: "深淺色切換 → 手機版底部分頁列 → 隱私政策與資料刪除說明",
  9: "Threads 貼文與提及 → 機器人回覆（實際輸出逐字）→ 手機結果頁 → 模擬模式說明",
  10: "架構圖：瀏覽器 → Vercel → Render（FastAPI）→ Supabase／長庚 CGU AIR；再切到三層判讀順序與護欄",
  11: "評測數字卡（96% → 100% count-up）、漏判為 0、自動化測試與測試計畫書、未通過的一項",
  12: "下一步兩張卡、網站與原始碼網址、謝謝各位老師、免責提醒",
};

const lines = [];
lines.push("# 簡報影片旁白稿（presentation_v1.0）");
lines.push("");
lines.push("> 這份是**機器產生**的：`video/hf-presentation/tools/build_narration_doc.mjs` 從實際的剪輯資料產生，");
lines.push("> 所以時間碼就是成片的時間碼。要改旁白請改 `video/hf-presentation/data/narration.json`，");
lines.push("> 再跑 `npm run tts`、`npm run timeline`，這份文件重跑本指令就會更新。");
lines.push("");
lines.push("| 項目 | 內容 |");
lines.push("|------|------|");
lines.push(`| 成品 | \`docs/demo/presentation_v1.0.mp4\`（1920×1080、30 fps）＋ \`docs/demo/presentation_v1.0.srt\` |`);
lines.push(`| 全長 | ${sched.total} 秒（${mmss(sched.total)}），上限 5 分鐘 |`);
lines.push(`| 配音 | edge-tts \`${narr.voice}\`、語速 ${narr.rate}；共 ${Object.keys(timing).length} 段，${sched.cues.length} 句字幕 |`);
lines.push("| 要換成真人聲音 | 照下表逐段錄，每段從「段落起點」開始講，講完不要超過「段落結束」前 0.3 秒即可；畫面不必重做 |");
lines.push("");
lines.push("## 逐段旁白");
lines.push("");

for (const shot of narr.shots) {
  const n = shot.shot;
  const s = sched.shots[String(n)];
  const t = timing[String(n)];
  const end = s.start + s.dur;
  lines.push(`### 鏡 ${n}　${mmss(s.start)} – ${mmss(end)}（${s.dur} 秒）`);
  lines.push("");
  lines.push(`**畫面**：${ON_SCREEN[n]}`);
  lines.push("");
  lines.push(`**旁白起點**：${mmss(s.audioStart)}　**語音長度**：${t.speech_end.toFixed(2)} 秒　**餘裕**：${(s.dur - plan.shots[String(n)].audio - t.speech_end).toFixed(2)} 秒`);
  lines.push("");
  for (const c of t.cues) {
    lines.push(`- \`${mmss(s.audioStart + c.start)}\`　${c.text}`);
  }
  const tts = shot.tts;
  if (tts && tts.some((x, i) => x !== shot.cues[i])) {
    lines.push("");
    lines.push("<details><summary>送給語音合成的讀音版本（字幕不受影響）</summary>");
    lines.push("");
    for (let i = 0; i < tts.length; i++) {
      if (tts[i] !== shot.cues[i]) lines.push(`- ${tts[i]}`);
    }
    lines.push("");
    lines.push("</details>");
  }
  lines.push("");
}

lines.push("## 念法備忘");
lines.push("");
lines.push("- 「重」當「再一次」解時，這個聲音會念成 zhòng，所以旁白一律避開，改寫成「再跑一次」「換上新模型之後」之類的說法。");
lines.push("- 英文一律照單字念：Threads、Vercel、Render、Supabase、GitHub、MyGoPen、Cofacts、FastAPI、Postgres、Meta。");
lines.push("- 逐字母念的：CGU（C G U）、API、IP、AI、HTTP、HTTPS、PG vector。");
lines.push("- 數字一律寫成國字送合成：一百五十、百分之九十六、七百、三百八十五、四十六、三十、二十七、零點七五、三百。");
lines.push("- 「P0」念成「P 零」。「長庚」這個聲音念得正確，不需要改寫。");
lines.push("");

const out = path.resolve(ROOT, "..", "..", "presentations", "2026-09_進度報告", "06_簡報影片旁白稿.md");
fs.mkdirSync(path.dirname(out), { recursive: true });
fs.writeFileSync(out, lines.join("\n"), "utf8");
console.log(`wrote ${path.relative(path.resolve(ROOT, "..", ".."), out)} (${lines.length} lines)`);
