// Builds the written report as a PowerPoint deck (this course submits the written report as a
// printed deck — see presentations/軟硬體專題第二次報告.pptx for the previous one).
//
// Usage:
//   npm install --prefix %TEMP%\fnv-pptx pptxgenjs
//   node presentations/tools/build_report_pptx.mjs
//
// Content comes from presentations/2026-09_進度報告/10_書面報告_草稿.html — edit the HTML first,
// then mirror the change here, so the printed PDF and the deck say the same thing.
//
// Visual language matches the site and the presentation film on purpose: white page, ink #111111,
// and red / yellow / green used ONLY for verdicts, never as decoration.
import { createRequire } from "node:module";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const require = createRequire(path.join(os.tmpdir(), "fnv-pptx", "noop.js"));
const PptxGenJS = require("pptxgenjs");

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const OUT = path.join(REPO, "presentations", "2026-09_進度報告", "10_書面報告.pptx");

const INK = "111111";
const MUTED = "5B5B66";
const LINE = "D4D4D8";
const PAPER = "FFFFFF";
const SOFT = "F4F4F6";
const RED = "C02626";
const AMBER = "9A6400";

const SANS = "Microsoft JhengHei";
const W = 13.333;
const M = 0.62;            // page margin
const CW = W - M * 2;      // content width

const pres = new PptxGenJS();
pres.layout = "LAYOUT_WIDE";
pres.author = "廖晢勛、石岱勳、姚睿、張宇宏、廖育翔";
pres.title = "AI 為核心的假訊息驗證系統 — 第三次進度報告";

let pageNo = 0;
const TOTAL = 12;

/** Every content page: title at the top, page number bottom-right, nothing decorative. */
function page(title, kicker) {
  pageNo += 1;
  const s = pres.addSlide();
  s.background = { color: PAPER };
  s.addText(title, {
    x: M, y: 0.44, w: CW - 2.2, h: 0.72, isTextBox: true, margin: 0,
    fontFace: SANS, fontSize: 30, bold: true, color: INK, valign: "middle",
  });
  if (kicker) {
    s.addText(kicker, {
      x: M, y: 1.16, w: CW - 2.2, h: 0.36, isTextBox: true, margin: 0,
      fontFace: SANS, fontSize: 13, color: MUTED, valign: "middle",
    });
  }
  s.addText(`${pageNo} / ${TOTAL}`, {
    x: W - M - 1.6, y: 6.72, w: 1.6, h: 0.32, isTextBox: true, margin: 0,
    fontFace: SANS, fontSize: 11, color: MUTED, align: "right", valign: "middle",
  });
  s.addText("全民查證公社　·　第三次進度報告　2026-09", {
    x: M, y: 6.72, w: 7.2, h: 0.32, isTextBox: true, margin: 0,
    fontFace: SANS, fontSize: 11, color: MUTED, valign: "middle",
  });
  return s;
}

/** A plain bordered card. No edge stripes, no fills except a very light tint when asked. */
function card(s, { x, y, w, h, tint = false }) {
  s.addShape(pres.ShapeType.roundRect, {
    x, y, w, h, rectRadius: 0.06,
    fill: { color: tint ? SOFT : PAPER },
    line: { color: LINE, width: 1 },
  });
}

