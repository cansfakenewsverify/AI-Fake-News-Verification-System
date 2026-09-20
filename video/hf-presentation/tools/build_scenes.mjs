// Generates the footage scenes (compositions/sNN-*.html) from data/scenes.json.
//
// Usage (from video/hf-presentation):  node tools/build_scenes.mjs
//
// Every footage scene has the same anatomy, so it is described as data rather than hand-written
// seven times: one or more panels (a captured clip with a virtual camera moving inside it), the
// honesty tags that must stay on screen, ink rings drawn in capture pixels, and a right-hand rail
// whose lines land on real narration cues (read from data/timing.json, produced by tools/tts.py).
//
// Hand-authored scenes (the hook, the bot simulation, the architecture, the numbers, the end card)
// are NOT generated: they are their own drawings and live in compositions/ directly.
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const plan = JSON.parse(fs.readFileSync(path.join(ROOT, "data", "plan.json"), "utf8"));
const spec = JSON.parse(fs.readFileSync(path.join(ROOT, "data", "scenes.json"), "utf8"));
const timing = JSON.parse(fs.readFileSync(path.join(ROOT, "data", "timing.json"), "utf8"));
// Where each accelerated / held piece actually landed on its clip's clock, written by build_footage.mjs.
const fmap = JSON.parse(fs.readFileSync(path.join(ROOT, "data", "footage_map.json"), "utf8"));
const r3 = (n) => Math.round(n * 1000) / 1000;
const esc = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

// Panel geometry, matching assets/film.css.
const PANEL = { x: 96, y: 76, w: 1140, h: 800 };
const PHONE = { w: 380, h: 822 };

/** Where a narration cue lands on the scene clock. cue -1 = the shot start. */
function cueTime(shot, i) {
  const s = plan.shots[String(shot)];
  if (i == null || i < 0) return s.audio;
  const t = timing[String(shot)];
  if (!t || !t.cues[i]) throw new Error(`shot ${shot}: no cue ${i} (has ${t ? t.cues.length : 0})`);
  return r3(s.audio + t.cues[i].start);
}

