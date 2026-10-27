// Builds the scenario film 《轉傳之前》 from data/storyboard.json.
//
// Usage (from video/hf-scenario):  node tools/build.mjs
// Reads:  data/storyboard.json   the shot list (presentations/2026-11_第二次簡報/01_情境劇劇本.md on a time line)
//         data/lines.json        length of every AI voice clip (tools/tts.py)
//         data/sfx_lengths.json  the sound effects (tools/sfx.py)
//         raw/                   the team's footage and voice-overs, when they exist ($FNV_SCENARIO_RAW overrides)
//         %TEMP%\fnv-scenario-raw  the live-site takes (tools/capture.mjs; $FNV_RAW overrides)
// Writes: compositions/*.html, index.html, data/schedule.json, renders/scenario.srt, and the baked media in
//         assets/footage/ and assets/audio/{live,rec}/.
//
// What stands in for what:
//   - live shot (the team on camera, short sketches): raw/<clip> → the clip and its own sound; the captions
//     follow the pauses in the speech. Missing → a placeholder card and AI voices (the storyboard preview).
//   - rec line (a team member's voice-over, one phone recording per scenario, raw/V1.m4a …): the recording is
//     cut at the pauses between sentences and each sentence goes to its line in order. Missing → AI voice.
//   - site step: one piece of a live-site take, with the last frame held until the voice-over ends.
//   - threads step: raw/T1.mp4 cut by the step's segments once they are set; until then a labelled mock-up.
// Every composition is generated: edit the storyboard, not compositions/ or index.html.
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import {
  ffmpeg, probeDur, loadTake, piecesOf, stepTime, bakeStep, cleanAudio, speechSegments, fitSentences,
} from "./footage.mjs";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const RAW = process.env.FNV_SCENARIO_RAW || path.join(ROOT, "raw");
const read = (f, fallback) => (fs.existsSync(f) ? JSON.parse(fs.readFileSync(f, "utf8")) : fallback);
const board = read(path.join(ROOT, "data", "storyboard.json"));
const lineLen = read(path.join(ROOT, "data", "lines.json"), {});
const sfxLen = read(path.join(ROOT, "data", "sfx_lengths.json"), {});
const FPS = board.fps;
const PAUSE = 1.2; // the "先暫停一下" freeze at the end of a sketch
const r3 = (n) => Math.round(n * 1000) / 1000;
const esc = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
const chunksOf = (l) => (Array.isArray(l.text) ? l.text : [l.text]);
const FOOTAGE = path.join(ROOT, "assets", "footage");
const LIVE_AUDIO = path.join(ROOT, "assets", "audio", "live");
const REC_AUDIO = path.join(ROOT, "assets", "audio", "rec");
for (const d of [FOOTAGE, LIVE_AUDIO, REC_AUDIO]) fs.mkdirSync(d, { recursive: true });

/** raw/S04.mp4, or the same name with another phone extension, or the last take S04_1, S04_2 … */
function findRaw(name, exts) {
  if (!fs.existsSync(RAW)) return null;
  const stem = name.replace(/\.[^.]+$/, "");
  const files = fs.readdirSync(RAW);
  const ok = (f) => exts.includes(path.extname(f).toLowerCase());
  const exact = files.find((f) => ok(f) && path.basename(f, path.extname(f)).toLowerCase() === stem.toLowerCase());
  if (exact) return path.join(RAW, exact);
  const takes = files
    .map((f) => ({ f, m: ok(f) && path.basename(f, path.extname(f)).match(new RegExp(`^${stem}_(\\d+)$`, "i")) }))
    .filter((x) => x.m)
    .sort((a, b) => Number(b.m[1]) - Number(a.m[1]));
  if (takes.length) {
    console.log(`  ${stem}: using the last take ${takes[0].f} (rename the best one to ${stem}${exts[0]} to choose)`);
    return path.join(RAW, takes[0].f);
  }
  return null;
}
const VIDEO_EXT = [".mp4", ".mov", ".m4v", ".3gp"];
const AUDIO_EXT = [".m4a", ".mp3", ".wav", ".aac", ".ogg", ".opus", ".amr", ".3gp", ".mp4", ".webm"];

/** Even split of [start, end] by caption length: the fallback when the pauses do not match the script. */
function proportional(start, end, weights) {
  const total = weights.reduce((a, b) => a + b, 0);
  let t = start;
  return weights.map((w) => {
    const seg = { start: r3(t), end: r3(t + ((end - start) * w) / total) };
    t = seg.end;
    return seg;
  });
}

// ── 1. the team's voice-overs: one recording per scenario, cut into its sentences ─────────────
const recLines = {};
for (const s of board.shots) for (const l of s.lines ?? []) if (l.rec) (recLines[l.rec] ??= []).push(l);
const recCuts = {};
for (const [rec, lines] of Object.entries(recLines)) {
  const src = findRaw(rec, AUDIO_EXT);
  if (!src) continue;
  const clean = path.join(REC_AUDIO, `${rec}.wav`);
  cleanAudio(src, clean);
  const { speech } = speechSegments(clean);
  let segs = board.recCuts?.[rec]?.map(([start, end]) => ({ start, end })) ?? fitSentences(speech, lines.length);
  if (!segs) {
    console.warn(`! ${rec}: ${speech.length} pauses-separated stretches for ${lines.length} sentences; split by length instead. Check the captions, or set recCuts.${rec} in the storyboard.`);
    segs = proportional(speech[0]?.start ?? 0, speech.at(-1)?.end ?? probeDur(clean), lines.map((l) => chunksOf(l).join("").length));
  }
  recCuts[rec] = segs.map((seg, i) => {
    const out = path.join(REC_AUDIO, `${rec}_${i}.wav`);
    const from = Math.max(0, seg.start - 0.08);
    ffmpeg(["-ss", String(from), "-t", String(seg.end + 0.12 - from), "-i", clean, "-c:a", "pcm_s16le", out], `${rec}_${i}`);
    return { file: `assets/audio/rec/${rec}_${i}.wav`, len: r3(probeDur(out)) };
  });
  console.log(`${rec}: ${path.basename(src)} → ${segs.length} sentences`);
}
const recUsed = {};

