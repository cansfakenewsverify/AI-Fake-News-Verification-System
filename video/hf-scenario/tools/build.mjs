// Builds the scenario drama 《轉傳之前》 from data/storyboard.json.
//
// Usage (from video/hf-scenario):  node tools/build.mjs
// Reads:  data/storyboard.json   the shot list (presentations/2026-11_第二次簡報/01_情境劇劇本.md on a time line)
//         data/lines.json        length of every voice clip (tools/tts.py)
//         data/footage_map.json  the live-site clips (tools/build_footage.mjs)
//         data/sfx_lengths.json  the sound effects (tools/sfx.py)
//         raw/*.mp4              the team's live-action clips, when they exist
// Writes: compositions/<shot>.html, compositions/captions.html, compositions/chrome.html, index.html,
//         data/schedule.json, renders/scenario.srt; trimmed live clips in assets/footage/live_*.mp4 and
//         their audio in assets/audio/live/*.wav.
//
// A live shot whose clip is not in raw/ yet is drawn as a placeholder card and its lines are read by an AI
// voice: that is the storyboard preview. Once the clip exists, the clip and the actors' own audio take its
// place; the narrator (旁白) is always the AI voice. Every composition is generated: edit the storyboard.
import fs from "node:fs";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const read = (f, fallback) => (fs.existsSync(f) ? JSON.parse(fs.readFileSync(f, "utf8")) : fallback);
const board = read(path.join(ROOT, "data", "storyboard.json"));
const lineLen = read(path.join(ROOT, "data", "lines.json"), {});
const fmap = read(path.join(ROOT, "data", "footage_map.json"), {});
const sfxLen = read(path.join(ROOT, "data", "sfx_lengths.json"), {});
const FPS = board.fps;
const r3 = (n) => Math.round(n * 1000) / 1000;
const esc = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
const RAW = path.join(ROOT, "raw");

function ffBin(name) {
  const guess = path.join(process.env.LOCALAPPDATA ?? "", "Microsoft", "WinGet", "Packages",
    "Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe", "ffmpeg-9.0.1-full_build", "bin", `${name}.exe`);
  return fs.existsSync(guess) ? guess : name;
}
function probeDur(file) {
  const r = spawnSync(ffBin("ffprobe"), ["-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", file], { encoding: "utf8" });
  return Number(r.stdout.trim());
}

// ── 1. timing: shift overlapping lines, size every shot ────────────────────────
const shots = board.shots.map((s) => {
  const useClip = Boolean(s.clip) && fs.existsSync(path.join(RAW, s.clip));
  let cursor = 0;
  const lines = (s.lines ?? []).map((l, n) => {
    const key = `${s.id}_${n}`;
    const len = l.len ?? lineLen[key]?.dur;
    if (!len) throw new Error(`${key}: no voice clip yet; run tools/tts.py`);
    let at = l.at;
    if (at < cursor + 0.15) {
      console.warn(`! ${key}: moved from ${at}s to ${r3(cursor + 0.25)}s so it does not overlap the line before`);
      at = r3(cursor + 0.25);
    }
    cursor = at + len;
    // In a real clip the actors speak; their audio is the clip's own. The narrator is always the AI voice.
    const voice = l.who === "旁白" || !useClip;
    return { ...l, key, at, len, voice };
  });
  let dur = s.dur;
  if (s.kind === "site") dur = Math.max(dur, fmap[s.footage]?.dur ?? 0);
  if (useClip && s.kind === "live" && !s.trim) dur = Math.max(dur, probeDur(path.join(RAW, s.clip)));
  if (s.trim) dur = s.trim[1] - s.trim[0];
  dur = Math.max(dur, cursor + 0.35);
  return { ...s, useClip, lines, dur: r3(dur) };
});
let clock = 0;
for (const s of shots) {
  s.start = r3(clock);
  clock += s.dur;
}
const TOTAL = r3(clock);
const preview = shots.some((s) => (s.kind === "live" || s.kind === "threads") && !s.useClip);