/* ───────────────────────────── 1. 封面 ───────────────────────────── */
{
  const s = pres.addSlide();
  s.background = { color: INK };
  s.addText("長庚大學　資訊工程學系　軟硬體專題", {
    x: M + 0.5, y: 0.95, w: CW - 1, h: 0.4, isTextBox: true, margin: 0,
    fontFace: SANS, fontSize: 15, color: "B9B9C2", charSpacing: 2,
  });
  s.addText("AI 為核心的\n假訊息驗證系統", {
    x: M + 0.5, y: 1.5, w: CW - 1, h: 1.85, isTextBox: true, margin: 0,
    fontFace: SANS, fontSize: 48, bold: true, color: PAPER, lineSpacingMultiple: 1.12,
  });
  s.addText("系統名稱：全民查證公社", {
    x: M + 0.5, y: 3.42, w: CW - 1, h: 0.44, isTextBox: true, margin: 0,
    fontFace: SANS, fontSize: 20, color: "D6D6DB",
  });

  const rows = [
    ["報告別", "第三次進度報告　·　2026 年 9 月"],
    ["團隊成員", "廖晢勛、石岱勳、姚睿、張宇宏、廖育翔"],
    ["指導教授", "黃崇源"],
    ["系統網址", "https://fakenewsverify.vercel.app"],
    ["原始碼", "github.com/cansfakenewsverify/AI-Fake-News-Verification-System"],
  ];
  rows.forEach(([k, v], i) => {
    const y = 4.18 + i * 0.44;
    s.addText(k, {
      x: M + 0.5, y, w: 1.5, h: 0.4, isTextBox: true, margin: 0,
      fontFace: SANS, fontSize: 13, bold: true, color: "B9B9C2", valign: "middle",
    });
    s.addText(v, {
      x: M + 2.1, y, w: 7.6, h: 0.4, isTextBox: true, margin: 0,
      fontFace: SANS, fontSize: 13, color: PAPER, valign: "middle",
    });
  });

  s.addShape(pres.ShapeType.roundRect, {
    x: W - M - 3.9, y: 4.1, w: 3.4, h: 2.0, rectRadius: 0.06,
    fill: { color: INK }, line: { color: "6A6A76", width: 1 },
  });
  s.addText("指導教授簽名", {
    x: W - M - 3.65, y: 4.32, w: 2.9, h: 0.34, isTextBox: true, margin: 0,
    fontFace: SANS, fontSize: 13, bold: true, color: "D6D6DB",
  });
  s.addText("簽名：", {
    x: W - M - 3.65, y: 5.02, w: 0.8, h: 0.3, isTextBox: true, margin: 0,
    fontFace: SANS, fontSize: 12, color: "D6D6DB",
  });
  s.addShape(pres.ShapeType.line, { x: W - M - 2.85, y: 5.32, w: 2.1, h: 0, line: { color: "D6D6DB", width: 1 } });
  s.addText("日期：", {
    x: W - M - 3.65, y: 5.52, w: 0.8, h: 0.3, isTextBox: true, margin: 0,
    fontFace: SANS, fontSize: 12, color: "D6D6DB",
  });
  s.addShape(pres.ShapeType.line, { x: W - M - 2.85, y: 5.82, w: 2.1, h: 0, line: { color: "D6D6DB", width: 1 } });
  pageNo += 1;
  s.addText(`${pageNo} / ${TOTAL}`, {
    x: W - M - 1.6, y: 6.72, w: 1.6, h: 0.32, isTextBox: true, margin: 0,
    fontFace: SANS, fontSize: 11, color: "9A9AA6", align: "right", valign: "middle",
  });
  s.addNotes("封面。列印後請黃崇源老師在右下角簽名欄簽名。");
}

/* ────────────────────── 2. 這一期做了什麼 ────────────────────── */
{
  const s = page("這一期做了什麼", "上次報告時系統只能在組員電腦上跑；現在任何人都能直接打開網址使用。");
  const items = [
    ["上雲", "前端 Vercel、後端 Render、資料改存 Supabase PostgreSQL（含 pgvector）。2026-09-19 起上線運作。"],
    ["介面重做", "依規格書 v1.3 與設計稿重寫前端，統一文案與紅黃綠燈的使用規則。"],
    ["來源紀律", "只採計已做出判定的查核來源；找不到就標示「尚無查核機構證實」，而且不給綠燈。"],
    ["上線護欄", "每日 AI 呼叫上限、每個 IP 的頻率限制、請求與上傳大小上限。"],
    ["測試計畫書", "依課程格式完成 TP-FNV-2026-01（5 類 46 項），執行兩輪並記錄未結缺陷。"],
    ["簡報影片", "依老師 9/20 的規定錄製 4 分 38 秒預錄影片，畫面全部是正式站實錄。"],
  ];
  const colW = (CW - 0.4) / 2;
  items.forEach(([h, b], i) => {
    const x = M + (i % 2) * (colW + 0.4);
    const y = 1.78 + Math.floor(i / 2) * 1.62;
    card(s, { x, y, w: colW, h: 1.4 });
    s.addText(`${String(i + 1).padStart(2, "0")}　${h}`, {
      x: x + 0.26, y: y + 0.16, w: colW - 0.52, h: 0.4, isTextBox: true, margin: 0,
      fontFace: SANS, fontSize: 17, bold: true, color: INK, valign: "middle",
    });
    s.addText(b, {
      x: x + 0.26, y: y + 0.58, w: colW - 0.52, h: 0.7, isTextBox: true, margin: 0,
      fontFace: SANS, fontSize: 12, color: "3F3F46", lineSpacingMultiple: 1.25, valign: "top",
    });
  });
}

