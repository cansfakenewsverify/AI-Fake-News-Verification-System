// Assembles presentation_v1.3 from data/plan.json (edit decision list) + data/timing.json (real narration timings).
// v1.3 (2026-10-28) changes only the sound and the captions: a Mixkit music bed ducked under the narration, Mixkit
// effects instead of the synthesised ones, captions at 54 px (5 % of the frame height) -- the same choices as the
// scenario film (video/hf-scenario), from the video-shotcraft skill's sound-design and aesthetic notes.
//
// Usage (from video/hf-demo):  node tools/build_timeline.mjs
// Writes:
//   index.html                      thin orchestrator: scene hosts, chrome, caption track, narration clips,
//                                   scene-to-scene transitions on the root timeline
//   compositions/captions.html      the single caption track (one group per narration cue)
//   ../../docs/demo/presentation_v1.3.srt the same cues as a sidecar subtitle file
//   data/schedule.json              where every shot / scene / cue lands on the film clock (reference)
//   compositions/chrome.html        persistent brand + progress rule (durations follow the plan)
// Scene files (compositions/sNN-*.html) are hand-authored; their root
// data-duration must equal the scene length + plan.overlap (this script checks it).
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const plan = JSON.parse(fs.readFileSync(path.join(ROOT, "data", "plan.json"), "utf8"));
const timing = JSON.parse(fs.readFileSync(path.join(ROOT, "data", "timing.json"), "utf8"));
const readOpt = (f, fallback) => (fs.existsSync(f) ? JSON.parse(fs.readFileSync(f, "utf8")) : fallback);
const sfx = readOpt(path.join(ROOT, "data", "sfx.json"), { events: [], gain: {} });
const mixLen = readOpt(path.join(ROOT, "data", "mixkit_lengths.json"), {});
const r3 = (n) => Math.round(n * 1000) / 1000;
const T = plan.transition;
const OVERLAP = plan.overlap;

// ── schedule ────────────────────────────────────────────────────────────────
const shots = {};
let clock = 0;
for (const n of Object.keys(plan.shots).map(Number).sort((a, b) => a - b)) {
  const s = plan.shots[n];
  const t = timing[n];
  if (s.audio + t.speech_end > s.dur - 0.3) throw new Error(`shot ${n}: narration (${t.speech_end}s @${s.audio}) does not fit ${s.dur}s`);
  shots[n] = { start: r3(clock), dur: s.dur, audioStart: r3(clock + s.audio), clip: t.clip, cues: t.cues };
  clock += s.dur;
}
const TOTAL = r3(clock);
const scenes = plan.scenes.map((sc, i) => {
  const start = shots[sc.shots[0]].start;
  const len = r3(sc.shots.reduce((a, n) => a + shots[n].dur, 0));
  const last = i === plan.scenes.length - 1;
  return { ...sc, start, len, hostDur: r3(last ? len : len + OVERLAP) };
});

const cues = [];
for (const [n, s] of Object.entries(shots)) {
  for (const c of s.cues) cues.push({ shot: Number(n), text: c.text, start: r3(s.audioStart + c.start), end: r3(s.audioStart + c.end) });
}
cues.forEach((c, i) => {
  const next = cues[i + 1];
  c.in = r3(Math.max(0, c.start - 0.06));
  c.out = r3(Math.min(c.end + 0.22, next ? next.start - 0.1 : TOTAL - 0.05));
});

// ── sanity: scene files carry the matching duration ─────────────────────────
for (const sc of scenes) {
  const f = path.join(ROOT, "compositions", `${sc.id}.html`);
  if (!fs.existsSync(f)) { console.warn(`! missing ${path.relative(ROOT, f)}`); continue; }
  const m = fs.readFileSync(f, "utf8").match(/id="root"[^>]*data-duration="([\d.]+)"/);
  if (!m || Math.abs(Number(m[1]) - sc.hostDur) > 1e-6) console.warn(`! ${sc.id}: root data-duration=${m?.[1]} but the host window is ${sc.hostDur}`);
}

