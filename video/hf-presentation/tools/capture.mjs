// Records the LIVE site (https://fakenewsverify.vercel.app) with headless Edge over CDP.
//
// Usage (from video/hf-presentation):
//   node tools/capture.mjs                # every take in tools/takes.mjs
//   node tools/capture.mjs home url_check # only those takes
//   node tools/capture.mjs --out D:\raw   # override the raw output folder
//
// Output: <rawDir>/<take>/frames/*.png + meta.json  (startWall, per-frame ts, action marks,
// and whatever the take recorded: result ids, cache layers, the composed Threads intent URL).
// Nothing here writes to the repo except the raw folder you point it at.
//
// Rules this script enforces (docs/demo/presentation_video_brief.md):
//   - no sign-ins; outbound clicks to threads.com are intercepted, never followed
//   - http(s) URLs in the page text are covered by an opaque mask block before any frame is kept
//   - the page's own data and DOM text are never rewritten, only overlaid
//   - AI verifications on the live site are counted and capped (AI_BUDGET)
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { launch, sleep } from "./cdp.mjs";
import { TAKES, SITE } from "./takes.mjs";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const argv = process.argv.slice(2);
const outFlag = argv.indexOf("--out");
// Raw frames are big and intermediate: they live in TEMP, never in the repo (and never inside the
// OneDrive-synced Desktop tree, which would churn the sync client for thousands of PNGs).
const RAW = outFlag >= 0 ? argv[outFlag + 1]
  : process.env.FNV_RAW || path.join(os.tmpdir(), "fnv-presentation-raw");
const only = argv.filter((a, i) => !a.startsWith("--") && !(outFlag >= 0 && i === outFlag + 1));
const AI_BUDGET = 12;

const OVERLAY = fs.readFileSync(path.join(ROOT, "tools", "overlay.js"), "utf8");
const NOTES_FILE = path.join(RAW, "notes.json");

let aiSpent = 0;
/** notes captured per take, kept on disk so a retake can continue on an earlier take's result page */
const allNotes = fs.existsSync(NOTES_FILE) ? JSON.parse(fs.readFileSync(NOTES_FILE, "utf8")) : {};

async function main() {
  fs.mkdirSync(RAW, { recursive: true });
  const takes = TAKES.filter((t) => !only.length || only.includes(t.name));
  if (!takes.length) {
    console.error(`no take matched: ${only.join(", ")}`);
    console.error(`known takes: ${TAKES.map((t) => t.name).join(", ")}`);
    process.exit(1);
  }

  await waitForBackend();

  let port = 9333;
  for (const take of takes) {
    if (take.aiCalls && aiSpent + take.aiCalls > AI_BUDGET) {
      console.error(`[${take.name}] skipped: would exceed the ${AI_BUDGET} AI-call budget (spent ${aiSpent})`);
      continue;
    }
    const d = deviceOf(take);
    // One browser per take: the device scale factor is a launch flag, and a fresh profile also
    // guarantees no leftover history rows or remembered theme leak into the next take.
    const session = await launch({ port: port++, width: d.width * d.deviceScaleFactor, height: d.height * d.deviceScaleFactor, dsf: d.deviceScaleFactor });
    const { page } = session;
    try {
      await page.send("Page.enable");
      await page.send("Runtime.enable");
      await page.send("Emulation.setScriptExecutionDisabled", { value: false });
      await page.send("Page.addScriptToEvaluateOnNewDocument", { source: OVERLAY });
      const notes = await record(page, take);
      aiSpent += notes.aiUsed;
      console.log(`[${take.name}] ok  frames=${notes.frames}  dur=${notes.duration}s  ai_spent=${aiSpent}`);
      if (Object.keys(notes.captured).length) console.log(`   ${JSON.stringify(notes.captured)}`);
    } finally {
      await session.close();
    }
  }
  console.log(`\nraw folder: ${RAW}`);
  console.log(`AI verifications used on the live site: ${aiSpent} / ${AI_BUDGET}`);
}

