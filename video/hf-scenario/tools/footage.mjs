// Footage helpers for tools/build.mjs: the live-site takes (tools/capture.mjs) and the team's clips.
//
// HyperFrames plays <video> at a constant rate only (no speed ramps, no mid-source freezes), so every
// tutorial step is baked into its own constant-rate clip here: the step's piece of the take, accelerated
// pieces where the storyboard asks for them (the scene labels them 畫面加速 ×N), and the last frame held
// until the step's voice-over ends.
//
// The raw takes are PNG frames plus meta.json in %TEMP%\fnv-scenario-raw (override with $FNV_RAW);
// they never go in the repo. Record them with `node tools/capture.mjs`.
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { createHash } from "node:crypto";
import { spawnSync } from "node:child_process";

export const RAW_TAKES = process.env.FNV_RAW || path.join(os.tmpdir(), "fnv-scenario-raw");

export function ffBin(name) {
  const guess = path.join(process.env.LOCALAPPDATA ?? "", "Microsoft", "WinGet", "Packages",
    "Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe", "ffmpeg-9.0.1-full_build", "bin", `${name}.exe`);
  return fs.existsSync(guess) ? guess : name;
}

export function ffmpeg(args, what) {
  const r = spawnSync(ffBin("ffmpeg"), ["-hide_banner", "-loglevel", "error", "-y", ...args], { encoding: "utf8", maxBuffer: 64 * 1024 * 1024 });
  if (r.status !== 0) throw new Error(`${what}: ffmpeg failed\n${r.stderr}`);
  return r;
}

export function probeDur(file) {
  const r = spawnSync(ffBin("ffprobe"), ["-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", file], { encoding: "utf8" });
  return Number(r.stdout.trim());
}

const takes = new Map();
/** Frames (sorted, with their time since the take started) and marks of one take. */
export function loadTake(name) {
  if (takes.has(name)) return takes.get(name);
  const dir = path.join(RAW_TAKES, name, "frames");
  const metaFile = path.join(dir, "meta.json");
  if (!fs.existsSync(metaFile)) throw new Error(`take ${name} not found in ${RAW_TAKES}; record it: node tools/capture.mjs ${name}`);
  const meta = JSON.parse(fs.readFileSync(metaFile, "utf8"));
  const frames = meta.frames.map((f) => ({ file: path.join(dir, f.name), rel: f.ts - meta.startWall })).sort((a, b) => a.rel - b.rel);
  const take = { name, frames, marks: meta.marks, recordedAt: meta.recordedAt, dsf: meta.device?.deviceScaleFactor ?? 1 };
  takes.set(name, take);
  return take;
}

/** A take time: seconds, or the label of a mark the take recorded ("home", "result_top", ...), optionally "result_top-2". */
export function takeTime(take, ref) {
  if (typeof ref === "number") return ref;
  const [, label, offset] = /^(.*?)([+-][\d.]+)?$/.exec(ref);
  const m = take.marks.find((x) => x.label === label);
  if (!m) throw new Error(`take ${take.name} has no mark "${label}" (marks: ${take.marks.filter((x) => x.label).map((x) => x.label).join(", ")})`);
  return +(m.t + Number(offset ?? 0)).toFixed(3);
}

/** The captured frame shown at a take time (the latest one at or before it). */
export function frameAt(take, raw) {
  let ans = take.frames[0];
  for (const f of take.frames) if (f.rel <= raw + 1e-6) ans = f;
  return ans.file;
}

/** A still close-up of the page: box = [x, y, w, h] in CSS pixels of the phone viewport. */
export function cropStill(take, raw, box, dst) {
  const [x, y, w, h] = box.map((v) => Math.round(v * take.dsf));
  ffmpeg(["-i", frameAt(take, raw), "-vf", `crop=${w}:${h}:${x}:${y}`, "-frames:v", "1", dst], path.basename(dst));
}

/** Segments → pieces on the step's own clock: [{from, to, speed, label, t0, t1}]. */
export function piecesOf(take, segments) {
  let clock = 0;
  return segments.map((seg) => {
    const from = takeTime(take, seg.from);
    const to = takeTime(take, seg.to);
    const speed = seg.speed ?? 1;
    const t0 = clock;
    clock += (to - from) / speed;
    return { from, to, speed, label: seg.label, t0: +t0.toFixed(3), t1: +clock.toFixed(3) };
  });
}

/** Where a take time lands on the step clock, or null when the step does not show it. */
export function stepTime(pieces, raw) {
  for (const p of pieces) if (raw >= p.from && raw < p.to) return +(p.t0 + (raw - p.from) / p.speed).toFixed(3);
  return null;
}