/* ──────────────────────── 3. 系統在做什麼 ──────────────────────── */
{
  const s = page("系統在做什麼", "貼上收到的可疑訊息（文字或網址），拿到判定與已做出判定的查核來源。");
  const blocks = [
    ["單筆查證", "判定為詐騙、假訊息或查無異常，以紅黃綠燈呈現；判不出來標「無法查證」。每一筆結果都有自己的網址，可複製連結或分享到 Threads。"],
    ["熱門牆", "彙整 MyGoPen、台灣事實查核中心與 Cofacts 的查核結果，可切換「全部」與「未查證」。"],
    ["知識庫", "查證過而且有來源佐證的內容都留在這裡，可以搜尋關鍵字，也可依判定篩選。"],
    ["Threads 查核機器人", "在可疑貼文底下標記機器人，它會回覆判定、來源與結果頁連結。目前以模擬模式展示，尚未對外開放。"],
  ];
  const colW = (CW - 0.36 * 3) / 4;
  blocks.forEach(([h, b], i) => {
    const x = M + i * (colW + 0.36);
    card(s, { x, y: 1.92, w: colW, h: 3.9, tint: i === 3 });
    s.addText(h, {
      x: x + 0.24, y: 2.14, w: colW - 0.48, h: 0.78, isTextBox: true, margin: 0,
      fontFace: SANS, fontSize: 18, bold: true, color: INK, valign: "top",
    });
    s.addText(b, {
      x: x + 0.24, y: 2.98, w: colW - 0.48, h: 2.6, isTextBox: true, margin: 0,
      fontFace: SANS, fontSize: 12.5, color: "3F3F46", lineSpacingMultiple: 1.35, valign: "top",
    });
  });
  s.addText("不需要註冊，不需要登入；查詢紀錄只留在使用者自己的瀏覽器，不上傳。", {
    x: M, y: 6.06, w: CW, h: 0.4, isTextBox: true, margin: 0,
    fontFace: SANS, fontSize: 13, color: MUTED, valign: "middle",
  });
}


/* ───────────────────────── 4. 關鍵技術 ───────────────────────── */
{
  const s = page("關鍵技術", "四項技術決定了這套系統能不能便宜、穩定而且誠實地回答問題。");
  const items = [
    ["向量語意檢索", "以 text-embedding-3-small 將訊息轉成 1536 維向量，存入 PostgreSQL 的 pgvector 並以 cosine 相似度比對。門檻 0.75 是用實測資料校準出來的：同一謠言的改寫版落在 0.79–0.82，不同謠言不超過 0.68。"],
    ["三層快取", "相同內容、語意相似、AI 判讀依序嘗試，把最貴的一步留到最後。雜湊命中 213 ms、向量命中約 3 秒、AI 判讀 9–27 秒；命中快取不耗用 AI 額度。"],
    ["來源分級", "把查核來源分成三級，只有已經做出判定的機構或媒體查核報導能顯示為來源。找不到就標示「尚無查核機構證實」，而且不給綠燈——寧可說還沒被證實，也不給一個看起來有來源的答案。"],
    ["雲端部署與護欄", "Vercel 靜態前端同源代理到 Render 的 FastAPI 後端，資料在 Supabase。對外連線一律經 SSRF 防護，另有每日 AI 次數上限、每個 IP 的頻率限制與請求大小上限。"],
  ];
  const colW = (CW - 0.4) / 2;
  items.forEach(([h, b], i) => {
    const x = M + (i % 2) * (colW + 0.4);
    const y = 1.86 + Math.floor(i / 2) * 2.34;
    card(s, { x, y, w: colW, h: 2.12, tint: i === 0 });
    s.addText(h, {
      x: x + 0.28, y: y + 0.2, w: colW - 0.56, h: 0.44, isTextBox: true, margin: 0,
      fontFace: SANS, fontSize: 20, bold: true, color: INK, valign: "middle",
    });
    s.addText(b, {
      x: x + 0.28, y: y + 0.68, w: colW - 0.56, h: 1.3, isTextBox: true, margin: 0,
      fontFace: SANS, fontSize: 12, color: "3F3F46", lineSpacingMultiple: 1.3, valign: "top",
    });
  });
}

