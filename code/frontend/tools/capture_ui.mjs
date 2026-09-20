// Screenshot every S1–S4 screen state for the UI-1 checklist, in one theme, reproducibly.
//
// Usage (from code/frontend, with the dev server already running):
//   $env:VITE_FIXTURES=""; npm run dev -- --port 5399      # in one terminal
//   node tools/capture_ui.mjs --theme dark --out ../../docs/test/screens
//   node tools/capture_ui.mjs --theme dark --only S3,S4    # just some screens
//
// Why it does NOT use VITE_FIXTURES: in fixture mode the app never calls fetch, so a loading or
// backend-down state cannot be staged. Instead the dev server runs normally and every /api/*
// request is answered by this script over CDP, from the SAME files in src/dev/fixtures — plus the
// two things a file cannot express: a delay (loading / submitting) and a transport failure
// (backend_down / network_error). Nothing here touches a backend, a database or an AI call.
//
// Output: <out>/S{n}_{state}_{width}_{theme}.png, and a shots.json next to them recording, per
// shot, exactly which fixture answered which request and what was clicked — so the checklist note
// can say how the picture was produced.
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const FRONTEND = path.resolve(HERE, "..");
const FIXTURES = path.join(FRONTEND, "src", "dev", "fixtures");

const argv = process.argv.slice(2);
const flag = (name, dflt) => {
  const i = argv.indexOf(`--${name}`);
  return i >= 0 ? argv[i + 1] : dflt;
};
const THEME = flag("theme", "dark");
const BASE = flag("base", "http://localhost:5399");
const OUT = path.resolve(flag("out", path.join(FRONTEND, "..", "..", "docs", "test", "screens")));
const ONLY = (flag("only", "") || "").split(",").filter(Boolean);
const PORT = Number(flag("port", 9500));

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const fixture = (name) => JSON.parse(fs.readFileSync(path.join(FIXTURES, name), "utf8"));