// ── index.html ──────────────────────────────────────────────────────────────
const esc = (s) => s.replace(/&/g, "&amp;").replace(/"/g, "&quot;");
const host = (id, start, dur, track, kind) => `      <div
        id="el-${id}"
        class="clip"
        data-composition-id="${id}"
        data-composition-src="compositions/${id}.html"
        data-start="${start}"
        data-duration="${dur}"
        data-track-index="${track}"
        data-track-kind="${kind}"
        data-width="1920"
        data-height="1080"
      ></div>`;
const fade = (clip) => esc(JSON.stringify({ version: 1, lanes: [{ target: "volume", points: [{ t: 0, v: 0 }, { t: 0.06, v: 1 }, { t: r3(clip - 0.22), v: 1 }, { t: r3(clip), v: 0 }] }] }));
const audio = Object.entries(shots).map(([n, s]) => `      <audio
        id="vo-${String(n).padStart(2, "0")}"
        src="assets/audio/shot${String(n).padStart(2, "0")}.wav"
        data-start="${s.audioStart}"
        data-duration="${s.clip}"
        data-track-index="20"
        data-volume="1"
        data-automation="${fade(s.clip)}"
      ></audio>`);

// sound effects: one track per kind so the Studio timeline stays readable (a second one, +10, for quick repeats).
// The event names come from tools/build_sfx.mjs; the files are Mixkit recordings (tools/mixkit.py, peak -1 dBFS).
const SOUND = {
  click: { file: "click", track: 21 },
  tick: { file: "click", track: 22 },
  chime: { file: "verdict", track: 23 },
  whoosh: { file: "whoosh", track: 24 },
};
const busyUntil = {};
const sfxEls = sfx.events.map((e, i) => {
  const snd = SOUND[e.sound];
  if (!snd || !mixLen[snd.file]) throw new Error(`sound ${e.sound}: run tools/mixkit.py`);
  const track = (busyUntil[snd.track] ?? -1) > e.t ? snd.track + 10 : snd.track;
  const len = r3(Math.min(mixLen[snd.file], TOTAL - e.t));
  busyUntil[track] = e.t + len;
  return `      <audio
        id="sfx-${String(i).padStart(3, "0")}"
        src="assets/audio/mixkit/${snd.file}.wav"
        data-start="${e.t}"
        data-duration="${len}"
        data-track-index="${track}"
        data-volume="${sfx.gain[e.sound] ?? 0.4}"
      ></audio>`;
});

// music bed: one Mixkit track, restarted at a scene change whenever it would run out, sitting at GAP between
// narration cues and dipping to UNDER 0.35 s before each cue, back up 0.7 s after it (cues closer than that
// stay ducked). Fades in at the start, out over the end card.
const MUSIC = { file: "bgm", gap: 0.45, under: 0.14, fadeIn: 1.2, fadeOut: 3.0 };
const bgmLen = mixLen[MUSIC.file];
if (!bgmLen) throw new Error("music missing: run tools/mixkit.py");
const spoken = [];
for (const c of cues) {
  const g = spoken.at(-1);
  if (g && c.start - 0.35 < g[1] + 0.7) g[1] = Math.max(g[1], c.end);
  else spoken.push([c.start, c.end]);
}
const duck = spoken.flatMap(([a, b]) => [[a - 0.35, MUSIC.gap], [a - 0.05, MUSIC.under], [b + 0.1, MUSIC.under], [b + 0.7, MUSIC.gap]]);
const lerp = (pts, t, outside) => {
  if (!pts.length || t <= pts[0][0]) return pts.length ? pts[0][1] : outside;
  for (let i = 1; i < pts.length; i++) if (t <= pts[i][0]) return pts[i - 1][1] + ((pts[i][1] - pts[i - 1][1]) * (t - pts[i - 1][0])) / (pts[i][0] - pts[i - 1][0]);
  return pts.at(-1)[1];
};
const bounds = [0];
while (TOTAL - bounds.at(-1) > bgmLen - 0.5) {
  const from = bounds.at(-1);
  const next = scenes.map((sc) => sc.start).filter((t) => t > from + 20 && t <= from + bgmLen - 0.5).at(-1);
  if (next === undefined) throw new Error(`music: no scene change to restart on between ${from}s and ${r3(from + bgmLen)}s`);
  bounds.push(next);
}
bounds.push(TOTAL);
const music = bounds.slice(0, -1).map((a, k) => {
  const b = bounds[k + 1];
  const last = k === bounds.length - 2;
  const env = [[a, 0], [a + (k === 0 ? MUSIC.fadeIn : 0.3), 1], [b - (last ? MUSIC.fadeOut : 0.4), 1], [b, 0]];
  const ts = [...new Set([...env.map((p) => p[0]), ...duck.map((p) => p[0]).filter((t) => t > a && t < b)].map(r3))].sort((x, y) => x - y);
  const points = ts.map((t) => ({ t: r3(t - a), v: r3(lerp(duck, t, MUSIC.gap) * lerp(env, t, 0)) }));
  return `      <audio
        id="bgm-${k}"
        src="assets/audio/mixkit/${MUSIC.file}.wav"
        data-start="${r3(a)}"
        data-duration="${r3(b - a)}"
        data-track-index="${40 + (k % 2)}"
        data-volume="1"
        data-automation="${esc(JSON.stringify({ version: 1, lanes: [{ target: "volume", points }] }))}"
      ></audio>`;
});

const trans = [];
scenes.forEach((sc, i) => {
  if (i === 0) return;
  const prev = `#el-${scenes[i - 1].id}`;
  const cur = `#el-${sc.id}`;
  const at = sc.start;
  if (sc.in === "push") {
    trans.push(`      // ${at}s push slide → ${sc.id}
      tl.to("${prev}", { x: -1920, duration: ${T}, ease: "power3.inOut" }, ${at});
      tl.fromTo("${cur}", { x: 1920 }, { x: 0, duration: ${T}, ease: "power3.inOut" }, ${at});`);
  } else if (sc.in === "push-up") {
    trans.push(`      // ${at}s vertical push → ${sc.id}
      tl.to("${prev}", { y: -1080, duration: ${T}, ease: "power3.inOut" }, ${at});
      tl.fromTo("${cur}", { y: 1080 }, { y: 0, duration: ${T}, ease: "power3.inOut" }, ${at});`);
  } else if (sc.in === "blur") {
    trans.push(`      // ${at}s blur crossfade → ${sc.id}
      tl.to("${prev}", { filter: "blur(10px)", scale: 1.03, opacity: 0, duration: ${T}, ease: "power2.inOut" }, ${at});
      tl.fromTo("${cur}", { filter: "blur(10px)", scale: 0.97, opacity: 0 }, { filter: "blur(0px)", scale: 1, opacity: 1, duration: ${T}, ease: "power2.inOut" }, ${r3(at + 0.1)});`);
  }
});

const filmCss = fs
  .readFileSync(path.join(ROOT, "assets", "film.css"), "utf8")
  .trimEnd()
  .split(/\r?\n/)
  .map((l) => (l ? "      " + l : l))
  .join("\n");
const index = `<!doctype html>
<!-- GENERATED by tools/build_timeline.mjs from data/plan.json + data/timing.json. Edit those, not this file. -->
<html lang="zh-Hant" data-resolution="landscape">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=1920, height=1080" />
    <title>全民查證公社 簡報影片 presentation v1.3</title>
    <script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
    <style>
      /* ── assets/film.css, inlined by tools/build_timeline.mjs: the render compiler only embeds fonts
            (JetBrains Mono) for font-family declarations it can see in the HTML itself ── */
${filmCss}
      /* ── root layout ── */
      html,
      body {
        margin: 0;
        background: #f7f7f8;
      }
      #root {
        position: relative;
        width: 100%;
        height: 100%;
        overflow: hidden;
        background: #f7f7f8;
      }
      #root > div[data-composition-src] {
        position: absolute;
        inset: 0;
      }
    </style>
  </head>
  <body>
    <div id="root" data-composition-id="main" data-start="0" data-width="1920" data-height="1080" data-duration="${TOTAL}" data-fps="${plan.fps}">
      <!-- scenes (track 1): one sub-composition per continuous stage; windows overlap by ${OVERLAP}s for the handoff -->
${scenes.map((sc) => host(sc.id, sc.start, sc.hostDur, 1, "graphics")).join("\n")}

      <!-- persistent chrome (track 5) and the single caption track (track 6) -->
${host("chrome", 0, TOTAL, 5, "graphics")}
${host("captions", 0, TOTAL, 6, "captions")}

      <!-- narration (track 20): edge-tts (voice and rate in data/narration.json), one clip per shot, gentle fades -->
${audio.join("\n")}

      <!-- sound effects (tracks 21-24, 31-34 for quick repeats): Mixkit via tools/mixkit.py, placed by tools/build_sfx.mjs -->
${sfxEls.join("\n")}

      <!-- music bed (tracks 40-41): Mixkit via tools/mixkit.py, ducked under the narration -->
${music.join("\n")}
    </div>
    <script>
      const tl = gsap.timeline({ paused: true });
${trans.join("\n")}
      window.__timelines["main"] = tl;
    </script>
  </body>
</html>
`;
fs.writeFileSync(path.join(ROOT, "index.html"), index, "utf8");

// ── compositions/captions.html ──────────────────────────────────────────────
const groups = cues.map((c, i) => `        <div class="cap-g" id="cap-${i}"><span class="cap-t">${c.text.replace(/&/g, "&amp;").replace(/</g, "&lt;")}</span></div>`);
const captions = `<!doctype html>
<!-- GENERATED by tools/build_timeline.mjs. One caption group per narration cue; one group visible at a time;
     every group gets a hard kill at its end (media-use → captions/authoring.md). -->
<html lang="zh-Hant">
  <head>
    <meta charset="UTF-8" />
  </head>
  <body>
    <template>
      <style>
        #root {
          position: absolute;
          inset: 0;
          pointer-events: none;
        }
        .cap-g {
          position: absolute;
          left: 0;
          top: 806px;
          width: 1920px;
          height: 170px;
          display: flex;
          align-items: flex-end;
          justify-content: center;
          opacity: 0;
        }
        .cap-t {
          display: block;
          max-width: 1640px;
          padding: 12px 36px 14px;
          border-radius: 20px;
          background: #161616;
          color: #ffffff;
          font-size: 54px;
          line-height: 68px;
          font-weight: 700;
          letter-spacing: 0.01em;
          text-align: center;
          white-space: normal;
          text-wrap: balance;
        }
      </style>
      <div id="root" class="fnv-root" data-composition-id="captions" data-width="1920" data-height="1080" data-duration="${TOTAL}" data-layout-allow-overlap>
${groups.join("\n")}
      </div>
      <script>
        (function () {
          const root = document.querySelector('[data-composition-id="captions"]');
          const tl = gsap.timeline({ paused: true });
          const CUES = ${JSON.stringify(cues.map((c) => [c.in, c.out]))};
          CUES.forEach(([t0, t1], i) => {
            const el = root.querySelector("#cap-" + i);
            tl.fromTo(el, { opacity: 0, y: 14 }, { opacity: 1, y: 0, duration: 0.2, ease: "power3.out" }, t0);
            tl.to(el, { opacity: 0, duration: 0.12, ease: "power2.in" }, t1 - 0.12);
            tl.set(el, { opacity: 0, visibility: "hidden" }, t1);
          });
          window.__timelines["captions"] = tl;
        })();
      </script>
    </template>
  </body>
</html>
`;
fs.writeFileSync(path.join(ROOT, "compositions", "captions.html"), captions, "utf8");

// ── compositions/chrome.html ────────────────────────────────────────────────
const chrome = `<!doctype html>
<!-- GENERATED by tools/build_timeline.mjs (durations follow data/plan.json). -->
<!--
  chrome — persistent film furniture over every scene: brand word-mark (top-left, from scene 2 until the
  end card takes over) and a progress rule along the bottom edge that runs for the whole film.
  frame.md → components.chrome. Spans the whole film.
-->
<html lang="zh-Hant">
  <head>
    <meta charset="UTF-8" />
  </head>
  <body>
    <template>
      <style>
        #root {
          position: absolute;
          inset: 0;
          pointer-events: none;
        }
        .chr-brand {
          position: absolute;
          left: 96px;
          top: 22px;
          display: flex;
          align-items: baseline;
          column-gap: 16px;
          white-space: nowrap;
        }
        .chr-name {
          font-size: 26px;
          line-height: 36px;
          font-weight: 700;
          letter-spacing: 0.04em;
        }
        .chr-sub {
          font-size: 19px;
          line-height: 36px;
          font-weight: 700;
          letter-spacing: 0.08em;
          color: #5b5b66;
        }
        .chr-track {
          position: absolute;
          left: 0;
          bottom: 0;
          width: 1920px;
          height: 6px;
          background: #d4d4d8;
        }
        .chr-fill {
          position: absolute;
          left: 0;
          bottom: 0;
          width: 1920px;
          height: 6px;
          background: #111111;
          transform-origin: left center;
        }
      </style>
      <div id="root" class="fnv-root" data-composition-id="chrome" data-width="1920" data-height="1080" data-duration="${TOTAL}">
        <div class="chr-brand" id="chr-brand">
          <span class="chr-name">全民查證公社</span>
          <span class="chr-sub fnv-mono">fakenewsverify.vercel.app</span>
        </div>
        <div class="chr-track"></div>
        <div class="chr-fill" id="chr-fill"></div>
      </div>
      <script>
        (function () {
          const root = document.querySelector('[data-composition-id="chrome"]');
          const tl = gsap.timeline({ paused: true });
          const TOTAL = ${TOTAL};
          tl.fromTo(root.querySelector("#chr-fill"), { scaleX: 0 }, { scaleX: 1, duration: TOTAL, ease: "none" }, 0);
          // brand: hidden over the hook (scene 1) and the end card
          tl.fromTo(root.querySelector("#chr-brand"), { opacity: 0, y: -10 }, { opacity: 1, y: 0, duration: 0.5, ease: "power2.out" }, ${r3(scenes[1].start + 0.55)});
          tl.to(root.querySelector("#chr-brand"), { opacity: 0, duration: 0.4, ease: "power1.in" }, ${r3(scenes[scenes.length - 1].start - 0.2)});
          window.__timelines["chrome"] = tl;
        })();
      </script>
    </template>
  </body>
</html>
`;
fs.writeFileSync(path.join(ROOT, "compositions", "chrome.html"), chrome, "utf8");

// ── SRT ─────────────────────────────────────────────────────────────────────
const tc = (t) => {
  const ms = Math.round(t * 1000);
  const p = (n, w = 2) => String(n).padStart(w, "0");
  return `${p(Math.floor(ms / 3600000))}:${p(Math.floor(ms / 60000) % 60)}:${p(Math.floor(ms / 1000) % 60)},${p(ms % 1000, 3)}`;
};
const srt = cues.map((c, i) => `${i + 1}\n${tc(c.in)} --> ${tc(c.out)}\n${c.text}\n`).join("\n");
const srtPath = path.resolve(ROOT, "..", "..", "docs", "demo", "presentation_v1.3.srt");
fs.writeFileSync(srtPath, srt, "utf8");

fs.writeFileSync(path.join(ROOT, "data", "schedule.json"), JSON.stringify({ total: TOTAL, shots, scenes, cues }, null, 1) + "\n", "utf8");

console.log(`total ${TOTAL}s · ${scenes.length} scenes · ${cues.length} cues · ${sfx.events.length} sfx · music restarts at ${bounds.slice(1, -1).join("s, ")}s`);
for (const [n, s] of Object.entries(shots)) console.log(`shot ${String(n).padStart(2)}  ${String(s.start).padStart(7)} – ${String(r3(s.start + s.dur)).padStart(7)}  vo @${s.audioStart} (+${s.clip}s)`);
console.log(`wrote index.html, compositions/captions.html, compositions/chrome.html, data/schedule.json, ${path.relative(ROOT, srtPath)}`);
