// Builds the printable test plan:
//   default  docs/test/TP-FNV-2026-01_精簡版.md
//              → presentations/2026-09_進度報告/04_測試計畫書_TP-FNV-2026-01_v1.6_精簡版.pdf
//   --full   docs/test/TP-FNV-2026-01.md（完整版，第二次簡報要交的版本）
//              → presentations/2026-11_第二次簡報/03_測試計畫書_TP-FNV-2026-01_v2.0_完整版.pdf
//
// Usage (from the repo root):
//   npm install --prefix "%TEMP%\fnv-md" marked@15      (once; kept out of the repo, like pptxgenjs)
//   node presentations/tools/build_testplan_pdf.mjs [--full]
//
// The Markdown file is the source. The HTML only exists in TEMP and is printed by
// code/frontend/tools/html_to_pdf.mjs (headless Edge over CDP). Page numbers come from CSS @page
// margin boxes. The script prints the resulting page count; the short version is meant to stay
// within 15 A4 pages.
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath, pathToFileURL } from "node:url";

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const FULL = process.argv.includes("--full");
const SRC = FULL
  ? path.join(REPO, "docs", "test", "TP-FNV-2026-01.md")
  : path.join(REPO, "docs", "test", "TP-FNV-2026-01_精簡版.md");
const OUT = FULL
  ? path.join(REPO, "presentations", "2026-11_第二次簡報", "03_測試計畫書_TP-FNV-2026-01_v2.0_完整版.pdf")
  : path.join(REPO, "presentations", "2026-09_進度報告", "04_測試計畫書_TP-FNV-2026-01_v1.6_精簡版.pdf");
const MAX_PAGES = FULL ? 120 : 15;

const markedPath = path.join(os.tmpdir(), "fnv-md", "node_modules", "marked", "lib", "marked.esm.js");
if (!fs.existsSync(markedPath)) {
  console.error(`marked not found at ${markedPath}\nrun: npm install --prefix "${path.join(os.tmpdir(), "fnv-md")}" marked@15`);
  process.exit(1);
}
const { marked } = await import(pathToFileURL(markedPath).href);

// Layout follows the reviewed Writer version of the short test plan: Noto Sans TC, 16 pt title,
// navy 13 pt section headings that start a new page, blue 11 pt sub-headings, 7.5 pt tables with
// light-blue (#D9E2F3) header rows and 0.5 pt black rules, 12.7 mm margins, no page numbers.
const CSS = `
  @page { size: A4; margin: 12.7mm; }
  * { box-sizing: border-box; }
  body { margin: 0; font-family: "Noto Sans TC", "Noto Sans CJK TC", "Microsoft JhengHei", sans-serif;
         font-size: 9pt; line-height: 1.55; color: #000; }
  h1 { font-size: 16pt; font-weight: 700; text-align: center; margin: 0 0 1.5mm; }
  p.subtitle { font-size: 12pt; font-weight: 700; text-align: center; margin: 0 0 1mm; }
  p.meta { font-size: 8pt; text-align: center; margin: 0 0 3mm; }
  h2 { font-size: 13pt; font-weight: 700; color: #1f3864; margin: 3.5mm 0 1.5mm; break-after: avoid; break-before: page; }
  h2:first-of-type { break-before: auto; }
  h3 { font-size: 11pt; font-weight: 700; color: #2e5395; margin: 3mm 0 1.2mm; break-after: avoid; }
  h4 { font-size: 10pt; font-weight: 700; color: #2e5395; margin: 2.5mm 0 1mm; break-after: avoid; }
  p { margin: 1mm 0; }
  p.note { font-style: italic; margin: 0 0 1.5mm; }
  div.pb { break-before: page; }
  table { width: 100%; border-collapse: collapse; margin: 1mm 0 2mm; font-size: 7.5pt; line-height: 1.45; }
  th, td { border: 0.5pt solid #000; padding: 0.7mm 1.4mm; text-align: left; vertical-align: top; }
  th { background: #d9e2f3; font-weight: 700; }
  thead { display: table-header-group; }
  tr { break-inside: avoid; }
  td:first-child { white-space: nowrap; }
  table.items td:nth-child(-n+3) { white-space: nowrap; }
  table.results td:nth-child(-n+3) { white-space: nowrap; }
  table.defects td:nth-child(2) { white-space: nowrap; }
  table.retest td:nth-child(-n+3), table.retest td:nth-child(5) { white-space: nowrap; }
  table.sign { break-inside: avoid; }
  table.sign td { height: 8mm; }
`;

// Column behaviour depends on what the table is; tell them apart by their header row.
function classifyTables(html) {
  return html.replace(/<table>([\s\S]*?)<\/table>/g, (whole, body) => {
    const head = (body.match(/<thead>([\s\S]*?)<\/thead>/) || ["", ""])[1];
    const has = (s) => head.includes(`>${s}<`);
    let cls = "";
    if (has("優先") && has("執行")) cls = "items";
    else if (has("結果") && has("重點數據")) cls = "results";
    else if (has("嚴重度")) cls = "defects";
    else if (has("第一輪") && has("重測判定")) cls = "retest";
    return cls ? `<table class="${cls}">${body}</table>` : whole;
  });
}

// The complete edition is read on paper rather than skimmed: larger type than the short version, page
// numbers, headers that never break mid-word, and every column except the ID allowed to wrap (its
// 本次執行 / result cells hold whole sentences).
const FULL_CSS = `
  @page { @bottom-center { content: counter(page) " / " counter(pages); font-size: 9pt; color: #444; } }
  body { font-size: 10.5pt; line-height: 1.6; }
  h1 { font-size: 20pt; }
  h2 { font-size: 15pt; }
  h3 { font-size: 12.5pt; }
  h4 { font-size: 11pt; }
  table { font-size: 9pt; line-height: 1.5; }
  th { white-space: nowrap; }
  table.items td:nth-child(-n+3), table.results td:nth-child(-n+3), table.retest td:nth-child(-n+3), table.retest td:nth-child(5) { white-space: normal; }
  table.items td:first-child, table.results td:first-child, table.retest td:first-child { white-space: nowrap; }
  td code { word-break: break-all; }
`;

const md = fs.readFileSync(SRC, "utf8");
const body = classifyTables(marked.parse(md, { gfm: true }));
const html = `<!doctype html>
<html lang="zh-Hant"><head><meta charset="utf-8"><title>${FULL ? "測試計畫書（完整版 v2.0）" : "測試計畫書（精簡版）"} TP-FNV-2026-01</title>
<style>${CSS}${FULL ? FULL_CSS : ""}</style></head><body>
${body}
</body></html>`;

const staged = path.join(os.tmpdir(), "fnv-md", FULL ? "testplan_full.html" : "testplan_short.html");
fs.writeFileSync(staged, html, "utf8");

const tool = path.join(REPO, "code", "frontend", "tools", "html_to_pdf.mjs");
const run = spawnSync(process.execPath, [tool, staged, OUT], { stdio: "inherit" });
if (run.status !== 0) process.exit(run.status ?? 1);

const pages = (fs.readFileSync(OUT).toString("latin1").match(/\/Type\s*\/Page[^s]/g) || []).length;
console.log(`${path.relative(REPO, OUT)}：${pages} 頁${pages > MAX_PAGES ? `（超過 ${MAX_PAGES} 頁）` : ""}`);