/**
 * The site lays out at its real breakpoint width in CSS px but is captured at 1.5x (desktop) or
 * 2x (phone) device pixels, so the film gets native 1920x1080 frames of the genuine layout.
 * Every coordinate in a take stays in CSS px, which is what Input.dispatchMouseEvent expects.
 */
function deviceOf(take) {
  return take.device === "phone"
    ? { width: 390, height: 844, deviceScaleFactor: 2, mobile: true }
    : { width: 1280, height: 720, deviceScaleFactor: 1.5, mobile: false };
}

async function waitForBackend() {
  process.stdout.write("waking the backend ...");
  for (let i = 0; i < 40; i++) {
    try {
      const r = await fetch(`${SITE}/api/health`);
      if (r.ok) {
        const h = await r.json();
        console.log(` ok (ai_available=${h.ai_available}, daily=${h.daily_ai_calls.used}/${h.daily_ai_calls.cap}, storage=${h.storage_backend})`);
        if (!h.ai_available) throw new Error("backend reports ai_available=false");
        return h;
      }
    } catch {
      /* still asleep */
    }
    process.stdout.write(".");
    await sleep(3000);
  }
  throw new Error("backend did not answer /api/health");
}

/** Apply the take's device profile, run its steps while the screencast runs, write frames + meta. */
async function record(page, take) {
  const dir = path.join(RAW, take.name, "frames");
  // Windows keeps handles on freshly written PNGs for a moment (indexer / Defender): retry, and
  // if the folder still will not go, move it aside rather than mixing takes.
  try {
    fs.rmSync(path.join(RAW, take.name), { recursive: true, force: true, maxRetries: 12, retryDelay: 250 });
  } catch {
    fs.renameSync(path.join(RAW, take.name), path.join(RAW, `${take.name}.old-${Date.now()}`));
  }
  fs.mkdirSync(dir, { recursive: true });

  const device = deviceOf(take);
  await page.send("Emulation.setDeviceMetricsOverride", { ...device, screenWidth: device.width, screenHeight: device.height });
  await page.send("Emulation.setTouchEmulationEnabled", device.mobile ? { enabled: true, maxTouchPoints: 5 } : { enabled: false });
  await page.send("Emulation.setUserAgentOverride", device.mobile
    ? { userAgent: "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/153.0.0.0 Mobile Safari/537.36", platform: "Android" }
    : { userAgent: "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36 Edg/153.0.0.0", platform: "Win32" });
  await page.send("Emulation.setEmulatedMedia", { media: "screen", features: [{ name: "prefers-color-scheme", value: take.scheme ?? "light" }] });

  // Pre-roll: get the page into its starting state before the screencast begins, so the take
  // opens on a settled frame. A take that reads a result page continues from the URL an earlier
  // take recorded (the result id is only known at run time).
  let start = "/";
  if (take.needsResultFrom) {
    const url = allNotes[take.needsResultFrom]?.result_url;
    if (!url) throw new Error(`[${take.name}] needs ${take.needsResultFrom} to have run first (no result_url)`);
    start = url;
  }
  await page.send("Page.navigate", { url: start.startsWith("http") ? start : SITE + start });
  await settle(page);
  if (!take.needsResultFrom) await evalPage(page, `try{localStorage.clear();sessionStorage.clear()}catch(e){}`);
  if (take.needsResultFrom) { await evalPage(page, `window.scrollTo(0,0)`); await sleep(400); }
  if (device.mobile) await evalPage(page, `window.__cap.setCursorVisible(false)`);

  const ctx = { page, take, notes: {}, marks: [] };
  if (take.setup) await runSteps(ctx, take.setup);

  const frames = [];
  let startWall = null;
  let n = 0;
  let stalled = null;
  const off = page.on("Page.screencastFrame", (p) => {
    const name = `f${String(n++).padStart(5, "0")}.png`;
    const ts = p.metadata.timestamp;
    if (startWall === null) startWall = ts;
    try {
      fs.writeFileSync(path.join(dir, name), Buffer.from(p.data, "base64"));
      frames.push({ name, ts });
    } catch (e) {
      stalled = stalled ?? `write failed: ${e.message}`;
    }
    // Ack must always go out, or Chrome stops sending frames after its small in-flight window.
    page.send("Page.screencastFrameAck", { sessionId: p.sessionId })
      .catch((e) => { stalled = stalled ?? `ack failed: ${e.message}`; });
  });

  await page.send("Page.startScreencast", { format: "png", everyNthFrame: 1, maxWidth: 2400, maxHeight: 2400 });
  // Marks are stamped from the wall clock, not from the last frame that happened to have arrived:
  // frame delivery lags the page by a variable amount, which would put a mark on the wrong shot.
  // Page.screencastFrame timestamps are seconds since the epoch, the same clock as Date.now().
  ctx.t0 = () => (startWall === null ? 0 : Date.now() / 1000 - startWall);
  await runSteps(ctx, take.steps);
  await sleep(400);
  await page.send("Page.stopScreencast");
  off();
  await sleep(200);
  if (stalled) throw new Error(`[${take.name}] screencast stalled: ${stalled}`);

  const meta = {
    take: take.name,
    site: SITE,
    device,
    scheme: take.scheme ?? "light",
    recordedAt: new Date().toISOString(),
    startWall,
    frames,
    marks: ctx.marks,
    notes: ctx.notes,
    aiCalls: take.aiCalls ?? 0,
  };
  // A cache hit costs no AI call; only a miss does. The take declares the worst case.
  const hitCache = typeof ctx.notes.chip === "string" && ctx.notes.chip.includes("快取命中");
  meta.aiUsed = hitCache ? 0 : (take.aiCalls ?? 0);
  fs.writeFileSync(path.join(dir, "meta.json"), JSON.stringify(meta, null, 1) + "\n", "utf8");
  allNotes[take.name] = { ...allNotes[take.name], ...ctx.notes };
  fs.writeFileSync(NOTES_FILE, JSON.stringify(allNotes, null, 1) + "\n", "utf8");
  return {
    frames: frames.length,
    duration: frames.length ? (frames[frames.length - 1].ts - startWall).toFixed(2) : "0",
    aiUsed: meta.aiUsed,
    captured: ctx.notes,
  };
}