// ── 2. timing: every line gets a start and a length; every shot gets its length ─────────────
const shots = board.shots.map((s) => {
  const vidClip = s.clip && (s.kind === "live" || (s.kind === "threads" && s.segments)) ? findRaw(s.clip, VIDEO_EXT) : null;
  let live = null;
  if (vidClip && s.kind === "live") {
    // The team holds still for 2 s before and after every take. Unless the shot sets "trim", keep from
    // "lead" seconds before the first word (a sketch needs its action before the line) to 0.6 s after the last.
    const full = path.join(LIVE_AUDIO, `${s.id}.full.wav`);
    cleanAudio(vidClip, full);
    const heard = speechSegments(full).speech;
    const lead = s.lead ?? (s.nameTag ? 0.5 : 1.5);
    const [tin, tout] = s.trim ?? [
      r3(Math.max(0, (heard[0]?.start ?? 0) - lead)),
      r3(Math.min(probeDur(full), (heard.at(-1)?.end ?? probeDur(full)) + 0.6)),
    ];
    const wav = path.join(LIVE_AUDIO, `${s.id}.wav`);
    ffmpeg(["-ss", String(tin), "-t", String(tout - tin), "-i", full, "-c:a", "pcm_s16le", wav], s.id);
    fs.rmSync(full, { force: true });
    const { speech } = speechSegments(wav);
    const n = (s.lines ?? []).length;
    let segs = n ? fitSentences(speech, n) : [];
    if (n && !segs) {
      console.warn(`! ${s.id}: ${speech.length} speech stretches for ${n} sentences; captions split by length. Check them.`);
      segs = proportional(speech[0]?.start ?? 0.3, speech.at(-1)?.end ?? tout - tin - 0.3, s.lines.map((l) => chunksOf(l).join("").length));
    }
    live = { src: vidClip, tin, tout, segs };
  }
  let cursor = 0;
  const lines = (s.lines ?? []).map((l, n) => {
    const key = `${s.id}_${n}`;
    let at, len, audio;
    if (live) {
      ({ start: at } = live.segs[n]);
      len = live.segs[n].end - live.segs[n].start;
      audio = null; // the clip's own sound
    } else {
      if (l.rec && recCuts[l.rec]) {
        const k = (recUsed[l.rec] = (recUsed[l.rec] ?? -1) + 1);
        ({ len } = recCuts[l.rec][k]);
        audio = { src: recCuts[l.rec][k].file, track: 20 };
      } else {
        len = lineLen[key]?.dur;
        if (!len) throw new Error(`${key}: no voice clip yet; run tools/tts.py`);
        audio = { src: `assets/audio/lines/${key}.wav`, track: 19 };
      }
      at = typeof l.at === "string" ? cursor + Number(l.at) : l.at;
      if (n > 0 && at < cursor + 0.15) {
        console.warn(`! ${key}: moved from ${at}s to ${r3(cursor + 0.25)}s so it does not overlap the line before`);
        at = cursor + 0.25;
      }
    }
    cursor = at + len;
    // captions: the line's chunks share its length by number of characters
    const w = chunksOf(l).map((c) => c.length);
    const chunks = proportional(at, at + len, w);
    return { ...l, key, at: r3(at), len: r3(len), audio, chunks };
  });

  let natural = 0;
  let pieces = null;
  let take = null;
  if (s.kind === "site") {
    take = loadTake(s.take);
    pieces = piecesOf(take, s.segments);
    natural = pieces.at(-1).t1;
  }
  if (s.kind === "threads" && vidClip) {
    pieces = piecesOf({ name: s.clip, marks: [] }, s.segments);
    natural = pieces.at(-1).t1;
  }
  let dur;
  if (live) dur = Math.max(live.tout - live.tin, cursor + 0.2);
  else dur = Math.max(s.dur ?? 0, natural, cursor + 0.35);
  const pauseAt = s.pause ? r3(dur) : null;
  if (s.pause) dur += PAUSE;
  const placeholder = (s.kind === "live" && !live) || (s.kind === "threads" && !vidClip);
  return { ...s, live, vidClip, lines, take, pieces, pauseAt, placeholder, dur: r3(dur) };
});
let clock = 0;
for (const s of shots) {
  s.start = r3(clock);
  clock += s.dur;
}
const TOTAL = r3(clock);
const preview = shots.some((s) => s.placeholder) || Object.keys(recLines).some((r) => !recCuts[r]);

/** A storyboard time: seconds, or "line2", "line2.1" (its second caption), "line2@0.5", "line2end", with "+0.4". */
function when(s, ref) {
  if (typeof ref === "number") return ref;
  const m = /^line(\d+)(?:\.(\d+))?(?:@([\d.]+)|(end))?([+-][\d.]+)?$/.exec(ref);
  if (!m) throw new Error(`${s.id}: cannot read the time "${ref}"`);
  const l = s.lines[Number(m[1])];
  if (!l) throw new Error(`${s.id}: "${ref}" names a line the shot does not have`);
  let t = l.at;
  if (m[2] !== undefined) t = l.chunks[Number(m[2])].start;
  else if (m[4]) t = l.at + l.len;
  else if (m[3]) t = l.at + l.len * Number(m[3]);
  return r3(t + Number(m[5] ?? 0));
}

// ── 3. media: tutorial steps from the takes, the team's clips ───────────────────────────
const sfxEvents = [];
for (const s of shots) {
  if (s.kind === "site") {
    const dst = path.join(FOOTAGE, `${s.id}.mp4`);
    if (bakeStep(s.take, s.pieces, s.dur, dst, FPS)) console.log(`${s.id}: baked ${s.take.name} ${s.pieces.map((p) => `${p.from}–${p.to}${p.speed > 1 ? `×${p.speed}` : ""}`).join(" ")} → ${s.dur}s`);
    // sound follows what the take did: a click where the cursor clicked, a chime where the result appeared
    for (const m of s.take.marks) {
      const sound = m.kind === "click" ? "click" : m.kind === "waitFor" ? "chime" : null;
      const t = sound ? stepTime(s.pieces, m.t) : null;
      if (t != null) sfxEvents.push({ sound, t: r3(s.start + t) });
    }
  }
  if (s.live) {
    const pad = s.pauseAt != null ? `,tpad=stop_mode=clone:stop_duration=${PAUSE}` : "";
    ffmpeg(["-ss", String(s.live.tin), "-t", String(s.live.tout - s.live.tin), "-i", s.live.src,
      "-vf", `fps=${FPS},scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,format=yuv420p${pad}`,
      "-c:v", "libx264", "-preset", "medium", "-crf", "16", "-an", "-movflags", "+faststart", path.join(FOOTAGE, `live_${s.id}.mp4`)], s.id);
    console.log(`${s.id}: ${path.basename(s.live.src)} [${s.live.tin}–${r3(s.live.tout)}]`);
  }
  if (s.kind === "threads" && s.vidClip) {
    const parts = s.pieces.map((p, i) => `[0:v]trim=start=${p.from}:end=${p.to},setpts=(PTS-STARTPTS)/${p.speed}[p${i}]`);
    const hold = r3(s.dur - s.pieces.at(-1).t1);
    const graph = `${parts.join(";")};${s.pieces.map((p, i) => `[p${i}]`).join("")}concat=n=${s.pieces.length}:v=1:a=0,fps=${FPS},scale=780:-2,format=yuv420p${hold > 0 ? `,tpad=stop_mode=clone:stop_duration=${hold}` : ""}[v]`;
    ffmpeg(["-i", s.vidClip, "-filter_complex", graph, "-map", "[v]", "-t", String(s.dur), "-c:v", "libx264", "-preset", "medium", "-crf", "16", "-an", "-movflags", "+faststart", path.join(FOOTAGE, `live_${s.id}.mp4`)], s.id);
  }
  for (const e of s.sfx ?? []) sfxEvents.push({ sound: e.sound, t: r3(s.start + e.at) });
}

