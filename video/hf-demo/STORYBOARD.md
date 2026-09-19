---
format: 1920x1080
duration: 157s
message: "可疑訊息先比對已查核的知識庫，查不到才問 AI，而且只把已做出判定的查核機構當來源"
arc: Hook → 定位 → 模擬閉環（快取命中）→ 手機結果頁與分享 → 語意相似 → AI 即時判讀（來源不足明說）→ 廣度 → 數據 → 限制與下一步
audience: 進度報告的老師與同學
mode: autonomous
---

This video tells 老師與同學 that 全民查證公社 先比對已查核的知識庫、查不到才問 AI，而且只把已做出判定的查核機構當來源。

Rhythm: hold – steady – BUILD – steady – quick – BUILD – steady – hold – close.
Transitions: push slide 0.5s (primary, "next point") · blur crossfade 0.5s (topic change: into the product, into the numbers, into the close) · the last scene fades out.
Scene files are sub-compositions; shots that share one continuous stage share one file (3+4, 5+6).
Narration and captions: `data/narration.json` → `tools/tts.py` → `data/timing.json` → `tools/build_timeline.mjs`.

## Frame 1 — 一則可疑訊息

- status: animated
- src: compositions/s01-hook.html
- duration: 7s
- transition_in: cut
- scene: 白底墨黑大字逐行落下：健保卡即日起停用！請點〔遮蔽〕重新驗證，逾期停卡 →「它是真的嗎？」
- voiceover: "這種訊息，你一定在群組或社群上看過。它是真的嗎？"
- motion: blueprint kinetic-type-beats (statement builds line by line onto a payoff question) · rules waterfall-entry, spring-pop-entrance
- honesty: 右下「示意訊息（模擬測試資料）」；網址為遮蔽色塊，底下沒有網址文字；不仿 Threads 介面

Viewer's own experience first: the message everyone has received. The question is the hook.

## Frame 2 — 定位：全民查證公社

- status: animated
- src: compositions/s02-home.html
- duration: 10s
- transition_in: blur crossfade
- scene: 首頁實錄放在畫面左側的視窗，鏡頭緩推到輸入框；右欄三行事實隨旁白落下
- voiceover: "全民查證公社：網站貼上訊息，或在 Threads 標記機器人，就能拿到 AI 判定和查核來源。"
- motion: blueprint device-surface-showcase (floating-window push) · rules viewport-change, waterfall-entry
- footage: assets/footage/s02_home.mp4 (S2_t1)
- honesty: 「本機執行畫面」；Threads 機器人標「本片為模擬模式」；不放正式網址（只在片尾）

## Frame 3 — Threads（模擬）：提及 → 快取命中 → 回覆

- status: animated
- src: compositions/s03-sim.html
- duration: 29.5s (鏡 3 13s + 鏡 4 16.5s)
- transition_in: push slide
- scene: 左：mentions.json（p100 原貼文、m1 提及被標出）；右：終端機重繪 --reset-sim 既有輸出、逐字打入 --poll、輸出逐行出現；標出 cache hash 與 1 x tier1；左欄換成 replies.jsonl 那一行；右側疊上 text 欄逐行字卡
- voiceover: 鏡 3「Threads 這段目前用模擬模式示範：…把原貼文抓回來。」＋鏡 4「系統先比對知識庫：…來源只放已經做出判定的查核機構。」
- motion: blueprint prompt-type-submit-generate (command types → machine answers → action log) + agent-progress-theater (receipt lines arrive) · rules discrete-text-sequence, context-sensitive-cursor, css-marker-patterns (neutral tint sweep), anchored-layout-expand
- honesty: 全程角標「模擬模式：流程與正式串接相同，正式上線需 Meta App Review」；終端機標「終端機實際輸出・畫面重繪」；文字逐字取自 data/captured.json；p100 網址遮蔽；🔴 只出現在錄到的回覆文字裡

## Frame 4 — 手機結果頁與分享

- status: animated
- src: compositions/s05-phone.html
- duration: 27.7s (鏡 5 17.2s + 鏡 6 10.5s)
- transition_in: vertical push (the link "opens")
- scene: 手機寬度實錄放在素色圓角框；右側放大鏡依旁白停在判定列、判讀摘要、查核來源列；鏡 6 按下分享 → 放大鏡換成實際產生的 Web Intent 網址（解碼後的 text／url）
- voiceover: 鏡 5「回覆裡的連結，打開就是這個手機版結果頁：…不算查核來源。」＋鏡 6「看懂之後，按一下分享到 Threads：…不需要 Meta 審核。」
- motion: blueprint device-surface-showcase (static tour) · rules coordinate-target-zoom (magnifier), nudge-curve, svg-path-draw (connector)
- footage: assets/footage/s05_phone.mp4 (S56_t1)
- honesty: 「本機執行畫面・手機寬度模擬 390×844」；「此筆由模擬模式產生（tester_a 為測試帳號）」；不開 Threads、不登入、不仿手機外觀；「你查的內容」網址在實錄時已遮蔽