// ── 2. live clips: trim to the shot, 1080p 30 fps, audio cleaned and levelled ─────
fs.mkdirSync(path.join(ROOT, "assets", "footage"), { recursive: true });
fs.mkdirSync(path.join(ROOT, "assets", "audio", "live"), { recursive: true });
for (const s of shots.filter((x) => x.useClip)) {
  const src = path.join(RAW, s.clip);
  const [tin, tout] = s.trim ?? [0, s.dur];
  const dst = path.join(ROOT, "assets", "footage", `live_${s.id}.mp4`);
  const wav = path.join(ROOT, "assets", "audio", "live", `${s.id}.wav`);
  const vertical = s.kind === "threads";
  const vf = vertical
    ? `fps=${FPS},scale=780:-2,format=yuv420p`
    : `fps=${FPS},scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,format=yuv420p`;
  const run = (args) => {
    const r = spawnSync(ffBin("ffmpeg"), ["-hide_banner", "-loglevel", "error", "-y", ...args], { encoding: "utf8" });
    if (r.status !== 0) throw new Error(`${s.id}: ffmpeg failed\n${r.stderr}`);
  };
  run(["-ss", String(tin), "-t", String(tout - tin), "-i", src, "-vf", vf, "-c:v", "libx264", "-preset", "medium", "-crf", "16", "-an", "-movflags", "+faststart", dst]);
  if (!vertical) run(["-ss", String(tin), "-t", String(tout - tin), "-i", src, "-af", "highpass=f=90,afftdn=nf=-25,loudnorm=I=-16:TP=-1.5:LRA=11", "-ar", "48000", "-ac", "2", wav]);
  console.log(`${s.id}: clip ${s.clip} [${tin}–${tout}]`);
}

// ── 3. shared pieces ─────────────────────────────────────────────────────────
const sceneChip = (s) => (s.scene ? `<div class="sc-chip" id="${s.id}-chip">${esc(s.scene)}</div>` : "");
const sceneChipJs = (s) => (s.scene ? `tl.fromTo($("#${s.id}-chip"), { opacity: 0, y: -10 }, { opacity: 1, y: 0, duration: 0.3, ease: "power2.out" }, 0.05);` : "");
const COMMON_CSS = `
        .sc-chip { position: absolute; left: 56px; top: 40px; padding: 8px 22px 9px; border-radius: 999px; background: rgba(17,17,17,0.82);
          color: #fff; font-size: 26px; line-height: 34px; font-weight: 700; letter-spacing: 0.04em; z-index: 5; }
        .ph { position: absolute; top: 72px; width: 440px; height: 924px; box-sizing: border-box; border: 12px solid #111111;
          border-radius: 58px; background: #ffffff; overflow: hidden; box-shadow: 0 30px 70px rgba(17,17,17,0.18); }
        .ph-screen { position: absolute; inset: 0; overflow: hidden; }
        .tag { position: absolute; padding: 8px 20px 9px; border-radius: 999px; background: #111111; color: #fff;
          font-size: 24px; line-height: 32px; font-weight: 700; white-space: nowrap; z-index: 6; }
        .tag-soft { background: #ffffff; color: #111111; box-shadow: 0 0 0 2px #d4d4d8; }
        .chips { position: absolute; right: 56px; top: 130px; display: flex; flex-direction: column; align-items: flex-end; gap: 18px; z-index: 5; }
        .chip { padding: 14px 28px 15px; border-radius: 18px; background: #ffffff; color: #111111;
          font-size: 40px; line-height: 50px; font-weight: 700; box-shadow: 0 10px 30px rgba(0,0,0,0.25); opacity: 0; }
        .chip b { display: inline-block; margin-right: 14px; color: #111111; }`;

const chipsHtml = (s) =>
  s.chips?.length && !s.template
    ? `<div class="chips">${s.chips.map((c, i) => `<div class="chip" id="${s.id}-c${i}"><b>✓</b>${esc(c.text)}</div>`).join("")}</div>`
    : "";
const chipsJs = (s) =>
  s.chips?.length && !s.template
    ? s.chips.map((c, i) => `tl.fromTo($("#${s.id}-c${i}"), { opacity: 0, x: 40 }, { opacity: 1, x: 0, duration: 0.45, ease: "power3.out" }, ${c.at});`).join("\n          ")
    : "";