// ── 4. shared pieces ─────────────────────────────────────────────────────────────
const COMMON_CSS = `
        .sc-chip { position: absolute; left: 56px; top: 40px; padding: 8px 22px 9px; border-radius: 999px; background: rgba(17,17,17,0.82);
          color: #fff; font-size: 26px; line-height: 34px; font-weight: 700; letter-spacing: 0.04em; z-index: 5; }
        .ph { position: absolute; left: 740px; top: 56px; width: 440px; height: 924px; box-sizing: border-box; border: 12px solid #111111;
          border-radius: 58px; background: #ffffff; overflow: hidden; box-shadow: 0 30px 70px rgba(17,17,17,0.18);
          transform: scale(0.82); transform-origin: 50% 0; } /* scaled to end above the caption band, which would hide the bottom of the screen */
        .ph-screen { position: absolute; inset: 0; overflow: hidden; }
        .ph video { position: absolute; left: 0; top: 0; width: 416px; height: 900px; object-fit: cover; object-position: top; }
        .tag { position: absolute; padding: 8px 20px 9px; border-radius: 999px; background: #111111; color: #fff;
          font-size: 24px; line-height: 32px; font-weight: 700; white-space: nowrap; z-index: 6; }
        .tag-soft { background: #ffffff; color: #111111; box-shadow: 0 0 0 2px #d4d4d8; }
        .stp { position: absolute; left: 110px; top: 236px; width: 580px; }
        .stp-h { font-size: 30px; line-height: 40px; font-weight: 700; color: #6b7280; margin-bottom: 18px; letter-spacing: 0.1em; }
        .stp-i { display: flex; align-items: center; gap: 20px; margin-bottom: 18px; color: #8e8e96; }
        .stp-n { flex: none; width: 54px; height: 54px; border-radius: 50%; box-sizing: border-box; border: 3px solid #c4c4c8;
          font-size: 28px; line-height: 48px; text-align: center; font-weight: 700; }
        .stp-t { font-size: 36px; line-height: 46px; font-weight: 700; }
        .stp-i.done { color: #6b7280; }
        .stp-i.done .stp-n { border-color: #6b7280; background: #6b7280; color: #fff; }
        .stp-i.now { color: #111111; }
        .stp-i.now .stp-n { border-color: #111111; background: #111111; color: #fff; }
        .stp-i.now .stp-t { font-size: 42px; line-height: 52px; }
        .nts { position: absolute; left: 1250px; top: 250px; width: 600px; display: flex; flex-direction: column; gap: 22px; }
        .nt { align-self: flex-start; max-width: 600px; box-sizing: border-box; padding: 16px 28px 18px; border-radius: 20px; background: #111111;
          color: #ffffff; font-size: 38px; line-height: 50px; font-weight: 700; opacity: 0; }
        .chips { position: absolute; right: 56px; top: 130px; display: flex; flex-direction: column; align-items: flex-end; gap: 18px; z-index: 5; }
        .chip { padding: 14px 28px 15px; border-radius: 18px; background: #ffffff; color: #111111;
          font-size: 40px; line-height: 50px; font-weight: 700; box-shadow: 0 10px 30px rgba(0,0,0,0.25); opacity: 0; }
        .chip b { display: inline-block; margin-right: 14px; }
        .chip.bad { background: #111111; color: #ffffff; }`;

const sceneChip = (s) => (s.scene ? `<div class="sc-chip" id="${s.id}-chip">${esc(s.scene)}</div>` : "");
const sceneChipJs = (s) => (s.scene ? `tl.fromTo($("#${s.id}-chip"), { opacity: 0, y: -10 }, { opacity: 1, y: 0, duration: 0.3, ease: "power2.out" }, 0.05);` : "");

function stepsHtml(s) {
  if (!s.steps) return { html: "", js: "" };
  const list = board.stepLists[s.steps];
  const items = list.map((t, i) => {
    const n = i + 1;
    const state = n < s.step ? "done" : n === s.step ? "now" : "next";
    return `<div class="stp-i ${state}"${state === "now" ? ` id="${s.id}-now"` : ""}><span class="stp-n">${state === "done" ? "✓" : n}</span><span class="stp-t">${esc(t)}</span></div>`;
  });
  return {
    html: `<div class="stp"><div class="stp-h">怎麼查</div>${items.join("")}</div>`,
    js: `tl.fromTo($("#${s.id}-now"), { opacity: 0.35, x: -16 }, { opacity: 1, x: 0, duration: 0.4, ease: "power3.out" }, 0.05);`,
  };
}
function notesHtml(s) {
  if (!s.notes?.length) return { html: "", js: "" };
  return {
    html: `<div class="nts">${s.notes.map((n, i) => `<div class="nt" id="${s.id}-n${i}">${esc(n.text)}</div>`).join("")}</div>`,
    js: s.notes.map((n, i) => `tl.fromTo($("#${s.id}-n${i}"), { opacity: 0, x: 30 }, { opacity: 1, x: 0, duration: 0.4, ease: "power3.out" }, ${when(s, n.at)});`).join("\n          "),
  };
}
function chipsHtml(s) {
  if (!s.chips?.length) return { html: "", js: "" };
  const mark = (c) => (c.bad ? "✕" : c.note ? "!" : "✓");
  return {
    html: `<div class="chips">${s.chips.map((c, i) => `<div class="chip${c.bad ? " bad" : ""}" id="${s.id}-c${i}"><b>${mark(c)}</b>${esc(c.text)}</div>`).join("")}</div>`,
    js: s.chips.map((c, i) => `tl.fromTo($("#${s.id}-c${i}"), { opacity: 0, x: 40 }, { opacity: 1, x: 0, duration: 0.45, ease: "power3.out" }, ${when(s, c.at)});`).join("\n          "),
  };
}