/* ────────────────────────── 5. 系統架構 ────────────────────────── */
{
  const s = page("系統架構", "金鑰只存在負責人本機的設定檔與 Render 後台；版本庫是公開的，裡面不含任何金鑰。");
  const boxes = [
    ["USER", "瀏覽器", "手機或電腦，不用登入", 1.85],
    ["VERCEL", "前端", "React 靜態檔・/api 同源代理", 1.85],
    ["RENDER", "後端 FastAPI", "判讀流程都在這裡", 2.05],
  ];
  let x = M + 0.15;
  boxes.forEach(([k, t, b, w], i) => {
    card(s, { x, y: 2.2, w, h: 1.5, tint: i === 2 });
    s.addText(k, {
      x: x + 0.2, y: 2.36, w: w - 0.4, h: 0.28, isTextBox: true, margin: 0,
      fontFace: SANS, fontSize: 10.5, bold: true, color: MUTED, charSpacing: 1.6,
    });
    s.addText(t, {
      x: x + 0.2, y: 2.64, w: w - 0.4, h: 0.44, isTextBox: true, margin: 0,
      fontFace: SANS, fontSize: 19, bold: true, color: INK,
    });
    s.addText(b, {
      x: x + 0.2, y: 3.1, w: w - 0.4, h: 0.5, isTextBox: true, margin: 0,
      fontFace: SANS, fontSize: 11, color: "3F3F46", lineSpacingMultiple: 1.2,
    });
    if (i < 2) {
      s.addShape(pres.ShapeType.line, {
        x: x + w + 0.08, y: 2.95, w: 0.5, h: 0,
        line: { color: INK, width: 2, endArrowType: "triangle" },
      });
    }
    x += w + 0.66;
  });

  const data = [
    ["SUPABASE", "資料庫", "PostgreSQL ＋ pgvector：知識庫、結果、熱門、用量"],
    ["長庚 CGU AIR", "AI 閘道", "判讀模型 gpt-5.4-mini；向量模型 text-embedding-3-small"],
  ];
  const dw = 3.2;
  data.forEach(([k, t, b], i) => {
    const dx = M + 0.15 + i * (dw + 0.66);
    card(s, { x: dx, y: 4.34, w: dw, h: 1.62 });
    s.addText(k, {
      x: dx + 0.2, y: 4.5, w: dw - 0.4, h: 0.28, isTextBox: true, margin: 0,
      fontFace: SANS, fontSize: 10.5, bold: true, color: MUTED, charSpacing: 1.6,
    });
    s.addText(t, {
      x: dx + 0.2, y: 4.78, w: dw - 0.4, h: 0.44, isTextBox: true, margin: 0,
      fontFace: SANS, fontSize: 19, bold: true, color: INK,
    });
    s.addText(b, {
      x: dx + 0.2, y: 5.24, w: dw - 0.4, h: 0.62, isTextBox: true, margin: 0,
      fontFace: SANS, fontSize: 11, color: "3F3F46", lineSpacingMultiple: 1.2,
    });
    s.addShape(pres.ShapeType.line, {
      x: dx + dw / 2, y: 3.78, w: 0, h: 0.5,
      line: { color: INK, width: 2, endArrowType: "triangle" },
    });
  });
}

/* ─────────────────── 5. 判讀流程：三層快取 ─────────────────── */
{
  const s = page("判讀流程：先找答案，找不到才問 AI", "呼叫大型語言模型是最貴的一步，所以只有前兩層都沒有命中時才真的呼叫。");
  const rows = [
    ["L1", "相同內容", "內容雜湊比對，完全一樣就直接沿用先前的判定", "213 ms"],
    ["L2", "語意相似", "向量比對，門檻 0.75，而且只比對已經證實的資料列", "約 3.1 秒"],
    ["L3", "AI 判讀", "前兩層都沒有命中才呼叫一次模型；判讀對象一律是使用者原文", "9–27 秒"],
  ];
  rows.forEach(([n, h, b, t], i) => {
    const y = 1.94 + i * 1.12;
    card(s, { x: M, y, w: CW - 3.5, h: 0.98, tint: i === 2 });
    s.addText(n, {
      x: M + 0.28, y: y + 0.24, w: 0.8, h: 0.5, isTextBox: true, margin: 0,
      fontFace: SANS, fontSize: 19, bold: true, color: MUTED, valign: "middle",
    });
    s.addText(h, {
      x: M + 1.1, y: y + 0.13, w: 2.3, h: 0.42, isTextBox: true, margin: 0,
      fontFace: SANS, fontSize: 18, bold: true, color: INK, valign: "middle",
    });
    s.addText(b, {
      x: M + 1.1, y: y + 0.52, w: CW - 4.9, h: 0.36, isTextBox: true, margin: 0,
      fontFace: SANS, fontSize: 12, color: "3F3F46", valign: "middle",
    });
    s.addText(t, {
      x: W - M - 3.4, y, w: 1.5, h: 0.98, isTextBox: true, margin: 0,
      fontFace: SANS, fontSize: 15, bold: true, color: INK, align: "right", valign: "middle",
    });
    s.addText("實測延遲", {
      x: W - M - 3.4, y: y + 0.55, w: 1.5, h: 0.3, isTextBox: true, margin: 0,
      fontFace: SANS, fontSize: 10, color: MUTED, align: "right", valign: "middle",
    });
  });

  card(s, { x: W - M - 1.78, y: 1.94, w: 1.78, h: 3.3, tint: true });
  s.addText("門檻 0.75", {
    x: W - M - 1.58, y: 2.14, w: 1.4, h: 0.36, isTextBox: true, margin: 0,
    fontFace: SANS, fontSize: 15, bold: true, color: INK,
  });
  s.addText("實測校準：\n\n同一謠言的改寫版\n0.79–0.82\n\n不同謠言\n≤ 0.68\n\n先前的 0.88 會把改寫版全部擋掉，等於讓向量層失去作用。", {
    x: W - M - 1.58, y: 2.52, w: 1.4, h: 2.6, isTextBox: true, margin: 0,
    fontFace: SANS, fontSize: 10.5, color: "3F3F46", lineSpacingMultiple: 1.18, valign: "top",
  });

  s.addText("上線護欄：每日 AI 呼叫 300 次／日　·　每個 IP 30 次／分、200 次／時　·　請求 1 MB、圖片 10 MB", {
    x: M, y: 5.62, w: CW, h: 0.42, isTextBox: true, margin: 0,
    fontFace: SANS, fontSize: 13, color: INK, valign: "middle",
  });
  s.addText("達到每日上限後仍可回覆命中快取的內容；快取命中不呼叫 AI、不佔用額度。", {
    x: M, y: 6.0, w: CW, h: 0.38, isTextBox: true, margin: 0,
    fontFace: SANS, fontSize: 11.5, color: MUTED, valign: "middle",
  });
}