// ── 4. one composition per shot ──────────────────────────────────────────────
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
    if (s.timer) {
      const t = s.timer;
      overlays.push(`<div class="ov-timer" id="${s.id}-tmr"><span class="ov-k">查了</span><span class="ov-n" id="${s.id}-tmrn">00:00</span></div>`);
      js.push(`tl.fromTo($("#${s.id}-tmr"), { opacity: 0 }, { opacity: 1, duration: 0.3 }, ${t.at});`);
      const [mm] = t.to.split(":").map(Number);
      js.push(`(function(){ const el = $("#${s.id}-tmrn"); const box = { v: 0 }; tl.to(box, { v: ${mm * 60}, duration: ${t.dur}, ease: "power1.in",
            onUpdate: () => { const v = Math.round(box.v); el.textContent = String(Math.floor(v / 60)).padStart(2, "0") + ":" + String(v % 60).padStart(2, "0"); } }, ${t.at}); })();`);
    }
    let body;
    if (s.useClip) {
      body = `<video id="${s.id}-v" class="lv-video" src="assets/footage/live_${s.id}.mp4" data-start="0" data-duration="${s.dur}" data-track-index="0" muted playsinline></video>`;
    } else if (s.split) {
      body = `<div class="lv-split">
          <div class="lv-half"><div class="lv-tag">實拍 ${s.id}b</div><div class="lv-desc">小翔（宿舍）講電話</div></div>
          <div class="lv-half"><div class="lv-tag">實拍 ${s.id}a</div><div class="lv-desc">阿嬤（客廳）講電話</div></div>
        </div>`;
    } else {
      body = `<div class="lv-card"><div class="lv-tag">實拍 ${s.id}</div><div class="lv-desc">${esc(s.desc)}</div><div class="lv-note">組員拍的畫面會放在這裡</div></div>`;
    }
    return {
      css: `
        #root { background: #23262b; }
        .lv-video { position: absolute; inset: 0; width: 1920px; height: 1080px; object-fit: cover; }
        .lv-card { position: absolute; left: 120px; top: 250px; width: 1180px; height: 470px; box-sizing: border-box; padding: 54px 70px;
          border: 3px dashed rgba(255,255,255,0.28); border-radius: 36px; color: #fff; }
        .lv-tag { display: inline-block; padding: 8px 22px; border-radius: 12px; background: #ffffff; color: #111111; font-size: 30px; line-height: 38px; font-weight: 700; }
        .lv-desc { margin-top: 30px; font-size: 54px; line-height: 76px; font-weight: 700; }
        .lv-note { margin-top: 26px; font-size: 28px; line-height: 38px; color: rgba(255,255,255,0.55); }
        .lv-split { position: absolute; inset: 0; display: grid; grid-template-columns: 1fr 1fr; gap: 8px; background: #111; }
        .lv-half { position: relative; background: #23262b; padding: 300px 70px 0; color: #fff; }
        .ov-counter, .ov-timer { position: absolute; right: 60px; top: 40px; display: flex; align-items: baseline; gap: 14px; padding: 14px 30px 16px;
          border-radius: 20px; background: #ffffff; color: #111111; box-shadow: 0 12px 34px rgba(0,0,0,0.3); z-index: 5; opacity: 0; }
        .ov-k { font-size: 34px; line-height: 44px; font-weight: 700; }
        .ov-n { display: inline-block; min-width: 40px; text-align: center; font-size: 72px; line-height: 80px; font-weight: 700; font-variant-numeric: tabular-nums; }`,
      html: `${body}\n        ${overlays.join("\n        ")}`,
      js: js.join("\n          "),
    };
  },

  chat(s) {
    const avatar = (who) => esc(who.slice(-1));
    const msgs = s.messages.map((m, i) => {
      const id = `${s.id}-m${i}`;
      if (m.link) {
        return `<div class="ch-row self" id="${id}"><div class="ch-link"><img src="assets/og.png" alt="" />
              <div class="ch-link-t">全民查證公社</div><div class="ch-link-d">貼上訊息，10 秒知道真假</div><div class="ch-link-u">${esc(m.link.site)}</div></div></div>`;
      }
      if (m.self) return `<div class="ch-row self" id="${id}"><div class="ch-b">${esc(m.text)}</div></div>`;
      return `<div class="ch-row" id="${id}"><div class="ch-av">${avatar(m.from)}</div><div><div class="ch-name">${esc(m.from)}</div><div class="ch-b">${esc(m.text)}</div></div></div>`;
    });
    return {
      css: `
        #root { background: #eceef1; }
        .ph { left: 740px; }
        .ch-top { position: absolute; left: 0; right: 0; top: 0; height: 120px; background: #ffffff; border-bottom: 2px solid #e4e4e7; }
        .ch-title { position: absolute; left: 30px; right: 30px; top: 58px; font-size: 27px; line-height: 36px; font-weight: 700; text-align: center; }
        .ch-sub { position: absolute; left: 0; right: 0; top: 92px; font-size: 18px; color: #6b7280; text-align: center; }
        .ch-list { position: absolute; left: 0; right: 0; top: 120px; bottom: 0; padding: 26px 22px; background: #f2f4f7;
          display: flex; flex-direction: column; gap: 22px; }
        .ch-row { display: flex; gap: 14px; align-items: flex-start; opacity: 0; }
        .ch-row.self { justify-content: flex-end; }
        .ch-av { flex: none; width: 54px; height: 54px; border-radius: 50%; background: #3f3f46; color: #fff; font-size: 26px; line-height: 54px;
          text-align: center; font-weight: 700; }
        .ch-name { font-size: 19px; line-height: 26px; color: #6b7280; margin-bottom: 4px; }
        .ch-b { max-width: 300px; padding: 14px 18px; border-radius: 22px; background: #ffffff; font-size: 24px; line-height: 35px; color: #111111;
          box-shadow: 0 1px 0 rgba(0,0,0,0.06); }
        .self .ch-b { background: #dcebff; }
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
        </div></div>`,
      js: s.messages.map((m, i) => `tl.fromTo($("#${s.id}-m${i}"), { opacity: 0, y: 24, scale: 0.96 }, { opacity: 1, y: 0, scale: 1, duration: 0.35, ease: "back.out(1.6)" }, ${m.at});`).join("\n          "),
      sfx: s.messages.map((m) => ({ sound: m.self ? "pop" : "ding", at: m.at })),
    };
  },

  sms(s) {
    return {
      css: `
        #root { background: #eceef1; }
        .ph { left: 740px; }
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
        <div class="tag tag-soft" style="left: 1240px; top: 470px">電話號碼已遮蔽</div>`,
      js: `tl.fromTo($("#${s.id}-b"), { opacity: 0, y: 24 }, { opacity: 1, y: 0, duration: 0.4, ease: "back.out(1.6)" }, 0.4);`,
      sfx: [{ sound: "buzz", at: 0.3 }],
    };
  },

  site(s) {
    const pieces = fmap[s.footage]?.pieces ?? [];
    const fast = pieces.filter((p) => p.speed > 1);
    return {
      css: `
        #root { background: #f7f7f8; }
        .ph { left: 740px; }
        .ph video { position: absolute; left: 0; top: 0; width: 416px; height: 900px; object-fit: cover; object-position: top; }
        .st-title { position: absolute; left: 160px; top: 420px; width: 520px; font-size: 56px; line-height: 72px; font-weight: 700; }
        .st-calls { position: absolute; left: 1240px; top: 260px; width: 600px; display: flex; flex-direction: column; gap: 30px; }
        .st-call { display: flex; align-items: center; gap: 22px; opacity: 0; }
        .st-num { flex: none; width: 64px; height: 64px; border-radius: 50%; background: #111111; color: #fff; font-size: 34px; line-height: 64px;
          text-align: center; font-weight: 700; }
        .st-txt { font-size: 42px; line-height: 54px; font-weight: 700; }`,
      html: `<div class="st-title" id="${s.id}-t">${esc(s.title ?? "")}</div>
        <div class="ph"><div class="ph-screen">
          <video id="${s.id}-v" src="assets/footage/${s.footage}.mp4" data-start="0" data-duration="${fmap[s.footage]?.dur ?? s.dur}" data-track-index="0" muted playsinline></video>
        </div></div>
        <div class="tag" style="left: 1240px; top: 120px">正式站實錄</div>
        ${fast.map((p, i) => `<div class="tag tag-soft" id="${s.id}-sp${i}" style="left: 1450px; top: 120px; opacity: 0">${esc(p.label)}</div>`).join("\n        ")}
        <div class="st-calls">
          ${s.callouts.map((c, i) => `<div class="st-call" id="${s.id}-k${i}"><div class="st-num">${i + 1}</div><div class="st-txt">${esc(c.text)}</div></div>`).join("\n          ")}
        </div>`,
      js: [
        `tl.fromTo($("#${s.id}-t"), { opacity: 0, x: -30 }, { opacity: 1, x: 0, duration: 0.5, ease: "power3.out" }, 0.2);`,
        ...fast.map((p, i) => `tl.set($("#${s.id}-sp${i}"), { opacity: 1 }, ${p.t0}); tl.set($("#${s.id}-sp${i}"), { opacity: 0 }, ${p.t1});`),
        ...s.callouts.map((c, i) => `tl.fromTo($("#${s.id}-k${i}"), { opacity: 0, x: 40 }, { opacity: 1, x: 0, duration: 0.45, ease: "power3.out" }, ${c.at});`),
      ].join("\n          "),
    };
  },

  threads(s) {
    if (s.useClip) {
      return {
        css: `#root { background: #f7f7f8; } .ph { left: 740px; } .ph video { position: absolute; left: 0; top: 0; width: 416px; height: 900px; object-fit: cover; object-position: top; }`,
        html: `<div class="ph"><div class="ph-screen"><video id="${s.id}-v" src="assets/footage/live_${s.id}.mp4" data-start="0" data-duration="${s.dur}" data-track-index="0" muted playsinline></video></div></div>
        <div class="tag" style="left: 1240px; top: 120px">Threads 實錄・帳號已遮蔽</div>`,
        js: "",
      };
    }
    const cm = (s.comments ?? []).map((c, i) => `<div class="th-c" id="${s.id}-cm${i}"><div class="th-av"></div><div><div class="th-n">${esc(c.author)}</div><div class="th-t">${esc(c.text)}</div></div></div>`);
    const mention = s.mention
      ? `<div class="th-c" id="${s.id}-mn"><div class="th-av dark"></div><div><div class="th-n">${esc(s.mention.author)}</div><div class="th-t th-at">${esc(s.mention.text)}</div></div></div>`
      : "";
    const reply = s.reply
      ? `<div class="th-c th-bot" id="${s.id}-rp"><div class="th-av bot">查</div><div><div class="th-n">factcheck_tw_bot</div>${s.reply.lines.map((l, i) => `<div class="th-r${i === 0 ? " th-r0" : ""}">${i === 0 ? '<span class="fnv-emoji">🔴</span>' + esc(l.replace("🔴", "")) : esc(l)}</div>`).join("")}</div></div>`
      : "";
    const js = [];
    (s.comments ?? []).forEach((c, i) => js.push(`tl.fromTo($("#${s.id}-cm${i}"), { opacity: 0, y: 20 }, { opacity: 1, y: 0, duration: 0.35, ease: "power3.out" }, ${c.at});`));
    if (s.mention) js.push(`tl.fromTo($("#${s.id}-mn"), { opacity: 0, y: 20 }, { opacity: 1, y: 0, duration: 0.35, ease: "power3.out" }, ${s.mention.at});`);
    if (s.speedup) js.push(`tl.set($("#${s.id}-sp"), { opacity: 1 }, ${s.speedup.at}); tl.set($("#${s.id}-sp"), { opacity: 0 }, ${r3(s.speedup.at + s.speedup.dur)});`);
    if (s.reply) js.push(`tl.fromTo($("#${s.id}-rp"), { opacity: 0, y: 30 }, { opacity: 1, y: 0, duration: 0.45, ease: "back.out(1.4)" }, ${s.reply.at});`);
    return {
      css: `
        #root { background: #f7f7f8; }
        .ph { left: 740px; }
        .th-top { position: absolute; left: 0; right: 0; top: 0; height: 96px; border-bottom: 2px solid #ececec; text-align: center; font-size: 24px; line-height: 150px; font-weight: 700; }
        .th-list { position: absolute; left: 0; right: 0; top: 96px; bottom: 0; padding: 22px 22px; display: flex; flex-direction: column; gap: 18px; }
        .th-post { padding-bottom: 18px; border-bottom: 2px solid #ececec; }
        .th-c { display: flex; gap: 14px; align-items: flex-start; opacity: 0; }
        .th-post .th-c { opacity: 1; }
        .th-av { flex: none; width: 46px; height: 46px; border-radius: 50%; background: #c4c4c8; }
        .th-av.dark { background: #3f3f46; }
        .th-av.bot { background: #111111; color: #fff; font-size: 22px; line-height: 46px; text-align: center; font-weight: 700; }
        .th-n { font-size: 19px; line-height: 26px; font-weight: 700; }
        .th-t { font-size: 23px; line-height: 33px; }
        .th-at { color: #1d4ed8; }
        .th-bot { padding: 14px; border-radius: 18px; background: #f4f4f5; }
        .th-r { font-size: 19px; line-height: 28px; word-break: break-all; }
        .th-r0 { font-size: 23px; line-height: 32px; font-weight: 700; }`,
      html: `<div class="ph"><div class="ph-screen">
          <div class="th-top">Threads</div>
          <div class="th-list">
            <div class="th-post"><div class="th-c"><div class="th-av"></div><div><div class="th-n">${esc(s.post.author)}</div><div class="th-t">${esc(s.post.text)}</div></div></div></div>
            ${cm.join("\n            ")}
            ${mention}
            ${reply}
          </div>
        </div></div>
        <div class="tag" style="left: 1240px; top: 120px">示意畫面：正式片換成 Threads 實錄</div>
        ${s.speedup ? `<div class="tag tag-soft" id="${s.id}-sp" style="left: 1240px; top: 190px; opacity: 0">${esc(s.speedup.label)}</div>` : ""}`,
      js: js.join("\n          "),
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
  freeze: (s) => ({
    css: `
        #root { background: #1b1d21; }
        .fz-list { position: absolute; left: 0; right: 0; top: 230px; display: flex; flex-direction: column; align-items: center; gap: 26px; }
        .fz { padding: 16px 40px 18px; border-radius: 20px; background: #ffffff; color: #111111; font-size: 60px; line-height: 74px; font-weight: 700; opacity: 0; }`,
    html: `<div class="fz-list">${s.chips.map((c, i) => `<div class="fz" id="${s.id}-z${i}">${esc(c)}</div>`).join("")}</div>`,
    js: s.chips.map((c, i) => `tl.fromTo($("#${s.id}-z${i}"), { opacity: 0, y: 26 }, { opacity: 1, y: 0, duration: 0.35, ease: "power3.out" }, ${r3(0.4 + i * 1.25)});`).join("\n          "),
    sfx: s.chips.map((c, i) => ({ sound: "tick", at: r3(0.4 + i * 1.25) })),
  }),
  rewind: (s) => {
    const back = ["S07", "S06", "S05", "S04", "S03", "S02", "S01"];
    return {
      css: `
        #root { background: #0e0f11; }
        .rw-lines { position: absolute; inset: 0; background: repeating-linear-gradient(0deg, rgba(255,255,255,0.05) 0 2px, rgba(0,0,0,0) 2px 6px); z-index: 3; }
        .rw-hud { position: absolute; left: 70px; top: 60px; color: #fff; font-size: 52px; line-height: 60px; font-weight: 700; letter-spacing: 0.1em; z-index: 4; }
        .rw-fl { position: absolute; left: 560px; top: 330px; width: 800px; height: 300px; border-radius: 24px; background: #2b2f36; color: rgba(255,255,255,0.8);
          font-size: 64px; line-height: 300px; text-align: center; font-weight: 700; opacity: 0; }
        .rw-q { position: absolute; left: 0; right: 0; top: 470px; text-align: center; color: #fff; font-size: 74px; line-height: 90px; font-weight: 700; opacity: 0; z-index: 4; }`,
      html: `<div class="rw-lines"></div><div class="rw-hud" id="${s.id}-hud">◀◀ 倒帶</div>
        ${back.map((b, i) => `<div class="rw-fl" id="${s.id}-f${i}">${b}</div>`).join("\n        ")}
        <div class="rw-q" id="${s.id}-q">如果，轉傳之前先查一下……</div>`,
      js: [
        `tl.fromTo($("#${s.id}-hud"), { opacity: 0 }, { opacity: 1, duration: 0.15, repeat: 5, yoyo: true }, 0.0);`,
        ...back.map((b, i) => `tl.set($("#${s.id}-f${i}"), { opacity: 1, x: ${i % 2 ? 14 : -14} }, ${r3(0.1 + i * 0.22)}); tl.set($("#${s.id}-f${i}"), { opacity: 0 }, ${r3(0.1 + (i + 1) * 0.22)});`),
        `tl.fromTo($("#${s.id}-q"), { opacity: 0, y: 20 }, { opacity: 1, y: 0, duration: 0.6, ease: "power3.out" }, 2.0);`,
      ].join("\n          "),
    };
  },
  compare: (s) => ({
    css: `
        #root { background: #f7f7f8; }
        .cp-h { position: absolute; left: 150px; top: 70px; font-size: 60px; line-height: 76px; font-weight: 700; }
        .cp { position: absolute; left: 150px; top: 190px; width: 1620px; border-collapse: collapse; }
        .cp th { font-size: 32px; line-height: 44px; text-align: left; padding: 10px 24px; color: #3f3f46; }
        .cp td { font-size: 36px; line-height: 48px; padding: 20px 24px; border-top: 2px solid #d4d4d8; vertical-align: top; }
        .cp td.k { width: 230px; font-weight: 700; }
        .cp td.b { width: 560px; color: #6b7280; }
        .cp td.a { font-weight: 700; }
        .cp tr.r { opacity: 0; }`,
    html: `<div class="cp-h" id="${s.id}-h">用之前 vs. 用之後</div>
        <table class="cp"><tr><th></th><th>使用前</th><th>使用全民查證公社之後</th></tr>
          ${s.rows.map((r, i) => `<tr class="r" id="${s.id}-r${i}"><td class="k">${esc(r[0])}</td><td class="b">${esc(r[1])}</td><td class="a">${esc(r[2])}</td></tr>`).join("\n          ")}
        </table>`,
    js: [`tl.fromTo($("#${s.id}-h"), { opacity: 0, y: -16 }, { opacity: 1, y: 0, duration: 0.45, ease: "power3.out" }, 0.2);`,
      ...s.rows.map((r, i) => `tl.fromTo($("#${s.id}-r${i}"), { opacity: 0, x: -30 }, { opacity: 1, x: 0, duration: 0.45, ease: "power3.out" }, ${r3(1.2 + i * 2.6)});`)].join("\n          "),
  }),
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

const compo = (s, k) => `<!doctype html>
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
        ${chipsHtml(s)}
        ${sceneChip(s)}
      </div>
      <script>
        (function () {
          const root = document.querySelector('[data-composition-id="${s.id}"]');
          const $ = (sel) => root.querySelector(sel);
          const tl = gsap.timeline({ paused: true });
          ${sceneChipJs(s)}
          ${k.js}
          ${chipsJs(s)}
          window.__timelines["${s.id}"] = tl;
        })();
      </script>
    </template>
  </body>
</html>
`;

fs.mkdirSync(path.join(ROOT, "compositions"), { recursive: true });
const sfxEvents = [];
for (const s of shots) {
  const k = KIND[s.kind](s);
  fs.writeFileSync(path.join(ROOT, "compositions", `${s.id}.html`), compo(s, k), "utf8");
  for (const e of [...(s.sfx ?? []), ...(k.sfx ?? [])]) sfxEvents.push({ sound: e.sound, t: r3(s.start + e.at) });
}

// ── 5. captions ──────────────────────────────────────────────────────────────
const cues = [];
for (const s of shots) {
  for (const l of s.lines) cues.push({ shot: s.id, who: l.who, off: l.off, text: l.text, start: r3(s.start + l.at), end: r3(s.start + l.at + l.len - 0.3) });
}
cues.forEach((c, i) => {
  const next = cues[i + 1];
  c.in = r3(Math.max(0, c.start - 0.06));
  c.out = r3(Math.min(c.end + 0.25, next ? next.start - 0.08 : TOTAL - 0.05));
});
const label = (c) => (c.who === "旁白" ? "" : `<span class="cap-who">${esc(c.who)}${c.off ? "（畫外）" : ""}</span>`);
const captions = `<!doctype html>
<!-- GENERATED by tools/build.mjs. One caption group per line; one group visible at a time. -->
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
fs.writeFileSync(path.join(ROOT, "compositions", "captions.html"), captions, "utf8");

// ── 6. chrome: the preview watermark while placeholder cards remain ──────────────
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
        ${preview ? '<div class="wm">分鏡預覽版：真人鏡頭為佔位字卡、台詞為 AI 語音</div>' : ""}
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
fs.writeFileSync(path.join(ROOT, "compositions", "chrome.html"), chrome, "utf8");

// ── 7. index.html ────────────────────────────────────────────────────────────
const host = (id, start, dur, track, kind = "graphics") => `      <div id="el-${id}" class="clip" data-composition-id="${id}" data-composition-src="compositions/${id}.html"
        data-start="${start}" data-duration="${dur}" data-track-index="${track}" data-track-kind="${kind}" data-width="1920" data-height="1080"></div>`;
const fade = (len) => esc(JSON.stringify({ version: 1, lanes: [{ target: "volume", points: [{ t: 0, v: 0 }, { t: 0.05, v: 1 }, { t: r3(len - 0.15), v: 1 }, { t: r3(len), v: 0 }] }] }));
const voices = [];
for (const s of shots) {
  for (const l of s.lines.filter((x) => x.voice)) {
    voices.push(`      <audio id="vo-${l.key}" src="assets/audio/lines/${l.key}.wav" data-start="${r3(s.start + l.at)}" data-duration="${l.len}"
        data-track-index="${l.who === "旁白" ? 20 : 19}" data-volume="1" data-automation="${fade(l.len)}"></audio>`);
  }
  if (s.useClip && s.kind === "live") {
    voices.push(`      <audio id="live-${s.id}" src="assets/audio/live/${s.id}.wav" data-start="${s.start}" data-duration="${s.dur}" data-track-index="18" data-volume="1"></audio>`);
  }
}
const SFX_TRACK = { click: 21, tick: 22, chime: 23, whoosh: 24, ding: 25, pop: 26, buzz: 27, rewind: 28 };
const SFX_GAIN = { click: 0.5, tick: 0.4, chime: 0.55, whoosh: 0.5, ding: 0.6, pop: 0.5, buzz: 0.6, rewind: 0.6 };
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

      <!-- voices: narrator (track 20), AI stand-ins for the actors (19), the actors' own audio (18) -->
${voices.join("\n")}

      <!-- sound effects (tracks 21-28), synthesised by tools/sfx.py -->
${sfxEls.join("\n")}
    </div>
    <script>
      window.__timelines["main"] = gsap.timeline({ paused: true });
    </script>
  </body>
</html>
`;
fs.writeFileSync(path.join(ROOT, "index.html"), index, "utf8");

// ── 8. schedule + srt ────────────────────────────────────────────────────────
fs.writeFileSync(path.join(ROOT, "data", "schedule.json"), JSON.stringify({ total: TOTAL, preview, shots: shots.map((s) => ({ id: s.id, kind: s.kind, start: s.start, dur: s.dur, clip: s.useClip })), cues }, null, 1) + "\n", "utf8");
const ts = (t) => {
  const ms = Math.round(t * 1000);
  const h = Math.floor(ms / 3600000), m = Math.floor((ms % 3600000) / 60000), sec = Math.floor((ms % 60000) / 1000), r = ms % 1000;
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:${String(sec).padStart(2, "0")},${String(r).padStart(3, "0")}`;
};
fs.mkdirSync(path.join(ROOT, "renders"), { recursive: true });
fs.writeFileSync(path.join(ROOT, "renders", "scenario.srt"),
  cues.map((c, i) => `${i + 1}\n${ts(c.in)} --> ${ts(c.out)}\n${c.who === "旁白" ? "" : c.who + "："}${c.text}\n`).join("\n"), "utf8");

for (const s of shots) console.log(`${s.id.padEnd(5)} ${s.kind.padEnd(8)} ${String(s.start).padStart(7)} +${s.dur}${s.useClip ? "  (clip)" : ""}`);
console.log(`total ${TOTAL}s (${Math.floor(TOTAL / 60)}:${String(Math.round(TOTAL % 60)).padStart(2, "0")}) · ${shots.length} shots · ${cues.length} captions · ${sfxEvents.length} sfx${preview ? " · storyboard preview" : ""}`);
if (TOTAL > 295) console.warn(`! longer than 4:55 (the limit is 5 minutes)`);