function sceneHtml(sc) {
  const shot = sc.shot;
  const len = plan.shots[String(shot)].dur;
  const isLast = plan.scenes[plan.scenes.length - 1].id === sc.id;
  const hostDur = r3(isLast ? len : len + plan.overlap);
  const at = (a) => (typeof a === "number" ? a : cueTime(shot, a.cue) + (a.off ?? 0));

  const styles = [];
  const body = [];
  const tl = [];

  // ── panels ────────────────────────────────────────────────────────────────
  sc.panels.forEach((p, pi) => {
    const clip = plan.footage[p.clip];
    if (!clip) throw new Error(`${sc.id}: no footage clip "${p.clip}" in plan.json`);
    const id = `${sc.id}-p${pi}`;
    const phone = clip.kind === "phone";
    const inT = at(p.in ?? 0);
    const outT = p.out == null ? null : at(p.out);

    body.push(`        <div class="${phone ? "sc-phone" : "fnv-panel"}" id="${id}">
          <div class="fnv-cam" id="${id}-cam" data-layout-allow-overflow>
            <video
              id="${id}-v"
              src="assets/footage/${p.clip}.mp4"
              data-start="${r3(inT)}"
              data-duration="${clip.dur}"
              data-track-index="${pi}"
              muted
              playsinline
            ></video>${(p.rings ?? []).map((r, ri) => `
            <div class="fnv-ring${r.shape === "box" ? " fnv-ring-box" : ""}" id="${id}-r${ri}"
                 style="left:${r.box[0]}px;top:${r.box[1]}px;width:${r.box[2]}px;height:${r.box[3]}px"></div>`).join("")}
          </div>
        </div>`);

    if (phone) {
      // The capture is 780x1688; show it whole inside a plain rounded device frame.
      styles.push(`        #${id} { position:absolute; left:${p.x ?? 470}px; top:${p.y ?? 118}px;
          width:${PHONE.w}px; height:${PHONE.h}px; overflow:hidden; border-radius:36px; background:#ffffff;
          box-shadow: 0 0 0 3px #d4d4d8, 0 24px 60px rgba(17,17,17,.12); }
        #${id} .fnv-cam { width:780px; height:1688px; transform-origin:0 0; }
        #${id} .fnv-cam video { width:780px; height:1688px; }`);
      // Fit 780x1688 into 380x822 (scale 0.4870).
      const s0 = r3(PHONE.h / 1688);
      tl.push(`          tl.set($("#${id}-cam"), { x: ${r3((PHONE.w - 780 * s0) / 2)}, y: 0, scale: ${s0} });`);
    }

    // entrance / exit
    tl.push(`          tl.set($("#${id}"), { opacity: 0 }, 0);`);
    tl.push(`          tl.fromTo($("#${id}"), { opacity: 0, y: ${p.rise ?? 30} }, { opacity: 1, y: 0, duration: 0.55, ease: "power3.out" }, ${r3(inT)});`);
    if (outT != null) tl.push(`          tl.to($("#${id}"), { opacity: 0, y: -22, duration: 0.4, ease: "power2.in" }, ${r3(outT)});`);

    // virtual camera: each step eases the capture point (cx, cy) and scale inside the panel
    if (!phone && p.camera) {
      const camFn = `cam`;
      p.camera.forEach((k, ki) => {
        const [cx, cy, s] = k.to;
        const t = r3(at(k.at));
        if (ki === 0 && (k.dur ?? 0) === 0) tl.push(`          tl.set($("#${id}-cam"), ${camFn}(${cx}, ${cy}, ${s}), ${t});`);
        else tl.push(`          tl.to($("#${id}-cam"), { ...${camFn}(${cx}, ${cy}, ${s}), duration: ${k.dur ?? 3}, ease: "${k.ease ?? "power1.inOut"}" }, ${t});`);
      });
    }

    (p.rings ?? []).forEach((r, ri) => {
      tl.push(`          tl.fromTo($("#${id}-r${ri}"), { opacity: 0, scale: 1.08 }, { opacity: 1, scale: 1, duration: 0.35, ease: "power3.out", transformOrigin: "50% 50%" }, ${r3(at(r.in))});`);
      tl.push(`          tl.to($("#${id}-r${ri}"), { opacity: 0, duration: 0.3, ease: "power2.in" }, ${r3(at(r.out))});`);
    });
  });

  // ── speed labels, derived from the edit itself ────────────────────────────
  // Not hand-written: they come from data/footage_map.json, so a labelled stretch on screen is
  // exactly the stretch that was played faster. Adjacent labelled pieces are merged.
  const speed = [];
  sc.panels.forEach((p) => {
    const inT = at(p.in ?? 0);
    for (const piece of fmap[p.clip]?.pieces ?? []) {
      if (!piece.label) continue;
      const a = r3(inT + piece.t0);
      const b = r3(inT + piece.t1);
      const last = speed[speed.length - 1];
      if (last && last.text === piece.label && a - last.out < 0.35) last.out = b;
      else speed.push({ text: piece.label, in: a, out: b });
    }
  });
  speed.forEach((s, i) => {
    const id = `${sc.id}-sp${i}`;
    body.push(`        <div class="fnv-tag fnv-tag-ghost fnv-tag-speed" id="${id}">${esc(s.text)}</div>`);
    tl.push(`          tl.set($("#${id}"), { opacity: 0 }, 0);`);
    tl.push(`          tl.to($("#${id}"), { opacity: 1, duration: 0.2, ease: "none" }, ${s.in});`);
    tl.push(`          tl.to($("#${id}"), { opacity: 0, duration: 0.2, ease: "none" }, ${s.out});`);
  });

  // ── honesty tags ──────────────────────────────────────────────────────────
  (sc.tags ?? []).forEach((t, i) => {
    const id = `${sc.id}-t${i}`;
    body.push(`        <div class="fnv-tag ${t.ghost ? "fnv-tag-ghost " : ""}${t.slot === "speed" ? "fnv-tag-speed" : "fnv-tag-panel"}" id="${id}">${esc(t.text)}</div>`);
    tl.push(`          tl.set($("#${id}"), { opacity: 0 }, 0);`);
    tl.push(`          tl.to($("#${id}"), { opacity: 1, duration: 0.3, ease: "none" }, ${r3(at(t.in ?? 0.6))});`);
    if (t.out != null) tl.push(`          tl.to($("#${id}"), { opacity: 0, duration: 0.3, ease: "none" }, ${r3(at(t.out))});`);
  });

  // ── right-hand rail ───────────────────────────────────────────────────────
  if (sc.rail) {
    const rail = sc.rail;
    body.push(`        <div class="sc-col">
          <div class="fnv-eyebrow fnv-mono" id="${sc.id}-eyebrow">${esc(rail.eyebrow)}</div>
          <div class="sc-title" id="${sc.id}-title">${rail.title}</div>${rail.lede ? `
          <div class="sc-lede" id="${sc.id}-lede">${rail.lede}</div>` : ""}
          <div class="sc-rule" id="${sc.id}-rule"></div>
          <div class="sc-facts">
${(rail.facts ?? []).map((f, i) => `            <div class="sc-fact" id="${sc.id}-f${i}">
              <div class="sc-fact-n fnv-mono">${String(i + 1).padStart(2, "0")}</div>
              <div>
                <div class="sc-fact-h">${f.h}</div>${f.b ? `
                <div class="sc-fact-b">${f.b}</div>` : ""}
              </div>
            </div>`).join("\n")}
          </div>
        </div>`);
    tl.push(`          tl.fromTo($("#${sc.id}-eyebrow"), { opacity: 0 }, { opacity: 1, duration: 0.4, ease: "none" }, 0.3);`);
    tl.push(`          tl.fromTo($("#${sc.id}-title"), { opacity: 0, x: 40 }, { opacity: 1, x: 0, duration: 0.6, ease: "expo.out" }, ${r3(at(rail.titleAt ?? 0.55))});`);
    if (rail.lede) tl.push(`          tl.fromTo($("#${sc.id}-lede"), { opacity: 0, y: 14 }, { opacity: 1, y: 0, duration: 0.5, ease: "power2.out" }, ${r3(at(rail.titleAt ?? 0.55) + 0.45)});`);
    tl.push(`          tl.fromTo($("#${sc.id}-rule"), { scaleX: 0 }, { scaleX: 1, duration: 0.7, ease: "power3.inOut" }, ${r3(at(rail.titleAt ?? 0.55) + 0.8)});`);
    (rail.facts ?? []).forEach((f, i) => {
      tl.push(`          tl.fromTo($("#${sc.id}-f${i}"), { opacity: 0, y: 22 }, { opacity: 1, y: 0, duration: 0.45, ease: "power3.out" }, ${r3(at(f.at))});`);
    });
  }

  const html = `<!doctype html>
<!-- GENERATED by tools/build_scenes.mjs from data/scenes.json. Edit that file, not this one.
     ${sc.note ?? ""} -->
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
          overflow: hidden;
          background: #f7f7f8;
          color: #111111;
        }
        .sc-col {
          position: absolute;
          left: 1284px;
          top: 76px;
          width: 540px;
          height: 760px;
          display: flex;
          flex-direction: column;
        }
        .sc-title {
          margin-top: 16px;
          font-size: 62px;
          line-height: 1.18;
          font-weight: 700;
          letter-spacing: 0.02em;
        }
        .sc-lede {
          margin-top: 18px;
          font-size: 29px;
          line-height: 1.5;
          color: #3f3f46;
        }
        .sc-rule {
          margin-top: 26px;
          width: 100%;
          height: 3px;
          background: #111111;
          transform-origin: left center;
        }
        .sc-facts {
          margin-top: 6px;
          display: flex;
          flex-direction: column;
        }
        .sc-fact {
          display: grid;
          grid-template-columns: 54px 1fr;
          column-gap: 12px;
          padding: 18px 0 16px;
          border-bottom: 2px solid #d4d4d8;
        }
        .sc-fact-n {
          font-size: 22px;
          line-height: 40px;
          font-weight: 700;
          color: #5b5b66;
        }
        .sc-fact-h {
          font-size: 31px;
          line-height: 40px;
          font-weight: 700;
        }
        .sc-fact-b {
          margin-top: 2px;
          font-size: 24px;
          line-height: 34px;
          color: #3f3f46;
        }
        .sc-mono {
          font-size: 0.88em;
          letter-spacing: -0.01em;
        }
${styles.join("\n")}
      </style>

      <div id="root" class="fnv-root" data-composition-id="${sc.id}" data-width="1920" data-height="1080" data-duration="${hostDur}">
        <div class="fnv-grid"></div>
${body.join("\n")}
      </div>

      <script>
        (function () {
          const root = document.querySelector('[data-composition-id="${sc.id}"]');
          const $ = (s) => root.querySelector(s);
          const tl = gsap.timeline({ paused: true });
          // Virtual camera: put capture point (cx, cy) in the middle of the ${PANEL.w}x${PANEL.h} panel
          // at scale s, clamped so the panel never shows past the edge of the capture.
          const cam = (cx, cy, s) => ({
            x: Math.min(0, Math.max(${PANEL.w} - 1920 * s, ${PANEL.w / 2} - cx * s)),
            y: Math.min(0, Math.max(${PANEL.h} - 1080 * s, ${PANEL.h / 2} - cy * s)),
            scale: s,
          });
${tl.join("\n")}
          window.__timelines["${sc.id}"] = tl;
        })();
      </script>
    </template>
  </body>
</html>
`;
  return { html, hostDur };
}

let n = 0;
for (const sc of spec.scenes) {
  const { html, hostDur } = sceneHtml(sc);
  fs.writeFileSync(path.join(ROOT, "compositions", `${sc.id}.html`), html, "utf8");
  console.log(`${sc.id}: shot ${sc.shot}, ${sc.panels.length} panel(s), host ${hostDur}s`);
  n++;
}
console.log(`generated ${n} footage scenes`);
