# Brief: 5-minute recorded presentation video — "開箱" style (2026-09-20, revision 2)

## What the advisor asked for (his words, 2026-09-20)

- 「就是用預先錄製且時間最長為五分鐘的影片來進行簡報」 — the course presentation (9/21–9/23) IS this video. Two
  professors watch it on site and grade it; a third grades later from GitHub.
- 「影片要有聲音旁白，用有聲音（和音效）的影片來介紹整個系統的功能與所有操作及輸出入過程。」
- 「等於是你們事先錄製好的一段簡報與操作說明」
- 「想看看，當你們上網看別人的產品介紹與操作功能展示時，網路網紅都會怎麼拍——等於是你們系統的開箱文」

So: **one video, hard limit 5:00 (aim for 4:40–4:55)**, narrated, with sound effects, that works like a product
"unboxing": show EVERY function, every operation, and what goes in and what comes out. It is a product tour first
and a slide talk second. The existing demo_v0.4.0 (2:37) is a starting point, not the answer: it skips several
functions and spends time on statistics.

## Where to work

- Working copy: `C:\Users\user\Desktop\AI-Fake-News-Verification-System` (the project moved here on 2026-09-19).
  NEVER read from or write to `C:\Users\user\OneDrive\桌面\AI-Fake-News-Verification-System`.
  Your shell may start in the old folder: always `cd` to the working copy or use absolute paths.
- HyperFrames project: `video\hf-demo\` (your v0.4.0 project). Check first that the git-ignored media survived the
  move (`assets/footage`, `assets/audio`, `.hyperframes` cache).
- Python: `code\backend\venv\Scripts\python.exe` (use `python -m ...`; the .exe launchers broke in the move).
- ffmpeg: `C:\Users\user\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-9.0.1-full_build\bin\`
- Keep demo_v0.4.0 reproducible: build the new film as a separate entry or a sibling project
  (`video\hf-presentation\`) that reuses scene files. Do not break `npm run render` for v0.4.0.

## New footage: record the LIVE site

The system is live since 2026-09-19: **https://fakenewsverify.vercel.app** (Vercel → Render → Supabase, AI through
the university gateway). Record the real production site with headless Edge over CDP, the way the v0.3.0/v0.4.0
captures were made, desktop 1280-wide and phone 390×844. Show the real URL in the frame chrome: it proves the
system is online.

- The backend is a free instance that sleeps after 15 idle minutes: hit `https://fakenewsverify.vercel.app/api/health`
  first and wait until it answers 200 before recording.
- Budget: at most **12 new AI verifications** on the live site for the whole job (there is a 300/day cap shared with
  real users; each costs the school about USD 0.006). Cached queries are free. Prefer inputs that are already in
  the knowledge base when you only need to show the flow.
- Do not submit anything other than verification inputs on our own site. No sign-ins anywhere. If you open the
  "share to Threads" link, stop at the Threads page that asks to log in — do not log in; a frame of our button and the
  composed intent URL/text is enough.
- The Threads bot is NOT running in the cloud (THREADS_MODE=off there). Reuse the v0.4.0 simulation footage /
  redraw for that part and keep the 模擬模式 label on screen the whole time.
- Real data only on screen: no mock results dressed up as real ones. Labels for sped-up footage and redrawn terminal
  output stay, as in v0.4.0.

## Content: every function, every operation, input → output (target timings; total ≤ 4:55)

1. **Cold open + title, 0:00–0:25.** A suspicious message arrives ("健保卡即日起停用…" with the URL masked, as in
   s01). "這種訊息你一定收過。今天帶大家開箱我們做的系統。" Title card: formal title 「AI 為核心的假訊息驗證系統」, system
   name 「全民查證公社」, 長庚大學資訊工程學系 軟硬體專題, team 廖晢勛、石岱勳、姚睿、張宇宏、廖育翔 (exactly these characters: 育, not 昱),
   指導教授 黃崇源, site URL.
2. **Text check, the core flow, 0:25–1:15.** Home page tour in one breath (tabs 文字／網址, counter 0/20000, example
   chips, "最近查證"). Paste a message → 「開始查證」 → the three-step progress (檢查快取 → 讀取內容 → AI 判讀, it only moves
   forward) → result page. Walk the OUTPUT top to bottom: the coloured verdict block (red / yellow / green and what
   each means), confidence chip, 「AI 即時判定」 chip, the yellow 「尚無查核機構證實」 banner when no fact-check source
   exists, 你查的內容, 判讀摘要, 詳細說明 (open the disclosure), 查核來源 with their tier labels, then the three actions:
   分享到 Threads, 複製連結 (show the toast), 再查一則. Say that every result has its own shareable address `/r/<id>`.
3. **URL check, 1:15–1:40.** Switch to the 網址 tab, paste a news/fact-check URL, show that the system reads the page
   itself and then judges it; show one input error in passing (「這不是有效的網址」) so the viewer sees input validation.
4. **The three-layer cache, 1:40–2:15.** Same text again → instant answer with the 「快取」 chip; the same rumour in
   different words → 「語意相似」 chip (the vector layer; reuse the s07 0.80 vs 0.75 visual if it still fits). One
   sentence on why: repeated rumours cost no AI calls.
5. **Trending wall and knowledge base, 2:15–2:50.** /trending: where the items come from (MyGoPen, 台灣事實查核中心,
   Cofacts), the 全部／未查證 filter, open one item. /knowledge: type a keyword, use the 詐騙／假訊息／安全／無法查證
   filters, the hit counter and source domain on each card.
6. **Small things people notice, 2:50–3:05.** Dark / light toggle, phone layout with the bottom tab bar, the
   privacy and data-deletion pages in the footer, no login needed and history stays in the browser.
