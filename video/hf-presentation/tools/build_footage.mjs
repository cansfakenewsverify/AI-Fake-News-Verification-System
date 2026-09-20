// Rebuilds the footage clips used by the compositions from the genuine live-site captures.
//
// Usage (from video/hf-presentation):  node tools/build_footage.mjs [name ...] [--raw <dir>]
//   The raw takes come from tools/capture.mjs; by default they sit in %TEMP%\fnv-presentation-raw
//   (one folder per take, each with frames/meta.json). Override with --raw or $FNV_RAW.
//
// HyperFrames plays <video> at a constant rate only (no speed ramps, no mid-source freezes), so the
// time map in data/plan.json (accelerated loading segments, cut idle ranges, freeze holds) is baked
// into one constant-rate clip per scene here. Output: assets/footage/<name>.mp4 (H.264, 30 fps CFR,
// yuv420p, no audio; git-ignored) and data/footage_map.json (where each piece lands on the clip clock).
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const argv = process.argv.slice(2);
const rawFlag = argv.indexOf("--raw");
const rawDir = rawFlag >= 0 ? argv[rawFlag + 1]
  : process.env.FNV_RAW || path.join(os.tmpdir(), "fnv-presentation-raw");
const only = argv.filter((a, i) => !a.startsWith("--") && !(rawFlag >= 0 && i === rawFlag + 1));
if (!fs.existsSync(rawDir)) {
  console.error(`raw folder not found: ${rawDir}\nRecord it first: node tools/capture.mjs`);
  process.exit(1);
}
const plan = JSON.parse(fs.readFileSync(path.join(ROOT, "data", "plan.json"), "utf8"));
const FPS = plan.fps;
const OUT = path.join(ROOT, "assets", "footage");
const TMP = path.join(ROOT, ".hf-tmp");
fs.mkdirSync(OUT, { recursive: true });
fs.mkdirSync(TMP, { recursive: true });
const fwd = (p) => p.replace(/\\/g, "/");

function ffmpegBin() {
  const guess = path.join(process.env.LOCALAPPDATA ?? "", "Microsoft", "WinGet", "Packages",
    "Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe", "ffmpeg-9.0.1-full_build", "bin", "ffmpeg.exe");
  return process.env.FFMPEG || (fs.existsSync(guess) ? guess : "ffmpeg");
}

function loadTake(take) {
  const dir = path.join(rawDir, take, "frames");
  const meta = JSON.parse(fs.readFileSync(path.join(dir, "meta.json"), "utf8"));
  const frames = meta.stopMotion
    ? meta.frames.map((f) => ({ file: path.join(dir, f.name), rel: f.t }))
    : meta.frames.map((f) => ({ file: path.join(dir, f.name), rel: f.ts - meta.startWall }));
  return frames.sort((a, b) => a.rel - b.rel);
}

/** Same rule as the v0.3.0 cut: an output frame shows the latest captured frame at or before its raw time. */
function mapFrames(frames, pieces, duration) {
  const total = Math.round(duration * FPS);
  const pick = (r) => {
    let lo = 0, hi = frames.length - 1, ans = 0;
    while (lo <= hi) {
      const mid = (lo + hi) >> 1;
      if (frames[mid].rel <= r + 1e-6) { ans = mid; lo = mid + 1; } else hi = mid - 1;
    }
    return frames[ans].file;
  };
  const out = [];
  const marks = [];
  let lastRaw = 0;
  let count = 0;
  const push = (file) => {
    if (out.length && out[out.length - 1].file === file) out[out.length - 1].count++;
    else out.push({ file, count: 1 });
    count++;
  };
  for (const p of pieces) {
    const t0 = count / FPS;
    if (p.hold !== undefined) {
      const f = pick(lastRaw);
      for (let i = 0; i < Math.round(p.hold * FPS); i++) push(f);
      marks.push({ hold: p.hold, t0: +t0.toFixed(3), t1: +(count / FPS).toFixed(3) });
      continue;
    }
    const n = Math.round(((p.to - p.from) / p.speed) * FPS);
    for (let k = 0; k < n; k++) push(pick(p.from + (k * p.speed) / FPS));
    lastRaw = p.to;
    marks.push({ from: p.from, to: p.to, speed: p.speed, label: p.label, t0: +t0.toFixed(3), t1: +(count / FPS).toFixed(3) });
  }
  while (count < total) { out[out.length - 1].count++; count++; }
  while (count > total) {
    const last = out[out.length - 1];
    if (last.count > 1) last.count--; else out.pop();
    count--;
  }
  return { entries: out, marks };
}

const mapOut = {};
for (const [name, spec] of Object.entries(plan.footage)) {
  const { entries, marks } = mapFrames(loadTake(spec.take), spec.pieces, spec.dur);
  mapOut[name] = { take: spec.take, dur: spec.dur, pieces: marks };
  if (only.length && !only.includes(name)) continue;
  const list = path.join(TMP, `${name}.ffconcat`);
  const lines = ["ffconcat version 1.0"];
  for (const e of entries) lines.push(`file '${fwd(e.file)}'`, `duration ${(e.count / FPS).toFixed(6)}`);
  lines.push(`file '${fwd(entries[entries.length - 1].file)}'`);
  fs.writeFileSync(list, lines.join("\n") + "\n", "utf8");
  const dst = path.join(OUT, `${name}.mp4`);
  const r = spawnSync(ffmpegBin(), ["-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", list,
    "-vf", `fps=${FPS},format=yuv420p`, "-c:v", "libx264", "-preset", "slow", "-crf", "13", "-g", String(FPS),
    "-t", String(spec.dur), "-an", "-movflags", "+faststart", dst], { encoding: "utf8", maxBuffer: 64 * 1024 * 1024 });
  if (r.status !== 0) { console.error(`[${name}] ffmpeg failed:\n${r.stderr}`); process.exit(1); }
  console.log(`${name}: ${spec.take} -> ${entries.length} unique captures, ${spec.dur}s, ${(fs.statSync(dst).size / 1e6).toFixed(2)} MB`);
}
fs.writeFileSync(path.join(ROOT, "data", "footage_map.json"), JSON.stringify(mapOut, null, 1) + "\n", "utf8");
fs.rmSync(TMP, { recursive: true, force: true });
console.log("wrote data/footage_map.json");
