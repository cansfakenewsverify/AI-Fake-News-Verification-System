// Checks the rendered film against the brief before it is called done.
//
// Usage (from video/hf-presentation):  node tools/verify.mjs [path-to-mp4]
//
// Verifies: duration <= 295 s, streams and frame rate, no black frames, no silent stretch longer
// than ~5 s (with sound effects there should not be one), overall loudness and true peak, and the
// size of the committed web copy. Also writes a contact sheet of evenly spaced frames to the
// scratchpad so the picture can actually be looked at rather than assumed.
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const REPO = path.resolve(ROOT, "..", "..");
const film = process.argv[2] || path.join(REPO, "docs", "demo", "presentation_v1.0.mp4");
const webCopy = path.join(REPO, "code", "frontend", "public", "demo", "presentation_v1.mp4");
const SHEET_DIR = process.env.FNV_SHEETS || path.join(os.tmpdir(), "fnv-verify");

const bin = (name) => {
  const guess = path.join(process.env.LOCALAPPDATA ?? "", "Microsoft", "WinGet", "Packages",
    "Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe", "ffmpeg-9.0.1-full_build", "bin", `${name}.exe`);
  return fs.existsSync(guess) ? guess : name;
};
const run = (exe, args) => spawnSync(exe, args, { encoding: "utf8", maxBuffer: 64 * 1024 * 1024 });

const results = [];
const check = (ok, label, detail) => { results.push({ ok, label, detail }); };

if (!fs.existsSync(film)) {
  console.error(`film not found: ${film}`);
  process.exit(1);
}

// ── container and streams ───────────────────────────────────────────────────
const probe = JSON.parse(run(bin("ffprobe"), ["-v", "error", "-show_format", "-show_streams", "-of", "json", film]).stdout);
const v = probe.streams.find((s) => s.codec_type === "video");
const a = probe.streams.find((s) => s.codec_type === "audio");
const dur = Number(probe.format.duration);
const sizeMB = Number(probe.format.size) / 1e6;
const fps = v ? eval(v.r_frame_rate) : 0; // "30/1"

check(dur <= 295, `片長 ${dur.toFixed(2)} s（上限 295）`, `${Math.floor(dur / 60)}:${(dur % 60).toFixed(1).padStart(4, "0")}`);
check(!!v && v.width === 1920 && v.height === 1080, `畫面 ${v?.width}×${v?.height}`, v?.codec_name);
check(Math.abs(fps - 30) < 0.01, `${fps} fps`, `${v?.nb_frames ?? "?"} 影格`);
check(v?.codec_name === "h264" && v?.pix_fmt === "yuv420p", `視訊編碼 ${v?.codec_name} ${v?.pix_fmt}`, v?.profile);
check(!!a && a.codec_name === "aac" && Number(a.sample_rate) === 48000, `音訊 ${a?.codec_name} ${a?.sample_rate} Hz ${a?.channels}ch`, "");

// ── black frames ────────────────────────────────────────────────────────────
const black = run(bin("ffmpeg"), ["-hide_banner", "-nostats", "-i", film, "-vf", "blackdetect=d=0.25:pic_th=0.98", "-an", "-f", "null", "-"]).stderr;
const blackHits = [...black.matchAll(/black_start:([\d.]+) black_end:([\d.]+)/g)]
  .map((m) => `${Number(m[1]).toFixed(2)}–${Number(m[2]).toFixed(2)}s`);
check(blackHits.length === 0, `黑畫面 ${blackHits.length} 段`, blackHits.join(", "));

// ── long silences ───────────────────────────────────────────────────────────
const sil = run(bin("ffmpeg"), ["-hide_banner", "-nostats", "-i", film, "-af", "silencedetect=n=-50dB:d=4.0", "-vn", "-f", "null", "-"]).stderr;
const silences = [];
let start = null;
for (const m of sil.matchAll(/silence_(start|end): ([\d.-]+)/g)) {
  if (m[1] === "start") start = Number(m[2]);
  else if (start != null) { silences.push([start, Number(m[2])]); start = null; }
}
const long = silences.filter(([s, e]) => e - s > 5).map(([s, e]) => `${s.toFixed(1)}–${e.toFixed(1)}s`);
check(long.length === 0, `超過 5 秒的靜音 ${long.length} 段`, long.join(", "));

