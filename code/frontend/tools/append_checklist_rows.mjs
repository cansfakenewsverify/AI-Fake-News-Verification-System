// Adds one UI-1 checklist row per screenshot recorded in docs/test/screens/shots_<theme>.json.
//
// Usage (from code/frontend):  node tools/append_checklist_rows.mjs --theme dark
//
// Rows are appended before the four trailing "未執行 / 報告後執行" rows so the file still reads
// top-to-bottom, and the note says exactly how each picture was staged (which fixture answered
// which request, what was clicked). Idempotent: a file already in the checklist is not added twice.
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const REPO = path.resolve(HERE, "..", "..", "..");
const CSV = path.join(REPO, "docs", "test", "ui_checklist.csv");
const argv = process.argv.slice(2);
const THEME = argv[argv.indexOf("--theme") + 1] || "dark";
const SHOTS = path.join(REPO, "docs", "test", "screens", `shots_${THEME}.json`);

/* ── a small CSV reader/writer (the note column contains commas and quotes) ── */
function parseCsv(text) {
  const rows = [];
  let row = [], field = "", quoted = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (quoted) {
      if (c === '"') { if (text[i + 1] === '"') { field += '"'; i++; } else quoted = false; }
      else field += c;
    } else if (c === '"') quoted = true;
    else if (c === ",") { row.push(field); field = ""; }
    else if (c === "\n") { row.push(field); rows.push(row); row = []; field = ""; }
    else if (c !== "\r") field += c;
  }
  if (field || row.length) { row.push(field); rows.push(row); }
  return rows.filter((r) => r.length > 1 || r[0] !== "");
}
const cell = (v) => (/[",\n]/.test(v) ? `"${v.replace(/"/g, '""')}"` : v);
const toCsv = (rows) => rows.map((r) => r.map(cell).join(",")).join("\r\n") + "\r\n";

/* ── build the rows ────────────────────────────────────────────────────────── */
const shots = JSON.parse(fs.readFileSync(SHOTS, "utf8"));
const raw = fs.readFileSync(CSV, "utf8").replace(/^﻿/, "");
const rows = parseCsv(raw);
const header = rows[0];
const col = Object.fromEntries(header.map((h, i) => [h, i]));
const body = rows.slice(1);

const already = new Set(body.map((r) => r[col.file]));
const lastId = Math.max(...body.map((r) => Number((r[col.ID] || "").split("-").pop()) || 0));

const ACTION_TEXT = { fill: "填入文字", click: "點擊", type: "輸入關鍵字", key: "按 Enter", wait: "等待", scrollBottom: "捲到底" };
const staged = (s) => {
  const api = s.api.length ? s.api.join("；") : "無 API 請求";
  const acts = s.actions.length ? `；操作：${s.actions.map((a) => ACTION_TEXT[a] || a).join("→")}` : "";
  const seen = s.waited_for ? `；已確認畫面出現「${s.waited_for}」` : "";
  return `證據：${THEME === "dark" ? "深色" : "淺色"}版由 code/frontend/tools/capture_ui.mjs 擷取（headless Edge，`
    + `dev server 未開 VITE_FIXTURES，改以 CDP 直接回應 /api/*，來源檔為 src/dev/fixtures；未連後端、未呼叫 AI）；`
    + `路由 ${s.route}；回應：${api}${acts}${seen}`;
};

let n = lastId;
const added = [];
for (const s of shots) {
  const file = s.file;
  if (already.has(file)) continue;
  n += 1;
  const r = new Array(header.length).fill("");
  r[col.ID] = `UI-1-${String(n).padStart(3, "0")}`;
  r[col.screen] = s.screen;
  r[col.state] = s.state;
  r[col.width] = s.width;
  r[col.theme] = s.theme;
  r[col.file] = file;
  r[col.result] = "";           // 預檢欄留白：深色版沒有做 Claude 目視預檢，由組員直接勾核
  r[col.note] = staged(s);
  r[col["勾核者"]] = "石岱勳";
  r[col["覆核者"]] = "張宇宏";
  added.push(r);
}

// keep the four "未執行 / 報告後執行" rows at the end
const isTrailing = (r) => !r[col.file].trim();
const out = [header, ...body.filter((r) => !isTrailing(r)), ...added, ...body.filter(isTrailing)];
fs.writeFileSync(CSV, "﻿" + toCsv(out), "utf8");
console.log(`新增 ${added.length} 列（${THEME}），檢核表現在 ${out.length - 1} 列`);
if (added.length) console.log(`  ${added[0][col.ID]} … ${added[added.length - 1][col.ID]}`);