/**
 * One constant-rate clip for a tutorial step: every output frame shows the latest captured frame at or
 * before its take time (the same rule as the earlier films), then the last frame is held to `dur`.
 * Skipped when the clip for the same take, pieces, length and frame rate already exists.
 */
export function bakeStep(take, pieces, dur, dst, fps) {
  const key = createHash("sha1").update(JSON.stringify([take.name, take.recordedAt, pieces, dur, fps])).digest("hex").slice(0, 16);
  const stamp = `${dst}.key`;
  if (fs.existsSync(dst) && fs.existsSync(stamp) && fs.readFileSync(stamp, "utf8") === key) return false;
  const pick = (r) => {
    let lo = 0, hi = take.frames.length - 1, ans = 0;
    while (lo <= hi) {
      const mid = (lo + hi) >> 1;
      if (take.frames[mid].rel <= r + 1e-6) { ans = mid; lo = mid + 1; } else hi = mid - 1;
    }
    return take.frames[ans].file;
  };
  const total = Math.round(dur * fps);
  const out = [];
  const push = (file) => {
    if (out.length && out[out.length - 1].file === file) out[out.length - 1].count++;
    else out.push({ file, count: 1 });
  };
  let n = 0;
  for (const p of pieces) {
    const frames = Math.round(((p.to - p.from) / p.speed) * fps);
    for (let k = 0; k < frames && n < total; k++, n++) push(pick(p.from + (k * p.speed) / fps));
  }
  const last = pick(pieces[pieces.length - 1].to);
  for (; n < total; n++) push(last);
  const fwd = (p) => p.replace(/\\/g, "/");
  const list = `${dst}.ffconcat`;
  const lines = ["ffconcat version 1.0"];
  for (const e of out) lines.push(`file '${fwd(e.file)}'`, `duration ${(e.count / fps).toFixed(6)}`);
  lines.push(`file '${fwd(out[out.length - 1].file)}'`);
  fs.writeFileSync(list, lines.join("\n") + "\n", "utf8");
  try {
    ffmpeg(["-f", "concat", "-safe", "0", "-i", list, "-vf", `fps=${fps},format=yuv420p`, "-c:v", "libx264", "-preset", "slow", "-crf", "13",
      "-g", String(fps), "-t", String(dur), "-an", "-movflags", "+faststart", dst], path.basename(dst));
  } finally {
    fs.rmSync(list, { force: true });
  }
  fs.writeFileSync(stamp, key, "utf8");
  return true;
}

// ── the team's recordings ──────────────────────────────────────────────────────

/** Cleaned speech: low cut, denoise, loudness -16 LUFS, 48 kHz stereo WAV. */
export function cleanAudio(src, dst, from = 0, len = null) {
  const cut = len == null ? ["-ss", String(from)] : ["-ss", String(from), "-t", String(len)];
  ffmpeg([...cut, "-i", src, "-vn", "-af", "highpass=f=90,afftdn=nf=-25,loudnorm=I=-16:TP=-1.5:LRA=11", "-ar", "48000", "-ac", "2", dst], path.basename(dst));
}

/** Speech stretches in a WAV, from ffmpeg's silencedetect: [{start, end}] in seconds. */
export function speechSegments(wav) {
  const r = spawnSync(ffBin("ffmpeg"), ["-hide_banner", "-nostats", "-i", wav, "-af", "silencedetect=noise=-34dB:d=0.4", "-f", "null", "-"], { encoding: "utf8" });
  const total = probeDur(wav);
  const silences = [];
  let open = null;
  for (const line of r.stderr.split(/\r?\n/)) {
    const s = line.match(/silence_start: ([\d.]+)/);
    const e = line.match(/silence_end: ([\d.]+)/);
    if (s) open = Number(s[1]);
    if (e) { silences.push([open ?? 0, Number(e[1])]); open = null; }
  }
  if (open != null) silences.push([open, total]);
  const speech = [];
  let cursor = 0;
  for (const [a, b] of silences) {
    if (a - cursor > 0.15) speech.push({ start: cursor, end: a });
    cursor = b;
  }
  if (total - cursor > 0.15) speech.push({ start: cursor, end: total });
  return { total, speech };
}

/**
 * Fit the speech stretches to `count` sentences. The readers pause between sentences, so the longest
 * gaps are the sentence breaks: shorter gaps are merged away first. Returns null when there are fewer
 * stretches than sentences (a sentence was skipped, or two were read without a pause).
 */
export function fitSentences(speech, count) {
  const segs = speech.map((s) => ({ ...s }));
  while (segs.length > count) {
    let k = 0;
    for (let i = 1; i < segs.length - 1; i++) if (segs[i + 1].start - segs[i].end < segs[k + 1].start - segs[k].end) k = i;
    segs.splice(k, 2, { start: segs[k].start, end: segs[k + 1].end });
  }
  return segs.length === count ? segs : null;
}
