// Minimal Chrome DevTools Protocol client for the capture script.
//
// Local only: launches headless Microsoft Edge with a throwaway profile, no sign-in, no telemetry.
// `ws` resolves from video/node_modules (the Remotion project's dependency tree).
import { spawn } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import WebSocket from "ws";

const EDGE_CANDIDATES = [
  "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
  "C:/Program Files/Microsoft/Edge/Application/msedge.exe",
];

export function edgeBin() {
  const found = EDGE_CANDIDATES.find((p) => fs.existsSync(p));
  if (!found) throw new Error("Microsoft Edge not found");
  return found;
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function fetchJson(url, tries = 60) {
  for (let i = 0; i < tries; i++) {
    try {
      const r = await fetch(url);
      if (r.ok) return await r.json();
    } catch {
      /* not listening yet */
    }
    await sleep(250);
  }
  throw new Error(`devtools endpoint never came up: ${url}`);
}

/** Launch headless Edge and attach to its first page target. */
export async function launch({ port = 9333, width = 1920, height = 1080, dsf = 1 } = {}) {
  const profile = fs.mkdtempSync(path.join(os.tmpdir(), "fnv-capture-"));
  const proc = spawn(edgeBin(), [
    "--headless=new",
    `--remote-debugging-port=${port}`,
    `--user-data-dir=${profile}`,
    `--window-size=${width},${height}`,
    "--hide-scrollbars",
    // The screencast surface follows the BROWSER's device scale factor, not the one passed to
    // Emulation.setDeviceMetricsOverride. Without this flag a 1.5x emulated page is still sent
    // as 1280x720 frames. Both must be set, and the flag is fixed for the life of the process,
    // so a take is recorded in its own browser.
    `--force-device-scale-factor=${dsf}`,
    "--disable-gpu",
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-sync",
    "--disable-features=Translate,MediaRouter,OptimizationHints,msEdgeIdentityFeatures",
    "--disable-extensions",
    "--disable-background-networking",
    "--metrics-recording-only",
    "--mute-audio",
    "--font-render-hinting=none",
    "about:blank",
  ], { stdio: "ignore" });

  const version = await fetchJson(`http://127.0.0.1:${port}/json/version`);
  const browser = await connect(version.webSocketDebuggerUrl);
  const { targetId } = await browser.send("Target.createTarget", { url: "about:blank" });
  const { sessionId } = await browser.send("Target.attachToTarget", { targetId, flatten: true });
  const page = sessionWrapper(browser, sessionId);
  return {
    page,
    browser,
    userAgentBrand: version["User-Agent"],
    async close() {
      try { await browser.send("Browser.close"); } catch { /* already gone */ }
      browser.ws.close();
      proc.kill();
      await sleep(800);
      // Edge can still hold the throwaway profile for a moment; it lives in TEMP either way.
      try { fs.rmSync(profile, { recursive: true, force: true }); } catch { /* leave it to TEMP */ }
    },
  };
}

function connect(url) {
  return new Promise((resolve, reject) => {
    const ws = new WebSocket(url, { perMessageDeflate: false, maxPayload: 256 * 1024 * 1024 });
    let nextId = 1;
    const pending = new Map();
    const listeners = new Map();
    const api = {
      ws,
      send(method, params = {}, sessionId) {
        const id = nextId++;
        const msg = { id, method, params };
        if (sessionId) msg.sessionId = sessionId;
        return new Promise((res, rej) => {
          pending.set(id, { res, rej, method });
          ws.send(JSON.stringify(msg));
        });
      },
      on(event, fn, sessionId) {
        const key = `${sessionId ?? ""}:${event}`;
        if (!listeners.has(key)) listeners.set(key, new Set());
        listeners.get(key).add(fn);
        return () => listeners.get(key).delete(fn);
      },
    };
    ws.on("open", () => resolve(api));
    ws.on("error", reject);
    ws.on("message", (raw) => {
      const msg = JSON.parse(raw.toString());
      if (msg.id !== undefined) {
        const p = pending.get(msg.id);
        if (!p) return;
        pending.delete(msg.id);
        if (msg.error) p.rej(new Error(`${p.method}: ${msg.error.message}`));
        else p.res(msg.result);
        return;
      }
      const key = `${msg.sessionId ?? ""}:${msg.method}`;
      for (const fn of listeners.get(key) ?? []) fn(msg.params);
    });
  });
}

function sessionWrapper(browser, sessionId) {
  return {
    sessionId,
    send: (method, params) => browser.send(method, params, sessionId),
    on: (event, fn) => browser.on(event, fn, sessionId),
  };
}

export { sleep };