// ── loudness ────────────────────────────────────────────────────────────────
const lou = run(bin("ffmpeg"), ["-hide_banner", "-nostats", "-i", film, "-af", "ebur128=peak=true", "-vn", "-f", "null", "-"]).stderr;
const tail = lou.slice(lou.lastIndexOf("Integrated loudness"));
const I = Number((tail.match(/I:\s*(-?[\d.]+) LUFS/) || [])[1]);
const LRA = Number((tail.match(/LRA:\s*(-?[\d.]+) LU/) || [])[1]);
const TP = Number((tail.match(/Peak:\s*(-?[\d.]+) dBFS/) || [])[1]);
check(I <= -14 && I >= -19, `整體響度 ${I} LUFS（目標 −16）`, `LRA ${LRA} LU`);
check(TP <= -1.5, `真實峰值 ${TP} dBFS（上限 −1.5）`, "");

// ── the committed web copy ──────────────────────────────────────────────────
if (fs.existsSync(webCopy)) {
  const wmb = fs.statSync(webCopy).size / 1e6;
  const wp = JSON.parse(run(bin("ffprobe"), ["-v", "error", "-show_format", "-show_streams", "-of", "json", webCopy]).stdout);
  const wv = wp.streams.find((s) => s.codec_type === "video");
  check(wmb < 30, `網站用檔 ${wmb.toFixed(1)} MB（上限 30）`, `${wv?.width}×${wv?.height}`);
  check(Math.abs(Number(wp.format.duration) - dur) < 0.25, `網站用檔片長 ${Number(wp.format.duration).toFixed(2)} s`, "與母片一致");
} else {
  check(false, "網站用檔還沒產生", webCopy);
}

// ── frame spot-checks ───────────────────────────────────────────────────────
fs.rmSync(SHEET_DIR, { recursive: true, force: true });
fs.mkdirSync(SHEET_DIR, { recursive: true });
const sched = JSON.parse(fs.readFileSync(path.join(ROOT, "data", "schedule.json"), "utf8"));
// two frames inside every scene, plus a few extra, so every stage of the film is eyeballed
const stamps = [];
for (const sc of sched.scenes) {
  stamps.push(sc.start + Math.min(3.2, sc.len * 0.25), sc.start + sc.len * 0.6, sc.start + sc.len * 0.88);
}
stamps.sort((x, y) => x - y);
const list = path.join(SHEET_DIR, "frames.txt");
const files = [];
stamps.forEach((t, i) => {
  const out = path.join(SHEET_DIR, `f${String(i).padStart(2, "0")}.png`);
  run(bin("ffmpeg"), ["-hide_banner", "-loglevel", "error", "-y", "-ss", String(t.toFixed(3)), "-i", film, "-frames:v", "1", out]);
  if (fs.existsSync(out)) files.push({ out, t });
});
fs.writeFileSync(list, files.map((f) => `file '${f.out.replace(/\\/g, "/")}'`).join("\n") + "\n");
const cols = 3;
const sheet = path.join(SHEET_DIR, "sheet.png");
run(bin("ffmpeg"), ["-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", list,
  "-vf", `scale=620:-1,tile=${cols}x${Math.ceil(files.length / cols)}:padding=8:color=#7a7a7a`, "-frames:v", "1", sheet]);
check(files.length === stamps.length, `抽樣影格 ${files.length} 張`, sheet);

// ── report ──────────────────────────────────────────────────────────────────
let bad = 0;
for (const r of results) {
  if (!r.ok) bad++;
  console.log(`${r.ok ? "ok  " : "FAIL"}  ${r.label}${r.detail ? `   ${r.detail}` : ""}`);
}
console.log(`\n${film}\n${sizeMB.toFixed(1)} MB · ${results.length - bad}/${results.length} 項通過`);
console.log(`抽樣影格：${SHEET_DIR}`);
process.exit(bad ? 1 : 0);