// ── 5. one composition per shot ───────────────────────────────────────────────────
const KIND = {
  live(s) {
    const overlays = [];
    const js = [];
    if (s.counter) {
      const c = s.counter;
      overlays.push(`<div class="ov-counter" id="${s.id}-cnt"><span class="ov-k">${esc(c.label)}</span><span class="ov-n" id="${s.id}-cntn">${c.from}</span><span class="ov-k">${esc(c.unit)}</span></div>`);
      js.push(`tl.fromTo($("#${s.id}-cnt"), { opacity: 0, scale: 0.9 }, { opacity: 1, scale: 1, duration: 0.3, ease: "back.out(2)" }, ${c.at});`);
      for (let n = c.from + 1, k = 1; n <= c.to; n++, k++) {
        const t = r3(c.at + k * c.every);
        js.push(`tl.set($("#${s.id}-cntn"), { textContent: "${n}" }, ${t}); tl.fromTo($("#${s.id}-cntn"), { scale: 1.35 }, { scale: 1, duration: 0.25, ease: "power2.out" }, ${t});`);
      }
    }
    if (s.nameTag) {
      overlays.push(`<div class="lv-name" id="${s.id}-name">${esc(s.nameTag)}</div>`);
      js.push(`tl.fromTo($("#${s.id}-name"), { opacity: 0, x: -24 }, { opacity: 1, x: 0, duration: 0.4, ease: "power3.out" }, 0.3);`);
    }
    if (s.pauseAt != null) {
      overlays.push(`<div class="lv-dim" id="${s.id}-dim"></div><div class="lv-pause" id="${s.id}-pz"><span class="pz-bars"><i></i><i></i></span>先暫停一下</div>`);
      js.push(`tl.fromTo($("#${s.id}-dim"), { opacity: 0 }, { opacity: 1, duration: 0.25 }, ${s.pauseAt});`);
      js.push(`tl.fromTo($("#${s.id}-pz"), { opacity: 0, scale: 0.85 }, { opacity: 1, scale: 1, duration: 0.3, ease: "back.out(2)" }, ${s.pauseAt});`);
    }
    const body = s.live
      ? `<video id="${s.id}-v" class="lv-video" src="assets/footage/live_${s.id}.mp4" data-start="0" data-duration="${s.dur}" data-track-index="0" muted playsinline></video>`
      : `<div class="lv-card"><div class="lv-tag">實拍 ${s.id}</div><div class="lv-desc">${esc(s.desc)}</div><div class="lv-note">組員拍的畫面會放在這裡</div></div>`;
    return {
      css: `
        #root { background: #23262b; }
        .lv-video { position: absolute; inset: 0; width: 1920px; height: 1080px; object-fit: cover; }
        .lv-card { position: absolute; left: 120px; top: 250px; width: 1180px; height: 470px; box-sizing: border-box; padding: 54px 70px;
          border: 3px dashed rgba(255,255,255,0.28); border-radius: 36px; color: #fff; }
        .lv-tag { display: inline-block; padding: 8px 22px; border-radius: 12px; background: #ffffff; color: #111111; font-size: 30px; line-height: 38px; font-weight: 700; }
        .lv-desc { margin-top: 30px; font-size: 54px; line-height: 76px; font-weight: 700; }
        .lv-note { margin-top: 26px; font-size: 28px; line-height: 38px; color: rgba(255,255,255,0.55); }
        .lv-name { position: absolute; left: 56px; top: 750px; padding: 10px 26px 12px; border-radius: 14px; background: #ffffff; color: #111111;
          font-size: 34px; line-height: 44px; font-weight: 700; box-shadow: 0 10px 30px rgba(0,0,0,0.25); z-index: 5; opacity: 0; }
        .lv-dim { position: absolute; inset: 0; background: rgba(17,17,17,0.5); z-index: 7; opacity: 0; }
        .lv-pause { position: absolute; left: 660px; top: 440px; width: 600px; height: 140px; border-radius: 70px; background: #ffffff; color: #111111;
          display: flex; align-items: center; justify-content: center; gap: 28px; font-size: 60px; line-height: 70px; font-weight: 700; z-index: 8; opacity: 0; }
        .pz-bars { display: flex; gap: 12px; }
        .pz-bars i { display: block; width: 16px; height: 56px; border-radius: 4px; background: #111111; }
        .ov-counter { position: absolute; right: 60px; top: 40px; display: flex; align-items: baseline; gap: 14px; padding: 14px 30px 16px;
          border-radius: 20px; background: #ffffff; color: #111111; box-shadow: 0 12px 34px rgba(0,0,0,0.3); z-index: 5; opacity: 0; }
        .ov-k { font-size: 34px; line-height: 44px; font-weight: 700; }
        .ov-n { display: inline-block; min-width: 40px; text-align: center; font-size: 72px; line-height: 80px; font-weight: 700; font-variant-numeric: tabular-nums; }`,
      html: `${body}\n        ${overlays.join("\n        ")}`,
      js: js.join("\n          "),
    };
  },

  chat(s) {
    const avatar = (who) => esc(who.slice(-1));
    const on = s.shown ? " on" : "";
    const msgs = s.messages.map((m, i) => {
      const id = `${s.id}-m${i}`;
      if (m.link) {
        return `<div class="ch-row self${on}" id="${id}"><div class="ch-link"><img src="assets/og.png" alt="" />
              <div class="ch-link-t">全民查證公社</div><div class="ch-link-d">貼上訊息，10 秒知道真假</div><div class="ch-link-u">fakenewsverify.vercel.app</div></div></div>`;
      }
      const menu = s.copy?.msg === i ? `<div class="ch-menu" id="${s.id}-menu"><span>回覆</span><span class="hit">複製</span><span>轉傳</span></div>` : "";
      if (m.self) return `<div class="ch-row self${on}" id="${id}"><div class="ch-b">${esc(m.text)}</div></div>`;
      return `<div class="ch-row${on}" id="${id}"><div class="ch-av">${avatar(m.from)}</div><div class="ch-col"><div class="ch-name">${esc(m.from)}</div><div class="ch-b" id="${id}-b">${esc(m.text)}</div>${menu}</div></div>`;
    });
    const js = s.shown ? [] : s.messages.map((m, i) => `tl.fromTo($("#${s.id}-m${i}"), { opacity: 0, y: 24, scale: 0.96 }, { opacity: 1, y: 0, scale: 1, duration: 0.35, ease: "back.out(1.6)" }, ${m.at});`);
    if (s.copy) {
      const t = s.copy.at;
      js.push(`tl.to($("#${s.id}-m${s.copy.msg}-b"), { backgroundColor: "#d4d4d8", duration: 0.25 }, ${t});`);
      js.push(`tl.fromTo($("#${s.id}-menu"), { opacity: 0, y: -10 }, { opacity: 1, y: 0, duration: 0.25, ease: "power3.out" }, ${r3(t + 0.35)});`);
      js.push(`tl.to($("#${s.id}-menu"), { opacity: 0, duration: 0.2 }, ${r3(t + 1.6)});`);
      js.push(`tl.to($("#${s.id}-m${s.copy.msg}-b"), { backgroundColor: "#ffffff", duration: 0.25 }, ${r3(t + 1.6)});`);
      js.push(`tl.fromTo($("#${s.id}-toast"), { opacity: 0, y: 12 }, { opacity: 1, y: 0, duration: 0.25 }, ${r3(t + 1.7)});`);
    }
    return {
      css: `
        #root { background: #eceef1; }
        .ch-top { position: absolute; left: 0; right: 0; top: 0; height: 120px; background: #ffffff; border-bottom: 2px solid #e4e4e7; }
        .ch-title { position: absolute; left: 30px; right: 30px; top: 58px; font-size: 27px; line-height: 36px; font-weight: 700; text-align: center; }
        .ch-sub { position: absolute; left: 0; right: 0; top: 92px; font-size: 18px; color: #6b7280; text-align: center; }
        .ch-list { position: absolute; left: 0; right: 0; top: 120px; bottom: 0; padding: 26px 22px; background: #f2f4f7;
          display: flex; flex-direction: column; gap: 22px; }
        .ch-row { display: flex; gap: 14px; align-items: flex-start; opacity: 0; }
        .ch-row.on { opacity: 1; }
        .ch-row.self { justify-content: flex-end; }
        .ch-col { position: relative; }
        .ch-av { flex: none; width: 54px; height: 54px; border-radius: 50%; background: #3f3f46; color: #fff; font-size: 26px; line-height: 54px;
          text-align: center; font-weight: 700; }
        .ch-name { font-size: 19px; line-height: 26px; color: #6b7280; margin-bottom: 4px; }
        .ch-b { max-width: 300px; padding: 14px 18px; border-radius: 22px; background: #ffffff; font-size: 24px; line-height: 35px; color: #111111;
          box-shadow: 0 1px 0 rgba(0,0,0,0.06); }
        .self .ch-b { background: #dcebff; }
        .ch-menu { position: absolute; left: 0; top: 100%; margin-top: 12px; display: flex; border-radius: 16px; background: #111111; color: #ffffff;
          overflow: hidden; opacity: 0; box-shadow: 0 10px 26px rgba(0,0,0,0.3); }
        .ch-menu span { padding: 12px 20px; font-size: 22px; line-height: 30px; font-weight: 700; }
        .ch-menu .hit { background: #ffffff; color: #111111; }
        .ch-toast { position: absolute; left: 118px; bottom: 60px; width: 180px; padding: 12px 0; border-radius: 999px; background: rgba(17,17,17,0.88);
          color: #ffffff; text-align: center; font-size: 22px; line-height: 30px; font-weight: 700; opacity: 0; }
        .ch-link { width: 300px; border-radius: 20px; background: #ffffff; overflow: hidden; box-shadow: 0 1px 0 rgba(0,0,0,0.06); }
        .ch-link img { display: block; width: 300px; height: 158px; object-fit: cover; background: #111; }
        .ch-link-t { padding: 12px 16px 0; font-size: 22px; line-height: 30px; font-weight: 700; }
        .ch-link-d { padding: 2px 16px 0; font-size: 19px; line-height: 27px; color: #3f3f46; }
        .ch-link-u { padding: 4px 16px 14px; font-size: 17px; line-height: 24px; color: #6b7280; }`,
      html: `<div class="ph"><div class="ph-screen">
          <div class="ch-top"><div class="ch-title">${esc(s.group)}</div><div class="ch-sub">群組聊天（示意介面）</div></div>
          <div class="ch-list">
            ${msgs.join("\n            ")}
          </div>
          ${s.copy ? `<div class="ch-toast" id="${s.id}-toast">已複製</div>` : ""}
        </div></div>`,
      js: js.join("\n          "),
      sfx: s.shown ? [] : s.messages.map((m) => ({ sound: m.self ? "pop" : "ding", at: m.at })),
    };
  },

  sms(s) {
    return {
      css: `
        #root { background: #eceef1; }
        .sm-top { position: absolute; left: 0; right: 0; top: 0; height: 150px; background: #f7f7f8; border-bottom: 2px solid #e4e4e7; text-align: center; }
        .sm-av { margin: 40px auto 8px; width: 60px; height: 60px; border-radius: 50%; background: #9ca3af; }
        .sm-from { font-size: 22px; line-height: 30px; font-weight: 700; }
        .sm-list { position: absolute; left: 0; right: 0; top: 150px; bottom: 0; padding: 30px 22px; background: #ffffff; }
        .sm-time { font-size: 18px; color: #6b7280; text-align: center; margin-bottom: 16px; }
        .sm-b { max-width: 330px; padding: 16px 20px; border-radius: 24px; background: #e9e9eb; font-size: 25px; line-height: 37px; opacity: 0; }`,
      html: `<div class="ph"><div class="ph-screen">
          <div class="sm-top"><div class="sm-av"></div><div class="sm-from">${esc(s.from)}</div></div>
          <div class="sm-list"><div class="sm-time">簡訊・今天 下午 3:12</div><div class="sm-b" id="${s.id}-b">${esc(s.text)}</div></div>
        </div></div>
        <div class="tag tag-soft" style="left: 1250px; top: 470px">電話號碼已遮蔽</div>`,
      js: `tl.fromTo($("#${s.id}-b"), { opacity: 0, y: 24 }, { opacity: 1, y: 0, duration: 0.4, ease: "back.out(1.6)" }, 0.4);`,
      sfx: [{ sound: "buzz", at: 0.3 }],
    };
  },

  site(s) {
    const fast = s.pieces.filter((p) => p.speed > 1);
    return {
      css: `#root { background: #f7f7f8; }`,
      html: `<div class="ph"><div class="ph-screen">
          <video id="${s.id}-v" src="assets/footage/${s.id}.mp4" data-start="0" data-duration="${s.dur}" data-track-index="0" muted playsinline></video>
        </div></div>
        <div class="tag" style="left: 1250px; top: 120px">正式站實錄</div>
        ${fast.map((p, i) => `<div class="tag tag-soft" id="${s.id}-sp${i}" style="left: 1460px; top: 120px; opacity: 0">${esc(p.label ?? `畫面加速 ×${p.speed}`)}</div>`).join("\n        ")}`,
      js: fast.map((p, i) => `tl.set($("#${s.id}-sp${i}"), { opacity: 1 }, ${p.t0}); tl.set($("#${s.id}-sp${i}"), { opacity: 0 }, ${p.t1});`).join("\n          "),
    };
  },

  threads(s) {
    if (s.vidClip) {
      const fast = s.pieces.filter((p) => p.speed > 1);
      return {
        css: `#root { background: #f7f7f8; }`,
        html: `<div class="ph"><div class="ph-screen"><video id="${s.id}-v" src="assets/footage/live_${s.id}.mp4" data-start="0" data-duration="${s.dur}" data-track-index="0" muted playsinline></video></div></div>
        <div class="tag" style="left: 1250px; top: 120px">Threads 實錄・帳號已遮蔽</div>
        ${fast.map((p, i) => `<div class="tag tag-soft" id="${s.id}-sp${i}" style="left: 1250px; top: 180px; opacity: 0">${esc(p.label ?? `畫面加速 ×${p.speed}`)}</div>`).join("\n        ")}`,
        js: fast.map((p, i) => `tl.set($("#${s.id}-sp${i}"), { opacity: 1 }, ${p.t0}); tl.set($("#${s.id}-sp${i}"), { opacity: 0 }, ${p.t1});`).join("\n          "),
      };
    }
    // mock-up until the team's screen recording arrives; one state per step
    const mock = board.threadsMock;
    const order = ["post", "mention", "wait", "reply"];
    const stage = order.indexOf(s.part);
    const cm = mock.comments.map((c, i) => `<div class="th-c${stage > 0 ? " on" : ""}" id="${s.id}-cm${i}"><div class="th-av"></div><div><div class="th-n">網友 ${"ABC"[i]}</div><div class="th-t">${esc(c)}</div></div></div>`);
    const mention = stage >= 1
      ? `<div class="th-c${stage > 1 ? " on" : ""}" id="${s.id}-mn"><div class="th-av dark"></div><div><div class="th-n">${esc(mock.mention.author)}</div><div class="th-t th-at">${esc(mock.mention.text)}</div></div></div>`
      : "";
    const reply = stage === 3
      ? `<div class="th-c th-bot" id="${s.id}-rp"><div class="th-av bot">查</div><div><div class="th-n">factcheck_tw_bot</div>${mock.reply.map((l, i) => `<div class="th-r${i === 0 ? " th-r0" : ""}">${i === 0 ? '<span class="fnv-emoji">🔴</span>' + esc(l.replace("🔴", "")) : esc(l)}</div>`).join("")}</div></div>`
      : "";
    const js = [];
    if (stage === 0) mock.comments.forEach((c, i) => js.push(`tl.fromTo($("#${s.id}-cm${i}"), { opacity: 0, y: 20 }, { opacity: 1, y: 0, duration: 0.35, ease: "power3.out" }, ${r3(1.0 + i * 1.2)});`));
    if (stage === 1) js.push(`tl.fromTo($("#${s.id}-mn"), { opacity: 0, y: 20 }, { opacity: 1, y: 0, duration: 0.35, ease: "power3.out" }, 0.8);`);
    if (stage === 2) js.push(`tl.fromTo($("#${s.id}-wt"), { opacity: 0 }, { opacity: 1, duration: 0.3 }, 0.3);`);
    if (stage === 3) js.push(`tl.fromTo($("#${s.id}-rp"), { opacity: 0, y: 30 }, { opacity: 1, y: 0, duration: 0.45, ease: "back.out(1.4)" }, 0.4);`);
    const sfx = stage === 0 ? mock.comments.map((c, i) => ({ sound: "pop", at: r3(1.0 + i * 1.2) }))
      : stage === 1 ? [{ sound: "click", at: 0.8 }]
      : stage === 3 ? [{ sound: "ding", at: 0.4 }] : [];
    return {
      css: `
        #root { background: #f7f7f8; }
        .th-top { position: absolute; left: 0; right: 0; top: 0; height: 96px; border-bottom: 2px solid #ececec; text-align: center; font-size: 24px; line-height: 150px; font-weight: 700; }
        .th-list { position: absolute; left: 0; right: 0; top: 96px; bottom: 0; padding: 22px 22px; display: flex; flex-direction: column; gap: 18px; }
        .th-post { padding-bottom: 18px; border-bottom: 2px solid #ececec; }
        .th-c { display: flex; gap: 14px; align-items: flex-start; opacity: 0; }
        .th-c.on, .th-post .th-c { opacity: 1; }
        .th-av { flex: none; width: 46px; height: 46px; border-radius: 50%; background: #c4c4c8; }
        .th-av.dark { background: #3f3f46; }
        .th-av.bot { background: #111111; color: #fff; font-size: 22px; line-height: 46px; text-align: center; font-weight: 700; }
        .th-n { font-size: 19px; line-height: 26px; font-weight: 700; }
        .th-t { font-size: 23px; line-height: 33px; }
        .th-at { color: #1d4ed8; }
        .th-bot { padding: 14px; border-radius: 18px; background: #f4f4f5; }
        .th-r { font-size: 19px; line-height: 28px; word-break: break-all; }
        .th-r0 { font-size: 23px; line-height: 32px; font-weight: 700; }
        .th-wait { align-self: center; margin-top: 10px; padding: 10px 22px; border-radius: 999px; background: #f4f4f5; color: #3f3f46;
          font-size: 20px; line-height: 28px; font-weight: 700; opacity: 0; }`,
      html: `<div class="ph"><div class="ph-screen">
          <div class="th-top">Threads</div>
          <div class="th-list">
            <div class="th-post"><div class="th-c"><div class="th-av"></div><div><div class="th-n">${esc(mock.post.author)}</div><div class="th-t">${esc(mock.post.text)}</div></div></div></div>
            ${cm.join("\n            ")}
            ${mention}
            ${stage === 2 ? `<div class="th-wait" id="${s.id}-wt">等待機器人回覆…</div>` : ""}
            ${reply}
          </div>
        </div></div>
        <div class="tag" style="left: 1250px; top: 120px">示意畫面：正式片換成 Threads 實錄</div>
        ${stage === 2 ? `<div class="tag tag-soft" style="left: 1250px; top: 180px">實際等待時間約 30 秒～1 分鐘</div>` : ""}`,
      js: js.join("\n          "),
      sfx,
    };
  },

  card(s) {
    return CARD[s.template](s);
  },
};