/* ──────────────────────── 7. 實際困難點 ──────────────────────── */
{
  const s = page("實際困難點", "以下四項是開發過程中真正卡住、而且改了設計才解決的問題。");
  const rows = [
    ["向量層形同虛設", "相似度門檻原本設 0.88。實測發現同一謠言的改寫版只有 0.79–0.82，全部被擋在門外，語意快取等於沒有作用。",
      "改以實測資料校準門檻為 0.75，並確認不同謠言之間不超過 0.68，不會誤命中。改寫版開始正常命中。"],
    ["分析對象被偷換", "使用者貼文字時，系統原本會先去爬網頁，再拿爬到的全文與知識庫比對。長篇網頁對上一句話的謠言，相似度永遠過不了門檻。",
      "改為文字輸入一律以使用者原文送 AI 與向量比對，爬到的頁面降級為參考資料，並補上回歸測試防止改回去。"],
    ["同一則謠言出現兩種標籤", "查核報導被當成謠言本身判定：同一則 SIM 卡謠言，一家媒體的查核報導被標成假訊息，另一家被標成安全。",
      "判定對象改為「被查核的主張」而非報導本身，並以標題判定詞、AI 指示與既有資料修復三道防線處理。"],
    ["免費雲端主機會休眠", "後端閒置 15 分鐘即休眠，喚醒約需 1 分鐘，但結果頁 15 秒逾時就顯示「連不上伺服器」，使用者以為壞掉。",
      "結果頁改為在 90 秒內持續重試並維持載入畫面，後端恢復後自動重新載入；送出查證的逾時延長至 75 秒。"],
  ];
  rows.forEach(([title, problem, fix], i) => {
    const y = 1.84 + i * 1.19;
    card(s, { x: M, y, w: CW, h: 1.05 });
    s.addText(title, {
      x: M + 0.26, y: y + 0.14, w: 2.5, h: 0.78, isTextBox: true, margin: 0,
      fontFace: SANS, fontSize: 16, bold: true, color: INK, valign: "top",
    });
    s.addText([{ text: "問題　", options: { bold: true, color: MUTED } }, { text: problem }], {
      x: M + 2.86, y: y + 0.13, w: 4.4, h: 0.82, isTextBox: true, margin: 0,
      fontFace: SANS, fontSize: 10.5, color: "3F3F46", lineSpacingMultiple: 1.22, valign: "top",
    });
    s.addText([{ text: "解法　", options: { bold: true, color: MUTED } }, { text: fix }], {
      x: M + 7.46, y: y + 0.13, w: CW - 7.72, h: 0.82, isTextBox: true, margin: 0,
      fontFace: SANS, fontSize: 10.5, color: "3F3F46", lineSpacingMultiple: 1.22, valign: "top",
    });
  });
  s.addText("每一項都留下缺陷編號與回歸測試，修正內容可在測試計畫書與版本庫中回溯。", {
    x: M, y: 6.62, w: CW, h: 0.34, isTextBox: true, margin: 0,
    fontFace: SANS, fontSize: 11.5, color: MUTED, valign: "middle",
  });
}