## Frame 5 — 換個說法：語意相似命中

- status: animated
- src: compositions/s07-vector.html
- duration: 15s
- transition_in: push slide
- scene: 實錄：貼上改寫句 → 開始查證 →（載入段 ×2）→ 紅燈＋「快取命中・語意相似」→ 點 chip 展開說明；右欄：原句／改寫句、相似度 0.80 對門檻 0.75、三層快取階梯 ② 亮起
- voiceover: "如果有人換個說法再問一次呢？系統用語意向量比對，認出這是同一則謠言，馬上沿用先前的查核結果，不必再請 AI 判讀。"
- motion: blueprint cursor-ui-demo (camera chases the interaction) · rules viewport-change, stat-bars-and-fills, counting-dynamic-scale, css-marker-patterns (ink outline ring on the chip and on the 「沒有再次呼叫 AI」 note)
- footage: assets/footage/s07_vector.mp4 (S7_t3)
- honesty: 「本機執行畫面」；載入段標「畫面加速 ×2」；0.8026 為 demo_posts.md 的實測值；剪掉的只有畫面完全靜止的空檔

## Frame 6 — 新訊息：AI 即時判讀＋尚無查核機構證實

- status: animated
- src: compositions/s08-ai.html
- duration: 21.5s
- transition_in: push slide
- scene: 實錄：貼上新訊息 → 開始查證 →（載入段 ×3）→「AI 即時判定」＋橫幅「尚無查核機構證實」→ 鏡頭下移到空的查核來源區；右欄：階梯 ③ 亮起、長庚 CGU AIR・gpt-5.4-mini、「沒有 Tier 1／2 來源 → 明示、不給綠燈」
- voiceover: "那全新的訊息呢？快取裡沒有，就交給長庚 CGU AIR 的模型即時判讀。但找不到已經做出判定的查核來源，所以頁面會明白標示「尚無查核機構證實」，不假裝有來源，也不會亮綠燈。"
- motion: blueprint cursor-ui-demo · rules viewport-change, multi-phase-camera, css-marker-patterns (ink outline ring on the chip, the banner and the empty sources box)
- footage: assets/footage/s08_ai.mp4 (S8_t1)
- honesty: 「本機執行畫面」；載入段標「畫面加速 ×3」；全片唯一一次「尚無查核機構證實」

## Frame 7 — 熱門牆與知識庫

- status: animated
- src: compositions/s09-wall.html
- duration: 15s
- transition_in: push slide
- scene: 實錄：熱門牆捲動 → 點「知識庫」→ 搜尋「健保」→ 結果卡；右欄兩張卡：熱門牆來源、知識庫只收已證實的判定
- voiceover: "熱門牆整理 MyGoPen、事實查核中心和 Cofacts 的最新查核；知識庫可以搜尋查過的內容，而且只收有查核來源佐證的判定。"
- motion: blueprint transcript-scroll-artifact-reveal (traversal as evidence) · rules viewport-change, css-marker-patterns (ink outline ring on the knowledge-base rule line)
- footage: assets/footage/s09_wall.mp4 (S9_t2)
- honesty: 「本機執行畫面」；加速段標「畫面加速 ×2」；畫面無 news.google.com

## Frame 8 — 數據

- status: animated
- src: compositions/s10-numbers.html
- duration: 22s
- transition_in: blur crossfade
- scene: 三列：①評測（前一版 96.0%／FN 0／FP 5 → 新模型 100%／FN 0／FP 0）②測試（pytest 478＋前端 375、CI、測試計畫書 5 類 46 項）③資料品質（Google News 轉址 31 → 0、知識庫已證實 128 筆）
- voiceover: "前一版模型在 150 筆資料上，準確率 96%，而且沒有把任何詐騙或假訊息判成安全；換上長庚 CGU 的新模型重跑，150 筆全部判對。每次提交，CI 都會自動跑完測試。"
- motion: blueprint dataviz-countup · rules counting-dynamic-scale, stat-bars-and-fills
- honesty: 數字一律為負責人核准值；count-up 停在精確值；FN 旁註「FN＝風險訊息被判成安全」

## Frame 9 — 限制與下一步

- status: animated
- src: compositions/s11-end.html
- duration: 9.5s
- transition_in: blur crossfade
- scene: 片尾：全民查證公社／fakenewsverify.vercel.app／@factcheck_tw_bot；「Threads 目前為模擬模式；公開服務需通過 Meta App Review 與企業驗證」；下一步：Threads 實機串接
- voiceover: "下一步是完成 Threads 實機串接；要公開給所有人使用，還需要通過 Meta 審查。"
- motion: blueprint titlecard-reveal (one restrained move, then stillness) · final 0.6s fade