const CARD = {
  disclaimer: (s) => ({
    css: `#root { background: #111111; } .dc { position: absolute; left: 0; right: 0; top: 500px; text-align: center; color: #fff; font-size: 44px; line-height: 60px; font-weight: 700; opacity: 0; }`,
    html: `<div class="dc" id="${s.id}-t">本片情節虛構；系統畫面皆為正式站實錄。</div>`,
    js: `tl.fromTo($("#${s.id}-t"), { opacity: 0 }, { opacity: 1, duration: 0.4 }, 0.2); tl.to($("#${s.id}-t"), { opacity: 0, duration: 0.3 }, ${r3(s.dur - 0.35)});`,
  }),
  title: (s) => ({
    css: `
        #root { background: #f7f7f8; }
        .tt-h { position: absolute; left: 0; right: 0; top: 330px; text-align: center; font-size: 150px; line-height: 180px; font-weight: 700; letter-spacing: 0.08em; }
        .tt-s { position: absolute; left: 0; right: 0; top: 540px; text-align: center; font-size: 46px; line-height: 60px; font-weight: 700; color: #3f3f46; }
        .tt-m { position: absolute; left: 0; right: 0; top: 640px; text-align: center; font-size: 30px; line-height: 40px; color: #6b7280; }
        .tt-rule { position: absolute; left: 760px; top: 620px; width: 400px; height: 4px; background: #111111; transform-origin: center; }`,
    html: `<div class="tt-h" id="${s.id}-h">《轉傳之前》</div><div class="tt-s" id="${s.id}-s">全民查證公社　使用情境劇</div>
        <div class="tt-rule" id="${s.id}-r"></div><div class="tt-m" id="${s.id}-m">長庚大學資訊工程學系　軟硬體專題　｜　指導教授 黃崇源</div>`,
    js: `tl.fromTo($("#${s.id}-h"), { opacity: 0, scale: 1.08 }, { opacity: 1, scale: 1, duration: 0.8, ease: "expo.out" }, 0.2);
          tl.fromTo($("#${s.id}-s"), { opacity: 0, y: 20 }, { opacity: 1, y: 0, duration: 0.5, ease: "power3.out" }, 0.9);
          tl.fromTo($("#${s.id}-r"), { scaleX: 0 }, { scaleX: 1, duration: 0.6, ease: "power3.inOut" }, 1.2);
          tl.fromTo($("#${s.id}-m"), { opacity: 0 }, { opacity: 1, duration: 0.5 }, 1.6);`,
  }),
  burst: (s) => {
    const spots = [[300, 250, -6], [1150, 200, 5], [420, 640, 4], [1080, 600, -4]];
    return {
      css: `
        #root { background: #eceef1; }
        .bb { position: absolute; padding: 26px 38px 28px; border-radius: 34px; background: #ffffff; font-size: 56px; line-height: 70px; font-weight: 700;
          box-shadow: 0 18px 44px rgba(17,17,17,0.14); opacity: 0; white-space: nowrap; }`,
      html: s.bubbles.map((b, i) => `<div class="bb" id="${s.id}-b${i}" style="left: ${spots[i][0]}px; top: ${spots[i][1]}px; transform: rotate(${spots[i][2]}deg)">${esc(b)}</div>`).join("\n        "),
      js: s.bubbles.map((b, i) => `tl.fromTo($("#${s.id}-b${i}"), { opacity: 0, scale: 0.6 }, { opacity: 1, scale: 1, duration: 0.35, ease: "back.out(2.2)" }, ${s.sfx?.[i]?.at ?? 0.3 + i * 0.6});`).join("\n          "),
    };
  },
  section: (s) => ({
    css: `
        #root { background: #111111; color: #ffffff; }
        .sx-n { position: absolute; left: 0; right: 0; top: 380px; text-align: center; }
        .sx-n span { display: inline-block; padding: 10px 30px 12px; border-radius: 999px; background: #ffffff; color: #111111; font-size: 40px; line-height: 50px; font-weight: 700; }
        .sx-t { position: absolute; left: 0; right: 0; top: 490px; text-align: center; font-size: 96px; line-height: 116px; font-weight: 700; }`,
    html: `<div class="sx-n" id="${s.id}-n"><span>${esc(s.num)}</span></div><div class="sx-t" id="${s.id}-t">${esc(s.title)}</div>`,
    js: `tl.fromTo($("#${s.id}-n"), { opacity: 0, y: -16 }, { opacity: 1, y: 0, duration: 0.35, ease: "power3.out" }, 0.05);
          tl.fromTo($("#${s.id}-t"), { opacity: 0, y: 24 }, { opacity: 1, y: 0, duration: 0.45, ease: "power3.out" }, 0.2);`,
  }),
  compare: (s) => {
    const span = Math.max(2.4, (s.dur - 3) / s.rows.length);
    return {
      css: `
        #root { background: #f7f7f8; }
        .cp-h { position: absolute; left: 150px; top: 70px; font-size: 60px; line-height: 76px; font-weight: 700; }
        .cp { position: absolute; left: 150px; top: 190px; width: 1620px; border-collapse: collapse; }
        .cp th { font-size: 32px; line-height: 44px; text-align: left; padding: 10px 24px; color: #3f3f46; }
        .cp td { font-size: 36px; line-height: 48px; padding: 18px 24px; border-top: 2px solid #d4d4d8; vertical-align: top; }
        .cp td.k { width: 230px; font-weight: 700; }
        .cp td.b { width: 560px; color: #6b7280; }
        .cp td.a { font-weight: 700; }
        .cp tr.r { opacity: 0; }`,
      html: `<div class="cp-h" id="${s.id}-h">用之前 vs. 用之後</div>
        <table class="cp"><tr><th></th><th>使用前</th><th>使用全民查證公社之後</th></tr>
          ${s.rows.map((r, i) => `<tr class="r" id="${s.id}-r${i}"><td class="k">${esc(r[0])}</td><td class="b">${esc(r[1])}</td><td class="a">${esc(r[2])}</td></tr>`).join("\n          ")}
        </table>`,
      js: [`tl.fromTo($("#${s.id}-h"), { opacity: 0, y: -16 }, { opacity: 1, y: 0, duration: 0.45, ease: "power3.out" }, 0.2);`,
        ...s.rows.map((r, i) => `tl.fromTo($("#${s.id}-r${i}"), { opacity: 0, x: -30 }, { opacity: 1, x: 0, duration: 0.45, ease: "power3.out" }, ${r3(0.9 + i * span)});`)].join("\n          "),
    };
  },
  end: (s) => ({
    css: `
        #root { background: #111111; color: #fff; }
        .en-h { position: absolute; left: 0; right: 0; top: 150px; text-align: center; font-size: 96px; line-height: 116px; font-weight: 700; }
        .en-u { position: absolute; left: 0; right: 0; top: 300px; text-align: center; font-size: 48px; line-height: 60px; font-weight: 700; }
        .en-qr { position: absolute; top: 420px; width: 300px; text-align: center; font-size: 30px; line-height: 40px; }
        .en-qr img { display: block; width: 240px; height: 240px; margin: 0 auto 16px; padding: 18px; background: #fff; border-radius: 18px; }
        .en-m { position: absolute; left: 0; right: 0; top: 860px; text-align: center; font-size: 28px; line-height: 44px; color: #d4d4d8; }`,
    html: `<div class="en-h" id="${s.id}-h">轉傳之前，先查一下！</div>
        <div class="en-u" id="${s.id}-u">fakenewsverify.vercel.app</div>
        <div class="en-qr" id="${s.id}-q1" style="left: 600px"><img src="assets/qr_site.svg" alt="" />網站</div>
        <div class="en-qr" id="${s.id}-q2" style="left: 1020px"><img src="assets/qr_threads.svg" alt="" />Threads 查核機器人</div>
        <div class="en-m" id="${s.id}-m">長庚大學資訊工程學系　軟硬體專題「AI 為核心的假訊息驗證系統」<br />組員：廖晢勛、石岱勳、姚睿、張宇宏、廖育翔　｜　指導教授：黃崇源</div>`,
    js: `tl.fromTo($("#${s.id}-h"), { opacity: 0, y: 20 }, { opacity: 1, y: 0, duration: 0.6, ease: "power3.out" }, 0.2);
          tl.fromTo($("#${s.id}-u"), { opacity: 0 }, { opacity: 1, duration: 0.5 }, 0.8);
          tl.fromTo([$("#${s.id}-q1"), $("#${s.id}-q2")], { opacity: 0, y: 24 }, { opacity: 1, y: 0, duration: 0.5, stagger: 0.2, ease: "power3.out" }, 1.2);
          tl.fromTo($("#${s.id}-m"), { opacity: 0 }, { opacity: 1, duration: 0.6 }, 2.0);`,
  }),
};