7. **Threads bot, 3:05–3:40.** Simulated loop from v0.4.0, shortened: someone tags @factcheck_tw_bot under a
   suspicious post → the bot replies with the light, one-line summary, source and the result-page link → open that
   link on the phone. Say plainly: this part is a simulation; going public needs Meta's App Review.
8. **Under the hood, 3:40–4:10.** One animated diagram: browser → Vercel → Render (FastAPI) → Supabase (Postgres +
   pgvector) and the university's CGU AIR gateway (`gpt-5.4-mini`); the pipeline hash → vector (0.75, verified rows
   only) → AI; the source rule ("只有已經做出判定的查核來源才算數"); the guards (300 AI calls a day, per-IP rate
   limit, upload size limit). Live since 2026-09-19: nobody's computer has to stay on.
9. **Does it work? 4:10–4:35.** Evaluation on 150 labelled messages: previous model 96.0% → current model 100%, no
   risky message judged safe in either run. Automated tests: backend 700, frontend 385, run on every push. Test
   plan: 46 items, P0 27/30 after the re-test; say the open one plainly — the semantic-cache hit rate is 65% against
   a 70% target and we did not lower the threshold to pass.
10. **Close, 4:35–4:55.** Next: real Threads integration, a larger evaluation set. End card: site URL, GitHub
    `github.com/cansfakenewsverify/AI-Fake-News-Verification-System`, 「謝謝各位老師」.

If time runs short, trim 8 and 9 before trimming 2–7: the advisor asked for functions, operations and input/output.
Numbers above are verified as of 2026-09-20 (test plan v1.5 §6.5, README). Do not show other numbers unless you
verify them in `docs/test/TP-FNV-2026-01.md` or `README.md`. The v0.4.0 numbers card (478 / 375) is outdated.

## Look and sound

- Tone: a friendly product walkthrough in first person plural ("我們"), conversational Taiwanese Mandarin, short
  sentences, the way a good tech reviewer explains a product — but no hype words, no exaggeration, nothing the
  system cannot do. Every claim on screen must be true.
- Picture: the real UI is the star. Use the v0.4.0 devices (virtual camera zoom and pan inside the capture, ink
  outline rings around the control being used, a magnifier for small text, a cursor that is easy to follow, short
  on-screen labels naming the input and the output). Light background, ink `#111111`, red / yellow / green only for
  verdicts. Nothing under ~28 px for body text at 1080p. One idea per scene.
- Narration: edge-tts `zh-TW-YunJheNeural`, rate +8% to +12%. A teammate may re-record it later with a human voice,
  so keep narration and picture loosely coupled: each scene's narration must fit inside the scene with ≥ 0.4 s spare.
- **Sound effects (new, the advisor asked for them).** Subtle, synthesised locally so there are no licence questions
  (ffmpeg `sine` / `anoisesrc` + filters, or numpy → WAV): a soft click on button presses, a short whoosh on scene
  changes, a gentle two-note chime when a verdict appears, a low tick for the three progress steps. Keep them at
  least 12 dB under the narration, never on top of a spoken consonant cluster, none during the first 0.3 s of a
  sentence. No background music (the owner decided that earlier). Overall loudness −16 LUFS, true peak ≤ −1.5 dB.
- **Pronunciation traps.** The owner caught 「重跑」 read as zhòng in v0.4.0. 重 meaning "again" is unsafe in this
  voice: write 「重新測試」「再跑一次」, or use the homophone trick in the `tts` field (captions keep the correct
  characters) and verify with the pitch-contour check. Check other polyphones you introduce (行、長、得、假、為、調、傳、處、
  便、更). 「長庚」 is read correctly. Spell out "CGU"; read "AIR", "Threads", "Vercel", "Render", "Supabase", "GitHub"
  as words; "P0" as 「P 零」.
- Captions: same single-track style as v0.4.0, never more than two lines, no overflow.

## Outputs

1. `docs\demo\presentation_v1.0.mp4`: 1920×1080, 30 fps, H.264 + AAC, **duration ≤ 295 s**. (`docs/demo/*.mp4` is
   git-ignored.)
2. `docs\demo\presentation_v1.0.srt`
3. `code\frontend\public\demo\presentation_v1.mp4`: web copy, H.264 CRF ~27, `+faststart`, **under 30 MB** (this one
   is committed; the site will serve it at https://fakenewsverify.vercel.app/demo/presentation_v1.mp4).
4. `presentations\2026-09_進度報告\06_簡報影片旁白稿.md`: narration text per scene with start / end times and what is
   on screen, so a teammate can re-record the voice. Plain Traditional Chinese.
5. `docs\demo\footage_log.md`: a "presentation_v1.0" section (what was recorded on the live site and when, what was
   reused, honesty labels, AI calls spent).

## Rules (unchanged)

- Local rendering only: no `hyperframes publish` / cloud / lambda / feedback, no sign-ins, telemetry off.
- Nothing sensitive on screen: no `.env`, tokens, keys, personal accounts, full local paths. Never read `.env`.
- Do not commit or push; do not edit files outside `video/`, `docs/demo/`, `code/frontend/public/demo/` and the one
  narration file in `presentations/2026-09_進度報告/`.
- Verify before you report: ffprobe (duration ≤ 295 s, streams), black-frame and long-silence detection (with SFX
  there should be no silent stretch over ~5 s), loudness, frame spot-checks at ≥ 16 timestamps for overflow,
  garbling, wrong numbers, wrong names, and the web copy size.

## Final report (short)

Output paths, exact duration, web-copy size, scene list with timings, what was newly recorded vs reused, AI calls
spent on the live site, the pronunciation checks you made, anything you could not verify (you cannot listen), and
anything missing after the folder move.