/* ────────────────────────────── what to shoot ────────────────────────────── */
// `api` maps "METHOD /path/prefix" to a reply: {file} from src/dev/fixtures, {status, body},
// {delay} seconds before replying, or {fail: true} for a transport error.
const RESULT = (id) => `/api/result/${id}`;
const SHOTS = [
  // ── S1 首頁 ────────────────────────────────────────────────────────────────
  {
    screen: "S1 首頁", n: 1, state: "empty", route: "/", widths: [375, 1280],
    waitFor: "貼上訊息，10 秒知道真假",
  },
  {
    screen: "S1 首頁", n: 1, state: "backend_down", route: "/", widths: [375, 1280],
    api: { "GET /api/health": { fail: true } },
    waitFor: "暫時連不上伺服器",
  },
  {
    screen: "S1 首頁", n: 1, state: "validation", route: "/", widths: [375, 1280],
    actions: [{ click: "開始查證" }, { wait: 0.8 }],
    waitFor: "請先貼上要查證的內容",
  },
  {
    screen: "S1 首頁", n: 1, state: "submitting", route: "/", widths: [375, 1280],
    api: { "POST /api/analyze": { file: "analyze_text_ok.json", delay: 6 } },
    actions: [{ fill: "網傳吃香蕉配優格會中毒" }, { click: "開始查證" }, { wait: 1.4 }],
    waitFor: "查證中",
  },
  {
    screen: "S1 首頁", n: 1, state: "rate_limited", route: "/", widths: [375, 1280],
    api: { "POST /api/analyze": { file: "analyze_rate_limited.json" } },
    actions: [{ fill: "網傳吃香蕉配優格會中毒" }, { click: "開始查證" }, { wait: 1.2 }],
    waitFor: "查證太頻繁",
  },
  {
    screen: "S1 首頁", n: 1, state: "quota", route: "/", widths: [375, 1280],
    api: { "POST /api/analyze": { file: "analyze_daily_cap_reached.json" } },
    actions: [{ fill: "網傳吃香蕉配優格會中毒" }, { click: "開始查證" }, { wait: 1.2 }],
    waitFor: "今日查證額度已用完",
  },

  // ── S2 結果頁 ──────────────────────────────────────────────────────────────
  {
    screen: "S2 結果頁", n: 2, state: "404", route: "/r/fx-notfound", widths: [375, 1280],
    api: { [`GET ${RESULT("fx-notfound")}`]: { file: "result_fx-notfound.json" } },
    waitFor: "找不到這筆查證",
  },
  {
    screen: "S2 結果頁", n: 2, state: "loading", route: "/r/fx-pending", widths: [375, 1280],
    api: { [`GET ${RESULT("fx-pending")}`]: { file: "result_fx-pending.json" } },
    waitFor: "AI 正在查證",
  },
  {
    screen: "S2 結果頁", n: 2, state: "network_error", route: "/r/fx-red-misinfo", widths: [375, 1280],
    api: { "GET /api/result": { fail: true }, "GET /api/health": { fail: true } },
    waitFor: "連不上伺服器",
  },
  {
    screen: "S2 結果頁", n: 2, state: "failed", route: "/r/fx-failed", widths: [375, 1280],
    api: { [`GET ${RESULT("fx-failed")}`]: { file: "result_fx-failed.json" } },
    waitFor: "出了點問題",
  },
  {
    screen: "S2 結果頁", n: 2, state: "ai_unavailable", route: "/r/fx-ai-unavailable", widths: [1280],
    api: { [`GET ${RESULT("fx-ai-unavailable")}`]: { file: "result_fx-ai-unavailable.json" } },
    waitFor: "AI 服務暫時無法使用",
  },
  {
    screen: "S2 結果頁", n: 2, state: "success", route: "/r/fx-red-misinfo", widths: [1280],
    api: { [`GET ${RESULT("fx-red-misinfo")}`]: { file: "result_fx-red-misinfo.json" } },
    waitFor: "判讀摘要",
  },
  {
    screen: "S2 結果頁", n: 2, state: "cache_vector", route: "/r/fx-green-cache-vector", widths: [375, 1280],
    api: { [`GET ${RESULT("fx-green-cache-vector")}`]: { file: "result_fx-green-cache-vector.json" } },
    waitFor: "判讀摘要",
  },
  {
    screen: "S2 結果頁", n: 2, state: "unverified_red", route: "/r/fx-red-unverified-scam", widths: [375, 1280],
    api: { [`GET ${RESULT("fx-red-unverified-scam")}`]: { file: "result_fx-red-unverified-scam.json" } },
    waitFor: "尚無查核機構證實",
  },
  {
    screen: "S2 結果頁", n: 2, state: "unverifiable", route: "/r/fx-unverifiable", widths: [1280],
    api: { [`GET ${RESULT("fx-unverifiable")}`]: { file: "result_fx-unverifiable.json" } },
    waitFor: "判讀摘要",
  },
  {
    screen: "S2 結果頁", n: 2, state: "shared", route: "/r/fx-red-misinfo", widths: [375, 1280],
    api: { [`GET ${RESULT("fx-red-misinfo")}`]: { file: "result_fx-red-misinfo.json" } },
    actions: [{ click: "分享到 Threads" }, { wait: 1.0 }],
    waitFor: "已開啟 Threads",
  },
  {
    screen: "S2 結果頁", n: 2, state: "shared-viewport", route: "/r/fx-red-misinfo", widths: [375],
    fullPage: false,
    api: { [`GET ${RESULT("fx-red-misinfo")}`]: { file: "result_fx-red-misinfo.json" } },
    actions: [{ scrollBottom: true }, { click: "分享到 Threads" }, { wait: 1.0 }],
    waitFor: "已開啟 Threads",
  },

  // ── S3 熱門牆 ──────────────────────────────────────────────────────────────
  {
    screen: "S3 熱門牆", n: 3, state: "success", route: "/trending", widths: [375, 1280],
    waitFor: "今日熱門查核",
  },
  {
    screen: "S3 熱門牆", n: 3, state: "loading", route: "/trending", widths: [375, 1280],
    api: { "GET /api/trending": { file: "trending_ok.json", delay: 8 } },
    actions: [{ wait: 1.6 }],
  },
  {
    screen: "S3 熱門牆", n: 3, state: "empty", route: "/trending", widths: [375, 1280],
    api: { "GET /api/trending": { file: "trending_empty.json" } },
    waitFor: "還沒有熱門查核資料",
  },
  {
    screen: "S3 熱門牆", n: 3, state: "error", route: "/trending", widths: [375, 1280],
    api: { "GET /api/trending": { fail: true }, "GET /api/health": { fail: true } },
    waitFor: "暫時連不上伺服器",
  },
  {
    screen: "S3 熱門牆", n: 3, state: "pending_chip", route: "/trending", widths: [375, 1280],
    waitFor: "未查證",
  },
  {
    screen: "S3 熱門牆", n: 3, state: "filter_empty", route: "/trending", widths: [375, 1280],
    api: { "GET /api/trending": { file: "trending_ok_all_verified.json" } },
    actions: [{ click: "未查證" }, { wait: 1.0 }],
    waitFor: "這個分類目前沒有資料",
  },

  // ── S4 知識庫 ──────────────────────────────────────────────────────────────
  {
    screen: "S4 知識庫", n: 4, state: "success", route: "/knowledge", widths: [375, 1280],
    waitFor: "查證知識庫",
  },
  {
    screen: "S4 知識庫", n: 4, state: "loading", route: "/knowledge", widths: [375, 1280],
    api: { "GET /api/knowledge": { file: "knowledge_page1.json", delay: 8 } },
    actions: [{ wait: 1.6 }],
  },
  {
    screen: "S4 知識庫", n: 4, state: "empty", route: "/knowledge", widths: [375, 1280],
    api: { "GET /api/knowledge": { file: "knowledge_empty.json" } },
    waitFor: "知識庫是空的",
  },
  {
    screen: "S4 知識庫", n: 4, state: "error", route: "/knowledge", widths: [375, 1280],
    api: { "GET /api/knowledge": { fail: true }, "GET /api/health": { fail: true } },
    waitFor: "暫時連不上伺服器",
  },
  {
    screen: "S4 知識庫", n: 4, state: "no_match", route: "/knowledge", widths: [375, 1280],
    api: { "GET /api/knowledge": { file: "knowledge_empty.json" } },
    actions: [{ type: { placeholder: "搜尋關鍵字", text: "zzzz" } }, { key: "Enter" }, { wait: 1.2 }],
    waitFor: "找不到符合",
  },
  {
    screen: "S4 知識庫", n: 4, state: "filter_unverifiable", route: "/knowledge", widths: [375, 1280],
    actions: [{ click: "無法查證" }, { wait: 1.2 }],
    waitFor: "查證知識庫",
  },
];