const compo = (s, k, extra) => `<!doctype html>
<!-- GENERATED by tools/build.mjs from data/storyboard.json (${s.id}). Edit the storyboard, not this file. -->
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
        }${COMMON_CSS}${k.css}
      </style>
      <div id="root" class="fnv-root" data-composition-id="${s.id}" data-width="1920" data-height="1080" data-duration="${s.dur}">
        ${k.html}
        ${extra.map((e) => e.html).filter(Boolean).join("\n        ")}
        ${sceneChip(s)}
      </div>
      <script>
        (function () {
          const root = document.querySelector('[data-composition-id="${s.id}"]');
          const $ = (sel) => root.querySelector(sel);
          const tl = gsap.timeline({ paused: true });
          ${sceneChipJs(s)}
          ${k.js}
          ${extra.map((e) => e.js).filter(Boolean).join("\n          ")}
          window.__timelines["${s.id}"] = tl;
        })();
      </script>
    </template>
  </body>
</html>
`;

const COMPO_DIR = path.join(ROOT, "compositions");
fs.rmSync(COMPO_DIR, { recursive: true, force: true });
fs.mkdirSync(COMPO_DIR, { recursive: true });
for (const s of shots) {
  const k = KIND[s.kind](s);
  fs.writeFileSync(path.join(COMPO_DIR, `${s.id}.html`), compo(s, k, [stepsHtml(s), notesHtml(s), chipsHtml(s)]), "utf8");
  for (const e of k.sfx ?? []) sfxEvents.push({ sound: e.sound, t: r3(s.start + e.at) });
}

