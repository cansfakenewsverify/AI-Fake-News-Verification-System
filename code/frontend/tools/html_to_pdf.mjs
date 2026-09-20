// Prints a local HTML file to a PDF with headless Edge. No install, no service, no upload.
//
// Usage:  node tools/html_to_pdf.mjs <input.html> <output.pdf> [--landscape]
//
// Used for the printable course forms in presentations/2026-09_進度報告/. The page keeps its own
// @page size and margins, so the result matches the browser's print preview.
//
// Two Windows details this works around:
//   - Edge's --print-to-pdf switch silently produces nothing here, so the PDF is taken over CDP
//     (Page.printToPDF), which does work.
//   - the repo's report folder and file names are Chinese and do not survive the trip through the
//     shell into Edge's command line, so the page is staged in TEMP under an ASCII name first.
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawn } from "node:child_process";

const args = process.argv.slice(2);
const [input, output] = args.filter((a) => !a.startsWith("--"));
const landscape = args.includes("--landscape");
if (!input || !output) {
  console.error("usage: node tools/html_to_pdf.mjs <input.html> <output.pdf> [--landscape]");
  process.exit(1);
}
const src = path.resolve(input);
const dst = path.resolve(output);
if (!fs.existsSync(src)) { console.error(`not found: ${src}`); process.exit(1); }

const EDGE = [
  "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
  "C:/Program Files/Microsoft/Edge/Application/msedge.exe",
].find((p) => fs.existsSync(p));
if (!EDGE) { console.error("Microsoft Edge not found"); process.exit(1); }

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function connect(url) {
  const ws = new WebSocket(url);
  await new Promise((res, rej) => {
    ws.addEventListener("open", res, { once: true });
    ws.addEventListener("error", rej, { once: true });
  });
  let id = 1;
  const pending = new Map();
  ws.addEventListener("message", (ev) => {
    const m = JSON.parse(ev.data);
    if (m.id === undefined) return;
    const p = pending.get(m.id);
    if (!p) return;
    pending.delete(m.id);
    m.error ? p.rej(new Error(`${p.method}: ${m.error.message}`)) : p.res(m.result);
  });
  return {
    ws,
    send(method, params = {}, sessionId) {
      const i = id++;
      return new Promise((res, rej) => {
        pending.set(i, { res, rej, method });
        ws.send(JSON.stringify({ id: i, method, params, ...(sessionId ? { sessionId } : {}) }));
      });
    },
  };
}

async function main() {
  const profile = fs.mkdtempSync(path.join(os.tmpdir(), "html2pdf-"));
  const stage = fs.mkdtempSync(path.join(os.tmpdir(), "html2pdf-src-"));
  const staged = path.join(stage, "page.html");
  fs.copyFileSync(src, staged);
  for (const f of fs.readdirSync(path.dirname(src))) {
    const full = path.join(path.dirname(src), f);
    if (full !== src && fs.statSync(full).isFile() && /\.(css|png|jpe?g|svg|woff2?)$/i.test(f)) {
      fs.copyFileSync(full, path.join(stage, f));
    }
  }

  const port = 9600 + Math.floor(Math.random() * 60);
  const proc = spawn(EDGE, [
    "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
    "--disable-extensions", "--disable-background-networking", "--mute-audio",
    `--user-data-dir=${profile}`, `--remote-debugging-port=${port}`, "about:blank",
  ], { stdio: "ignore" });

  let ver = null;
  for (let i = 0; i < 80 && !ver; i++) {
    try { const r = await fetch(`http://127.0.0.1:${port}/json/version`); if (r.ok) ver = await r.json(); } catch { /* not up */ }
    if (!ver) await sleep(250);
  }
  if (!ver) throw new Error("Edge devtools endpoint never came up");

  const c = await connect(ver.webSocketDebuggerUrl);
  const { targetId } = await c.send("Target.createTarget", { url: "about:blank" });
  const { sessionId } = await c.send("Target.attachToTarget", { targetId, flatten: true });
  const send = (m, p) => c.send(m, p, sessionId);

  await send("Page.enable");
  await send("Runtime.enable");
  await send("Page.navigate", { url: "file:///" + staged.replace(/\\/g, "/") });
  for (let i = 0; i < 80; i++) {
    const r = await send("Runtime.evaluate", { expression: "document.readyState", returnByValue: true }).catch(() => null);
    if (r?.result?.value === "complete") break;
    await sleep(150);
  }
  await sleep(600); // let the page's own script finish drawing

  const pdf = await send("Page.printToPDF", {
    printBackground: true,
    preferCSSPageSize: true,
    landscape,
    displayHeaderFooter: false,
  });
  fs.mkdirSync(path.dirname(dst), { recursive: true });
  fs.writeFileSync(dst, Buffer.from(pdf.data, "base64"));

  try { await c.send("Browser.close"); } catch { /* already gone */ }
  c.ws.close(); proc.kill(); await sleep(400);
  for (const d of [profile, stage]) {
    try { fs.rmSync(d, { recursive: true, force: true }); } catch { /* TEMP keeps it */ }
  }
  console.log(`${path.basename(dst)}  ${(fs.statSync(dst).size / 1024).toFixed(0)} KB`);
}

main().catch((e) => { console.error(e); process.exit(1); });