async function runSteps(ctx, steps) {
  for (const step of steps) await runStep(ctx, step);
}

async function runStep(ctx, step) {
  const { page } = ctx;
  const [kind] = Object.keys(step);
  const mark = (extra = {}) => ctx.marks.push({ t: +(ctx.t0 ? ctx.t0() : 0).toFixed(3), kind, ...extra });

  switch (kind) {
    case "goto": {
      await page.send("Page.navigate", { url: step.goto.startsWith("http") ? step.goto : SITE + step.goto });
      await settle(page);
      mark({ url: step.goto });
      return;
    }
    case "wait":
      await sleep(step.wait * 1000);
      return;
    case "mark":
      mark({ label: step.mark });
      return;
    case "waitFor": {
      const { target, timeout = 90 } = typeof step.waitFor === "string" ? { target: step.waitFor } : step.waitFor;
      const deadline = Date.now() + timeout * 1000;
      while (Date.now() < deadline) {
        const hit = await evalPage(page, `!!window.__cap.find(${JSON.stringify(target)})`);
        if (hit) { mark({ target }); return; }
        await sleep(250);
      }
      throw new Error(`[${ctx.take.name}] waitFor timed out: ${JSON.stringify(target)}`);
    }
    case "move": {
      const box = await boxOf(page, step.move);
      await glide(ctx, box.cx, box.cy, step.ms ?? 700);
      return;
    }
    case "click": {
      const box = await boxOf(page, step.click);
      await glide(ctx, box.cx, box.cy, step.ms ?? 650);
      await evalPage(page, `window.__cap.ripple(${box.cx},${box.cy})`);
      await mouse(page, "mousePressed", box.cx, box.cy);
      await sleep(70);
      await mouse(page, "mouseReleased", box.cx, box.cy);
      mark({ target: step.click });
      await sleep(step.after ?? 350);
      return;
    }
    case "paste": {
      // Value set through the native setter + an input event: the same result as a real paste,
      // without typing 60 characters of rumour text on camera.
      const ok = await evalPage(page, `window.__cap.setValue(${JSON.stringify(step.paste.target)}, ${JSON.stringify(step.paste.text)})`);
      if (!ok) throw new Error(`[${ctx.take.name}] paste target not found: ${JSON.stringify(step.paste.target)}`);
      mark({ chars: [...step.paste.text].length });
      await sleep(step.after ?? 500);
      return;
    }
    case "type": {
      const box = await boxOf(page, step.type.target);
      await glide(ctx, box.cx, box.cy, 500);
      await mouse(page, "mousePressed", box.cx, box.cy);
      await mouse(page, "mouseReleased", box.cx, box.cy);
      const cps = step.type.cps ?? 11;
      for (const ch of step.type.text) {
        await page.send("Input.insertText", { text: ch });
        await sleep(1000 / cps);
      }
      mark({ text: step.type.text });
      return;
    }
    case "key":
      await page.send("Input.dispatchKeyEvent", { type: "keyDown", key: step.key, code: step.key, windowsVirtualKeyCode: step.key === "Enter" ? 13 : 0, text: step.key === "Enter" ? "\r" : undefined });
      await page.send("Input.dispatchKeyEvent", { type: "keyUp", key: step.key, code: step.key, windowsVirtualKeyCode: step.key === "Enter" ? 13 : 0 });
      mark({ key: step.key });
      await sleep(step.after ?? 300);
      return;
    case "scroll": {
      const to = typeof step.scroll === "number"
        ? step.scroll
        : await evalPage(page, `window.__cap.topOf(${JSON.stringify(step.scroll)}, ${step.offset ?? 120})`);
      await evalPage(page, `window.__cap.scrollTo(${to}, ${step.ms ?? 1400})`);
      await sleep((step.ms ?? 1400) + 220);
      mark({ to });
      return;
    }
    case "capture": {
      // Read something out of the live page into meta.json (result id, cache chip, intent URL...).
      const value = await evalPage(page, step.capture.js);
      ctx.notes[step.capture.as] = value;
      mark({ as: step.capture.as, value });
      return;
    }
    case "js":
      await evalPage(page, step.js);
      return;
    default:
      throw new Error(`unknown step: ${kind}`);
  }
}