// ── 6. captions: one cue per caption chunk ─────────────────────────────────────────
const cues = [];
for (const s of shots) {
  for (const l of s.lines) {
    l.chunks.forEach((c, i) => {
      const last = i === l.chunks.length - 1;
      cues.push({ shot: s.id, who: l.who, text: chunksOf(l)[i], start: r3(s.start + c.start), end: r3(s.start + c.end - (last ? 0.3 : 0.05)) });
    });
  }
}
cues.sort((a, b) => a.start - b.start);
cues.forEach((c, i) => {
  const next = cues[i + 1];
  c.in = r3(Math.max(0, c.start - 0.06));
  c.out = r3(Math.min(Math.max(c.end + 0.25, c.in + 0.8), next ? next.start - 0.08 : TOTAL - 0.05));
});
const labelled = (c) => board.voices[c.who]?.label !== false;
const label = (c) => (labelled(c) ? `<span class="cap-who">${esc(c.who)}</span>` : "");
const captions = `<!doctype html>
<!-- GENERATED by tools/build.mjs. One caption group per cue; one group visible at a time. -->
<html lang="zh-Hant">
  <head>
    <meta charset="UTF-8" />
  </head>
  <body>
    <template>
      <style>
        #root { position: absolute; inset: 0; pointer-events: none; }
        .cap-g { position: absolute; left: 0; top: 846px; width: 1920px; height: 150px; display: flex; align-items: flex-end; justify-content: center; opacity: 0; }
        .cap-t { display: block; max-width: 1500px; padding: 11px 34px 13px; border-radius: 18px; background: rgba(17,17,17,0.9); color: #ffffff;
          font-size: 44px; line-height: 56px; font-weight: 700; text-align: center; text-wrap: balance; }
        .cap-who { display: inline-block; margin-right: 18px; padding: 0 14px; border-radius: 10px; background: #ffffff; color: #111111; font-size: 34px; line-height: 46px; vertical-align: 3px; }
      </style>
      <div id="root" class="fnv-root" data-composition-id="captions" data-width="1920" data-height="1080" data-duration="${TOTAL}" data-layout-allow-overlap>
${cues.map((c, i) => `        <div class="cap-g" id="cap-${i}"><span class="cap-t">${label(c)}${esc(c.text)}</span></div>`).join("\n")}
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
fs.writeFileSync(path.join(COMPO_DIR, "captions.html"), captions, "utf8");

// ── 7. chrome: the preview watermark while stand-ins remain ─────────────────────────────
const chrome = `<!doctype html>
<!-- GENERATED by tools/build.mjs. -->
<html lang="zh-Hant">
  <head>
    <meta charset="UTF-8" />
  </head>
  <body>
    <template>
      <style>
        #root { position: absolute; inset: 0; pointer-events: none; }
        .wm { position: absolute; right: 40px; bottom: 26px; padding: 6px 16px; border-radius: 10px; background: rgba(17,17,17,0.55); color: #fff;
          font-size: 22px; line-height: 30px; font-weight: 700; }
      </style>
      <div id="root" class="fnv-root" data-composition-id="chrome" data-width="1920" data-height="1080" data-duration="${TOTAL}" data-layout-allow-overlap>
        ${preview ? '<div class="wm">分鏡預覽版：真人畫面為佔位字卡，組員的台詞與配音暫用 AI 語音</div>' : ""}
      </div>
      <script>
        (function () {
          window.__timelines["chrome"] = gsap.timeline({ paused: true });
        })();
      </script>
    </template>
  </body>