/* ────────────────────────── 8. 評測結果 ────────────────────────── */
{
  const s = page("評測結果", "自建 150 筆已標註的訊息（詐騙、假訊息、安全各 50），其中刻意放入「看起來像詐騙的合法官方訊息」當難題。");
  const cards = [
    ["前一版　2026-06", "gpt-5-mini", "96.0", "%", "macro-F1 0.960　·　漏判 0　·　誤報 5", false],
    ["現行　2026-09-16", "gpt-5.4-mini", "100", "%", "macro-F1 1.000　·　漏判 0　·　誤報 0", true],
  ];
  cards.forEach(([k, model, num, unit, sub, dark], i) => {
    const x = M + i * 3.6;
    const s0 = { x, y: 1.96, w: 3.2, h: 2.5 };
    s.addShape(pres.ShapeType.roundRect, {
      ...s0, rectRadius: 0.06,
      fill: { color: dark ? INK : PAPER }, line: { color: dark ? INK : LINE, width: 1 },
    });
    s.addText(k, {
      x: x + 0.26, y: 2.14, w: 2.7, h: 0.3, isTextBox: true, margin: 0,
      fontFace: SANS, fontSize: 11, bold: true, color: dark ? "B9B9C2" : MUTED,
    });
    s.addText([{ text: num, options: { fontSize: 54 } }, { text: unit, options: { fontSize: 26 } }], {
      x: x + 0.26, y: 2.46, w: 2.7, h: 0.98, isTextBox: true, margin: 0,
      fontFace: SANS, bold: true, color: dark ? PAPER : INK, valign: "middle",
    });
    s.addText("準確率　" + model, {
      x: x + 0.26, y: 3.46, w: 2.7, h: 0.3, isTextBox: true, margin: 0,
      fontFace: SANS, fontSize: 12, color: dark ? "D6D6DB" : "3F3F46",
    });
    s.addText(sub, {
      x: x + 0.26, y: 3.84, w: 2.7, h: 0.44, isTextBox: true, margin: 0,
      fontFace: SANS, fontSize: 11, color: dark ? "D6D6DB" : "3F3F46", lineSpacingMultiple: 1.2,
    });
  });

  card(s, { x: M + 7.4, y: 1.96, w: CW - 7.4, h: 2.5 });
  s.addText("兩次評測都沒有把\n詐騙或假訊息判成安全", {
    x: M + 7.68, y: 2.18, w: CW - 8.0, h: 0.92, isTextBox: true, margin: 0,
    fontFace: SANS, fontSize: 19, bold: true, color: INK, lineSpacingMultiple: 1.15,
  });
  s.addText("也就是漏判（false negative）為 0。前一版的 5 次誤報全部是把反詐宣導或政府補助公告誤判成詐騙，新版已全部判對。現行結果的 95% 信賴區間為 0.976–1.000。", {
    x: M + 7.68, y: 3.2, w: CW - 8.0, h: 1.1, isTextBox: true, margin: 0,
    fontFace: SANS, fontSize: 12, color: "3F3F46", lineSpacingMultiple: 1.3,
  });

  card(s, { x: M, y: 4.72, w: CW, h: 1.42, tint: true });
  s.addText("這個 100% 不能解讀成「系統不會出錯」", {
    x: M + 0.3, y: 4.9, w: CW - 0.6, h: 0.38, isTextBox: true, margin: 0,
    fontFace: SANS, fontSize: 16, bold: true, color: AMBER,
  });
  s.addText("150 筆全部判對，代表這組題庫對現行模型已經飽和，分不出模型或設定之間的差異；而且題庫自 2026 年 6 月起就公開在版本庫中，無法排除新模型看過。下一步是把題庫擴充後再比較——這一點在報告與影片中都一併說明。", {
    x: M + 0.3, y: 5.3, w: CW - 0.6, h: 0.72, isTextBox: true, margin: 0,
    fontFace: SANS, fontSize: 12.5, color: "3F3F46", lineSpacingMultiple: 1.3,
  });
}

/* ───────────────────────── 7. 測試與品質 ───────────────────────── */
{
  const s = page("用什麼方法檢驗成果", "四種方法並行，其中兩種刻意交給沒有參與實作的人執行，避免自己檢查自己。");
  const stats = [["700", "後端自動化測試"], ["385", "前端自動化測試"], ["46", "測試計畫書項目"], ["27 / 30", "P0 重測通過"]];
  const sw = (CW - 0.36 * 3) / 4;
  stats.forEach(([v, k], i) => {
    const x = M + i * (sw + 0.36);
    card(s, { x, y: 1.92, w: sw, h: 1.34 });
    s.addText(v, {
      x: x + 0.24, y: 2.06, w: sw - 0.48, h: 0.66, isTextBox: true, margin: 0,
      fontFace: SANS, fontSize: 34, bold: true, color: INK, valign: "middle",
    });
    s.addText(k, {
      x: x + 0.24, y: 2.74, w: sw - 0.48, h: 0.34, isTextBox: true, margin: 0,
      fontFace: SANS, fontSize: 12, color: "3F3F46",
    });
  });

  s.addText("測試計畫書 TP-FNV-2026-01：5 類 46 項，含通過準則與中止規則。第一輪 P0 通過 23／30，修正缺陷後重測 27／30。", {
    x: M, y: 3.46, w: CW, h: 0.4, isTextBox: true, margin: 0,
    fontFace: SANS, fontSize: 13, color: INK, valign: "middle",
  });

  const rows = [
    ["PF-2", "未通過", "語意快取命中率 65%（13／20），未達 70% 的準則。沒有為了讓它通過而調低 0.75 的門檻——那是實測校準值，調低會提高誤命中。已排定由組員重新出題後重測。", RED],
    ["UI-1", "素材已補齊", "介面逐格檢核。深色版截圖已於 9 月 20 日補齊（54 張），檢核表共 143 列，由非實作組員勾核、另一位組員覆核中。", INK],
    ["UI-6、PF-1、OP-1", "未執行", "分別需要另外安裝的比對工具、未合入的量測參數，以及全新環境的重新取得流程；均非測試失敗。", MUTED],
  ];
  rows.forEach(([id, state, text, colour], i) => {
    const y = 4.02 + i * 0.78;
    s.addShape(pres.ShapeType.line, { x: M, y, w: CW, h: 0, line: { color: LINE, width: 1 } });
    s.addText(id, {
      x: M, y: y + 0.1, w: 1.9, h: 0.3, isTextBox: true, margin: 0,
      fontFace: SANS, fontSize: 13, bold: true, color: INK,
    });
    s.addText(state, {
      x: M + 1.9, y: y + 0.1, w: 1.4, h: 0.3, isTextBox: true, margin: 0,
      fontFace: SANS, fontSize: 13, bold: true, color: colour,
    });
    s.addText(text, {
      x: M + 3.4, y: y + 0.08, w: CW - 3.4, h: 0.62, isTextBox: true, margin: 0,
      fontFace: SANS, fontSize: 11.5, color: "3F3F46", lineSpacingMultiple: 1.22, valign: "top",
    });
  });
}