async function glide(ctx, x, y, ms) {
  const { page } = ctx;
  const from = await evalPage(page, `window.__cap.cursor()`);
  const steps = Math.max(2, Math.round(ms / 16));
  for (let i = 1; i <= steps; i++) {
    const k = i / steps;
    const e = k < 0.5 ? 2 * k * k : 1 - Math.pow(-2 * k + 2, 2) / 2; // easeInOutQuad
    const px = from.x + (x - from.x) * e;
    const py = from.y + (y - from.y) * e;
    await mouse(page, "mouseMoved", px, py);
    await sleep(16);
  }
}

function mouse(page, type, x, y) {
  return page.send("Input.dispatchMouseEvent", { type, x: Math.round(x), y: Math.round(y), button: "left", clickCount: type === "mouseMoved" ? 0 : 1, buttons: type === "mousePressed" ? 1 : 0 });
}

async function boxOf(page, target, tries = 40) {
  for (let i = 0; i < tries; i++) {
    const box = await evalPage(page, `window.__cap.box(${JSON.stringify(target)})`);
    if (box) return box;
    await sleep(250);
  }
  throw new Error(`target not found: ${JSON.stringify(target)}`);
}

async function evalPage(page, expression) {
  const r = await page.send("Runtime.evaluate", { expression, returnByValue: true, awaitPromise: true, userGesture: true });
  if (r.exceptionDetails) throw new Error(`page eval failed: ${r.exceptionDetails.text} :: ${expression.slice(0, 160)}`);
  return r.result.value;
}

/** Wait for load + one animation frame of quiet, then let the overlay re-mask. */
async function settle(page) {
  for (let i = 0; i < 80; i++) {
    const state = await evalPage(page, `document.readyState`).catch(() => null);
    if (state === "complete") break;
    await sleep(150);
  }
  await sleep(700);
  await evalPage(page, `window.__cap && window.__cap.remask()`).catch(() => {});
}

main().catch((e) => { console.error(e); process.exit(1); });