</html>
`;
fs.writeFileSync(path.join(COMPO_DIR, "chrome.html"), chrome, "utf8");

// ── 8. index.html ────────────────────────────────────────────────────────────────
const host = (id, start, dur, track, kind = "graphics") => `      <div id="el-${id}" class="clip" data-composition-id="${id}" data-composition-src="compositions/${id}.html"
        data-start="${start}" data-duration="${dur}" data-track-index="${track}" data-track-kind="${kind}" data-width="1920" data-height="1080"></div>`;
const fade = (len) => esc(JSON.stringify({ version: 1, lanes: [{ target: "volume", points: [{ t: 0, v: 0 }, { t: 0.05, v: 1 }, { t: r3(len - 0.15), v: 1 }, { t: r3(len), v: 0 }] }] }));
const voices = [];
for (const s of shots) {
  for (const l of s.lines.filter((x) => x.audio)) {
    voices.push(`      <audio id="vo-${l.key}" src="${l.audio.src}" data-start="${r3(s.start + l.at)}" data-duration="${l.len}"
        data-track-index="${l.audio.track}" data-volume="1" data-automation="${fade(l.len)}"></audio>`);
  }
  if (s.live) {
    voices.push(`      <audio id="live-${s.id}" src="assets/audio/live/${s.id}.wav" data-start="${s.start}" data-duration="${r3(s.live.tout - s.live.tin)}" data-track-index="18" data-volume="1"></audio>`);
  }
}
const SFX_TRACK = { click: 21, tick: 22, chime: 23, whoosh: 24, ding: 25, pop: 26, buzz: 27 };
const SFX_GAIN = { click: 0.5, tick: 0.4, chime: 0.5, whoosh: 0.5, ding: 0.6, pop: 0.5, buzz: 0.6 };
sfxEvents.sort((a, b) => a.t - b.t);
const sfxEls = sfxEvents.map((e, i) => `      <audio id="sfx-${String(i).padStart(3, "0")}" src="assets/audio/sfx/${e.sound}.wav" data-start="${e.t}"
        data-duration="${sfxLen[e.sound + ".wav"] ?? 0.4}" data-track-index="${SFX_TRACK[e.sound]}" data-volume="${SFX_GAIN[e.sound]}"></audio>`);

const filmCss = fs.readFileSync(path.join(ROOT, "assets", "film.css"), "utf8").trimEnd().split(/\r?\n/).map((l) => (l ? "      " + l : l)).join("\n");
const index = `<!doctype html>
<!-- GENERATED by tools/build.mjs from data/storyboard.json. Edit that, not this file. -->
<html lang="zh-Hant" data-resolution="landscape">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=1920, height=1080" />
    <title>全民查證公社 情境劇《轉傳之前》</title>
    <script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
    <style>
${filmCss}
      html, body { margin: 0; background: #111111; }
      #root { position: relative; width: 100%; height: 100%; overflow: hidden; background: #111111; }
      #root > div[data-composition-src] { position: absolute; inset: 0; }
    </style>
  </head>
  <body>
    <div id="root" data-composition-id="main" data-start="0" data-width="1920" data-height="1080" data-duration="${TOTAL}" data-fps="${FPS}">
      <!-- shots (track 1), back to back -->
${shots.map((s) => host(s.id, s.start, s.dur, 1)).join("\n")}

      <!-- watermark (track 5) and captions (track 6) -->
${host("chrome", 0, TOTAL, 5)}
${host("captions", 0, TOTAL, 6, "captions")}

      <!-- voices: the team's voice-overs (track 20), AI stand-ins (19), the sound of the team's clips (18) -->
${voices.join("\n")}

      <!-- sound effects (tracks 21-27), synthesised by tools/sfx.py -->
${sfxEls.join("\n")}
    </div>
    <script>
      window.__timelines["main"] = gsap.timeline({ paused: true });
    </script>
  </body>
</html>
`;
fs.writeFileSync(path.join(ROOT, "index.html"), index, "utf8");

// ── 9. schedule + srt ────────────────────────────────────────────────────────────
fs.writeFileSync(path.join(ROOT, "data", "schedule.json"), JSON.stringify({
  total: TOTAL, preview,
  shots: shots.map((s) => ({ id: s.id, kind: s.kind, start: s.start, dur: s.dur, real: Boolean(s.live || s.vidClip) })),
  recordings: Object.fromEntries(Object.keys(recLines).map((r) => [r, Boolean(recCuts[r])])),
  cues: cues.map(({ shot, who, text, in: t0, out: t1 }) => ({ shot, who, text, in: t0, out: t1 })),
}, null, 1) + "\n", "utf8");
const ts = (t) => {
  const ms = Math.round(t * 1000);
  const h = Math.floor(ms / 3600000), m = Math.floor((ms % 3600000) / 60000), sec = Math.floor((ms % 60000) / 1000), r = ms % 1000;
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:${String(sec).padStart(2, "0")},${String(r).padStart(3, "0")}`;
};
fs.mkdirSync(path.join(ROOT, "renders"), { recursive: true });
fs.writeFileSync(path.join(ROOT, "renders", "scenario.srt"),
  cues.map((c, i) => `${i + 1}\n${ts(c.in)} --> ${ts(c.out)}\n${labelled(c) ? c.who + "：" : ""}${c.text}\n`).join("\n"), "utf8");

for (const s of shots) console.log(`${s.id.padEnd(5)} ${s.kind.padEnd(8)} ${String(s.start).padStart(7)} +${s.dur}${s.live || s.vidClip ? "  (real)" : ""}`);
console.log(`total ${TOTAL}s (${Math.floor(TOTAL / 60)}:${String(Math.round(TOTAL % 60)).padStart(2, "0")}) · ${shots.length} shots · ${cues.length} captions · ${sfxEvents.length} sfx${preview ? " · storyboard preview" : ""}`);
if (TOTAL > 295) console.warn("! longer than 4:55 (the limit is 5 minutes)");