/* ────────────────────── 8. 誠實交代的限制 ────────────────────── */
{
  const s = page("誠實交代的限制", "以下每一項都寫在書面報告、投影片與簡報影片裡，不迴避。");
  const items = [
    ["Threads 機器人尚未對外開放", "流程與程式都完成並以模擬模式驗證過，但要公開回覆一般使用者，必須先通過 Meta 的 App Review 與企業驗證；在那之前只有被加入測試名單的帳號收得到回覆。"],
    ["評測資料集已飽和", "150 筆對現行模型已經分不出差異，需要擴充後再比較。"],
    ["語意快取命中率未達準則", "65% 對 70% 的目標。不以調低門檻的方式讓它通過。"],
    ["免費雲端方案會休眠", "後端 15 分鐘沒有流量會休眠，喚醒約 1 分鐘；前端會自動重試並顯示提示，但第一次查詢仍可能較慢。"],
    ["知識庫仍有待清理的資料", "9/20 檢查發現雲端知識庫 128 筆中有 24 筆的「查核來源」其實是求證平台上尚未有判定的回報貼文，卻被標成查核機構等級。已列入待辦，下一期清除或重新標記。"],
    ["AI 判讀僅供參考", "每一頁都標示判讀由 AI 自動產生、可能有誤，請使用者自行查證；另提供隱私政策與資料刪除說明。"],
  ];
  const colW = (CW - 0.4) / 2;
  items.forEach(([h, b], i) => {
    const x = M + (i % 2) * (colW + 0.4);
    const y = 1.86 + Math.floor(i / 2) * 1.52;
    s.addText(`${i + 1}.　${h}`, {
      x, y, w: colW, h: 0.34, isTextBox: true, margin: 0,
      fontFace: SANS, fontSize: 15, bold: true, color: INK, valign: "middle",
    });
    s.addText(b, {
      x: x + 0.34, y: y + 0.36, w: colW - 0.34, h: 0.96, isTextBox: true, margin: 0,
      fontFace: SANS, fontSize: 11.5, color: "3F3F46", lineSpacingMultiple: 1.28, valign: "top",
    });
  });
}