/* ─────────────────────────────── CDP plumbing ────────────────────────────── */
const EDGE = [
  "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
  "C:/Program Files/Microsoft/Edge/Application/msedge.exe",
].find((p) => fs.existsSync(p));

async function connect(url) {
  const ws = new WebSocket(url);
  await new Promise((res, rej) => {
    ws.addEventListener("open", res, { once: true });
    ws.addEventListener("error", rej, { once: true });
  });
  let id = 1;
  const pending = new Map();
  const handlers = new Map();
  ws.addEventListener("message", (ev) => {
    const m = JSON.parse(ev.data);
    if (m.id !== undefined) {
      const p = pending.get(m.id);
      if (!p) return;
      pending.delete(m.id);
      m.error ? p.rej(new Error(`${p.method}: ${m.error.message}`)) : p.res(m.result);
    } else {
      for (const fn of handlers.get(m.method) ?? []) fn(m.params, m.sessionId);
    }
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
    on(method, fn) {
      if (!handlers.has(method)) handlers.set(method, new Set());
      handlers.get(method).add(fn);
    },
  };
}

async function launch() {
  const profile = fs.mkdtempSync(path.join(os.tmpdir(), "fnv-ui-"));
  const proc = spawn(EDGE, [
    "--headless=new", `--remote-debugging-port=${PORT}`, `--user-data-dir=${profile}`,
    "--window-size=1400,1000", "--hide-scrollbars", "--force-device-scale-factor=1",
    "--disable-gpu", "--no-first-run", "--no-default-browser-check", "--disable-extensions",
    "--disable-background-networking", "--mute-audio", "about:blank",
  ], { stdio: "ignore" });
  let ver = null;
  for (let i = 0; i < 80 && !ver; i++) {
    try {
      const r = await fetch(`http://127.0.0.1:${PORT}/json/version`);
      if (r.ok) ver = await r.json();
    } catch { /* not up yet */ }
    if (!ver) await sleep(250);
  }
  if (!ver) throw new Error("Edge devtools endpoint never came up");
  const c = await connect(ver.webSocketDebuggerUrl);
  const { targetId } = await c.send("Target.createTarget", { url: "about:blank" });
  const { sessionId } = await c.send("Target.attachToTarget", { targetId, flatten: true });
  return {
    c, sessionId,
    close: async () => {
      try { await c.send("Browser.close"); } catch { /* gone */ }
      c.ws.close(); proc.kill(); await sleep(500);
      try { fs.rmSync(profile, { recursive: true, force: true }); } catch { /* TEMP keeps it */ }
    },
  };
}

/* ───────────────────────────────── capture ───────────────────────────────── */
const PAGE_HELPERS = `
  window.__ui = {
    find(spec) {
      const q = typeof spec === "string" ? { text: spec } : spec;
      const vis = (el) => { const r = el.getBoundingClientRect();
        return r.width > 0 && r.height > 0 && getComputedStyle(el).visibility !== "hidden"; };
      if (q.placeholder) return [...document.querySelectorAll("input,textarea")]
        .find((el) => (el.placeholder || "").includes(q.placeholder) && vis(el)) || null;
      const pool = [...document.querySelectorAll("button,a,[role=tab],label,summary,span,p,div,h1,h2,li")];
      const hit = pool.filter((el) => vis(el) &&
        (el.innerText || "").replace(/\\s+/g, " ").trim().includes(q.text));
      const deepest = hit.filter((el) => !hit.some((o) => o !== el && el.contains(o)));
      return deepest[0] || hit[0] || null;
    },
    has(text) { return !!window.__ui.find(text); },
    fill(text) {
      const el = document.querySelector("textarea[aria-label], textarea");
      if (!el) return false;
      el.focus();
      Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value").set.call(el, text);
      el.dispatchEvent(new Event("input", { bubbles: true }));
      return true;
    },
    typeInto(placeholder, text) {
      const el = window.__ui.find({ placeholder });
      if (!el) return false;
      el.focus();
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set.call(el, text);
      el.dispatchEvent(new Event("input", { bubbles: true }));
      return true;
    },
    click(text) { const el = window.__ui.find(text); if (el) el.click(); return !!el; },
  };
`;

async function main() {
  if (!EDGE) throw new Error("Microsoft Edge not found");
  fs.mkdirSync(OUT, { recursive: true });
  const shots = SHOTS.filter((s) => !ONLY.length || ONLY.includes(`S${s.n}`));
  const s = await launch();
  const { c, sessionId } = s;
  const send = (m, p) => c.send(m, p, sessionId);
  const ev = async (expr) => {
    const r = await send("Runtime.evaluate", { expression: expr, returnByValue: true, awaitPromise: true, userGesture: true });
    if (r.exceptionDetails) throw new Error(r.exceptionDetails.text);
    return r.result.value;
  };

  await send("Page.enable");
  await send("Runtime.enable");
  await send("Fetch.enable", { patterns: [{ urlPattern: "*/api/*" }] });
  await send("Emulation.setEmulatedMedia", { media: "screen", features: [{ name: "prefers-color-scheme", value: THEME }] });
  await send("Page.addScriptToEvaluateOnNewDocument", {
    source: `try { localStorage.setItem("fcc_theme", ${JSON.stringify(THEME)}); } catch (e) {}\n${PAGE_HELPERS}`,
  });

  // The API table for the shot currently being taken.
  let table = {};
  const used = new Set();
  c.on("Fetch.requestPaused", async (p) => {
    const u = new URL(p.request.url);
    const key = `${p.request.method} ${u.pathname}`;
    const rule = Object.entries(table).find(([k]) => {
      const [m, prefix] = k.split(" ");
      return m === p.request.method && u.pathname.startsWith(prefix);
    })?.[1];
    try {
      if (!rule) { await send("Fetch.failRequest", { requestId: p.requestId, errorReason: "Failed" }); return; }
      if (rule.delay) await sleep(rule.delay * 1000);
      if (rule.fail) {
        used.add(`${key} → 連線失敗`);
        await send("Fetch.failRequest", { requestId: p.requestId, errorReason: "ConnectionRefused" });
        return;
      }
      const data = rule.file ? fixture(rule.file) : rule.body ?? {};
      const { _status, _headers, ...body } = data;
      used.add(`${key} → ${rule.file ?? "inline"}`);
      await send("Fetch.fulfillRequest", {
        requestId: p.requestId,
        responseCode: rule.status ?? (Number.isInteger(_status) ? _status : 200),
        responseHeaders: Object.entries({ "content-type": "application/json", ..._headers })
          .map(([name, value]) => ({ name, value: String(value) })),
        body: Buffer.from(JSON.stringify(body), "utf8").toString("base64"),
      });
    } catch { /* the page navigated away mid-flight */ }
  });

  const log = [];
  for (const shot of shots) {
    for (const width of shot.widths) {
      const name = `S${shot.n}_${shot.state}_${width}_${THEME}.png`;
      const height = width <= 400 ? 812 : 900;
      table = { "GET /api/health": { file: "health_ok.json" },
                "GET /api/trending": { file: "trending_ok.json" },
                "GET /api/knowledge/stats": { file: "knowledge_stats.json" },
                "GET /api/knowledge": { file: "knowledge_page1.json" },
                ...(shot.api ?? {}) };
      used.clear();

      await send("Emulation.setDeviceMetricsOverride", {
        width, height, deviceScaleFactor: 1, mobile: width <= 400,
        screenWidth: width, screenHeight: height,
      });
      await send("Page.navigate", { url: BASE + shot.route });
      for (let i = 0; i < 60; i++) {
        if (await ev("document.readyState").catch(() => null) === "complete") break;
        await sleep(150);
      }
      await sleep(700);

      for (const a of shot.actions ?? []) {
        if (a.wait) await sleep(a.wait * 1000);
        if (a.fill) await ev(`window.__ui.fill(${JSON.stringify(a.fill)})`);
        if (a.type) await ev(`window.__ui.typeInto(${JSON.stringify(a.type.placeholder)}, ${JSON.stringify(a.type.text)})`);
        if (a.click) await ev(`window.__ui.click(${JSON.stringify(a.click)})`);
        if (a.scrollBottom) await ev(`window.scrollTo(0, document.body.scrollHeight)`);
        if (a.key === "Enter") {
          for (const type of ["keyDown", "keyUp"]) {
            await send("Input.dispatchKeyEvent", { type, key: "Enter", code: "Enter", windowsVirtualKeyCode: 13, text: type === "keyDown" ? "\r" : undefined });
          }
        }
        await sleep(250);
      }

      let ok = true;
      if (shot.waitFor) {
        ok = false;
        for (let i = 0; i < 80; i++) {
          if (await ev(`window.__ui.has(${JSON.stringify(shot.waitFor)})`).catch(() => false)) { ok = true; break; }
          await sleep(250);
        }
      }
      await sleep(500);

      const opts = { format: "png" };
      if (shot.fullPage !== false) {
        const { cssContentSize } = await send("Page.getLayoutMetrics");
        opts.captureBeyondViewport = true;
        opts.clip = { x: 0, y: 0, width, height: Math.ceil(cssContentSize.height), scale: 1 };
      }
      const png = await send("Page.captureScreenshot", opts);
      fs.writeFileSync(path.join(OUT, name), Buffer.from(png.data, "base64"));

      const entry = { file: `docs/test/screens/${name}`, screen: shot.screen, state: shot.state,
                      width: String(width), theme: THEME, route: shot.route,
                      api: [...used].sort(), actions: (shot.actions ?? []).map((a) => Object.keys(a)[0]),
                      waited_for: shot.waitFor ?? null, reached: ok };
      log.push(entry);
      console.log(`${ok ? "ok  " : "MISS"}  ${name}${ok ? "" : `   (never saw ${JSON.stringify(shot.waitFor)})`}`);
    }
  }

  // Merge, don't overwrite: a --only re-run of one screen must not drop the other screens' records.
  const logFile = path.join(OUT, `shots_${THEME}.json`);
  const previous = fs.existsSync(logFile) ? JSON.parse(fs.readFileSync(logFile, "utf8")) : [];
  const merged = [...previous.filter((p) => !log.some((n) => n.file === p.file)), ...log]
    .sort((a, b) => a.file.localeCompare(b.file));
  fs.writeFileSync(logFile, JSON.stringify(merged, null, 1) + "\n", "utf8");
  await s.close();
  const missed = log.filter((x) => !x.reached);
  console.log(`\n${log.length} shots -> ${OUT}`);
  if (missed.length) {
    console.log(`${missed.length} did not reach their expected state:`);
    for (const m of missed) console.log(`  ${path.basename(m.file)}  waited for ${JSON.stringify(m.waited_for)}`);
    process.exit(1);
  }
}

main().catch((e) => { console.error(e); process.exit(1); });