/* ───────────────────────── 9. 下一步與分工 ───────────────────────── */
{
  const s = page("下一步與分工");
  s.addText("下一步", {
    x: M, y: 1.72, w: 6.0, h: 0.4, isTextBox: true, margin: 0,
    fontFace: SANS, fontSize: 19, bold: true, color: INK,
  });
  const next = [
    "Threads 實機串接：申請 Meta App Review 與企業驗證，完成後對外開放。",
    "找非團隊成員的一般使用者實測，記錄達成率與誤解之處，作為第三方驗證。",
    "擴充評測資料集並重新評測，取得能分辨模型差異的結果。",
    "完成 PF-2 重測，並清理知識庫中 24 筆標記錯誤的來源。",
    "補做 UI-6、PF-1、OP-1 三項未執行的測試。",
    "開放首頁的圖片上傳介面（後端端點已具備檔頭檢查與大小限制）。",
  ];
  next.forEach((t, i) => {
    s.addText(`${i + 1}.`, {
      x: M, y: 2.22 + i * 0.62, w: 0.34, h: 0.36, isTextBox: true, margin: 0,
      fontFace: SANS, fontSize: 12.5, bold: true, color: MUTED, valign: "top",
    });
    s.addText(t, {
      x: M + 0.36, y: 2.2 + i * 0.62, w: 5.7, h: 0.58, isTextBox: true, margin: 0,
      fontFace: SANS, fontSize: 12.5, color: "3F3F46", lineSpacingMultiple: 1.25, valign: "top",
    });
  });

  s.addText("分工", {
    x: M + 6.5, y: 1.72, w: CW - 6.5, h: 0.4, isTextBox: true, margin: 0,
    fontFace: SANS, fontSize: 19, bold: true, color: INK,
  });
  const team = [
    ["廖晢勛", "組員 A．測試負責人", "系統實作與部署、測試執行與彙整、金鑰與資料管理"],
    ["石岱勳", "組員 B．介面測試", "介面截圖逐格勾核、手機實機與行動網路測試"],
    ["姚睿", "組員 C．績效與品質數據", "語意快取題組出題與命中率量測、效能數據整理"],
    ["張宇宏", "組員 D．文件與審查", "維護測試計畫書、覆核檢核表、文件一致性檢查"],
    ["廖育翔", "組員 E．影片與簡報", "簡報影片與投影片、報告呈現"],
  ];
  team.forEach(([n, role, work], i) => {
    const y = 2.2 + i * 0.78;
    s.addShape(pres.ShapeType.line, { x: M + 6.5, y, w: CW - 6.5, h: 0, line: { color: LINE, width: 1 } });
    s.addText(n, {
      x: M + 6.5, y: y + 0.1, w: 1.1, h: 0.3, isTextBox: true, margin: 0,
      fontFace: SANS, fontSize: 13, bold: true, color: INK,
    });
    s.addText(role, {
      x: M + 7.6, y: y + 0.1, w: 1.9, h: 0.3, isTextBox: true, margin: 0,
      fontFace: SANS, fontSize: 11.5, color: MUTED,
    });
    s.addText(work, {
      x: M + 6.5, y: y + 0.4, w: CW - 6.5, h: 0.3, isTextBox: true, margin: 0,
      fontFace: SANS, fontSize: 11.5, color: "3F3F46",
    });
  });
}

/* ─────────────────────── 10. 附件與可查證位置 ─────────────────────── */
{
  const s = pres.addSlide();
  pageNo += 1;
  s.background = { color: INK };
  s.addText("附件與可查證的位置", {
    x: M + 0.5, y: 0.8, w: CW - 1, h: 0.66, isTextBox: true, margin: 0,
    fontFace: SANS, fontSize: 30, bold: true, color: PAPER,
  });
  const links = [
    ["線上系統", "https://fakenewsverify.vercel.app"],
    ["簡報影片（4 分 38 秒）", "https://fakenewsverify.vercel.app/demo/presentation_v1.mp4"],
    ["原始碼", "github.com/cansfakenewsverify/AI-Fake-News-Verification-System"],
    ["測試計畫書", "docs/test/TP-FNV-2026-01.md（v1.5）"],
    ["評測資料與結果", "code/backend/data/eval_set.csv、eval_*.csv"],
    ["介面檢核表與截圖", "docs/test/ui_checklist.csv、docs/test/screens/"],
    ["規格與設計文件", "docs/rebuild/（共識、規格書 v1.3、設計稿、實作票、部署手冊）"],
  ];
  links.forEach(([k, v], i) => {
    const y = 1.74 + i * 0.52;
    s.addText(k, {
      x: M + 0.5, y, w: 3.2, h: 0.4, isTextBox: true, margin: 0,
      fontFace: SANS, fontSize: 13, bold: true, color: "B9B9C2", valign: "middle",
    });
    s.addText(v, {
      x: M + 3.9, y, w: CW - 4.4, h: 0.4, isTextBox: true, margin: 0,
      fontFace: SANS, fontSize: 13, color: PAPER, valign: "middle",
    });
  });
  s.addText("本專題的程式實作與自動化測試執行由 AI 程式開發助理 Claude Code（Anthropic）協助完成，全程在負責人監督下進行。需要人工判斷的工作——介面勾核、資料清洗審閱、測試結論與簽核——由組員與審查者執行，不由 AI 代為判定。此說明同時記載於測試計畫書中。", {
    x: M + 0.5, y: 5.56, w: CW - 1, h: 0.86, isTextBox: true, margin: 0,
    fontFace: SANS, fontSize: 11, color: "9A9AA6", lineSpacingMultiple: 1.3,
  });
  s.addText(`${pageNo} / ${TOTAL}`, {
    x: W - M - 1.6, y: 6.72, w: 1.6, h: 0.32, isTextBox: true, margin: 0,
    fontFace: SANS, fontSize: 11, color: "9A9AA6", align: "right", valign: "middle",
  });
}

await pres.writeFile({ fileName: OUT });
console.log(`${path.relative(REPO, OUT)}  ${(fs.statSync(OUT).size / 1024).toFixed(0)} KB  ${TOTAL} 張`);
