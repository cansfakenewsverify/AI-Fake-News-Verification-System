# demo_v0.3.0 素材紀錄（O-18 錄製／O-19 剪輯）

| 項目 | 內容 |
|------|------|
| 成品 | `docs/demo/demo_v0.3.0.mp4`（未進 git，`.gitignore` 已加 `docs/demo/*.mp4`）＋ `docs/demo/demo_v0.3.0.srt` |
| 規格 | 175.4 秒；1920×1080、30 fps、H.264 High yuv420p（CRF 23）；AAC 48 kHz 立體聲約 160 kbps；9.3 MB；整體響度 −15.1 LUFS |
| 製作 | 2026-09-16 01:10–02:30（+08:00），Claude 全自動錄製、配音、上字幕、剪輯（負責人 2026-09-16 核准，見 `docs/rebuild/owner_decisions_day0.md`） |
| 依據 | `docs/demo/storyboard.md` v1.0 ＋ 負責人對本次製作的五點變更（手機改網頁手機模擬、終端機改實際輸出重繪、錄本機、鏡 10 數字定稿、旁白只微調鏡 5／6） |
| 貼文與實測值 | `docs/demo/demo_posts.md` |

## 1. 錄製環境

| 項目 | 設定 |
|------|------|
| 後端 | 本機 `uvicorn app.main:app` on `127.0.0.1:8000`。只用程序環境變數設定：`THREADS_MODE=sim`、`PUBLIC_BASE_URL=https://fakenewsverify.vercel.app`、`THREADS_POLL_MINUTES=600`（排程不會在 reset 與 poll 之間自動輪詢）、`AI_PROVIDER=cgu`、`CGU_MODEL=gpt-5.4-mini`、`ENABLE_SCHEDULER=false`、一次性 `ADMIN_TOKEN`（錄完即刪、未印出）。`code/backend/.env` 未讀取、未修改。生效設定另含 `USE_WEB_SEARCH=false`、`SIMILARITY_THRESHOLD=0.75`、provider 鏈 `['cgu']` |
| 前端 | repo 的 `code/frontend`，以 Vite 8.3.0 dev server 跑在 `127.0.0.1:5288`（暫時設定檔放在 scratchpad、不在 repo；獨立 dep cache；`VITE_FIXTURES=0`；`/api` 代理到 8000）。負責人自己的 Vite（5173／5179／5199）未碰 |
| 錄影專用延遲 | 暫時設定檔對 `GET /api/result/*` 多等 800 ms 再轉發（其他請求不延遲），理由見第 4 節發現 1 |
| 瀏覽器 | headless Microsoft Edge 153（CDP），全新設定檔、無登入；每個 take 開錄前清空 localStorage／sessionStorage（首頁不出現「最近查證」測試句）；淺色主題 |
| 桌機鏡（2、7、8、9） | 1920×1080 視窗＋125% 呈現縮放（CSS zoom，版面同瀏覽器 125%），CDP screencast 即時錄製 |
| 手機鏡（5、6） | 390×844、DPR 2、mobile emulation（Android Chrome UA、觸控），CDP 截圖；靜止段即時擷取、捲動段逐步捲動逐張擷取；合成到 1920×1080 中性底色＋簡單圓角外框，無假狀態列 |
| 錄影輔助（僅視覺） | 注入可見滑鼠指標與點擊波紋；可疑網址（頁面上的 http(s) 網址文字）以覆蓋層模糊遮蔽；「分享到 Threads」連結被攔下不開新分頁（沒有對 threads.com 發出請求），並記下實際 href。頁面資料與 DOM 內容未改動 |
| 資料安全 | 開錄前備份 `knowledge_base.parquet`、`factcheck.db`、`tasks.parquet`（`data/threads_sim/`、`threads_state.json`、`threads_replies.jsonl` 原本不存在）。錄影用 `mentions.json` 只含 p100＋m1。錄完三個檔從備份還原（SHA-256 與錄前相同：`B4F49CD7…`、`880DAB98…`、`59074EC3…`），錄影新增的 `threads_sim/`、`threads_state.json`、`threads_replies.jsonl` 已刪除，`data/` 檔案清單與錄前一致 |

## 2. 各鏡紀錄

| 鏡 | 時間碼 | 秒 | 素材／take | result_id | cache_layer | 判定 | 與分鏡的差異與原因 |
|----|--------|----|------------|-----------|-------------|------|--------------------|
| 1 | 0:00.0–0:08.0 | 8.0 | 剪輯字卡（HTML 逐幀渲染）；文字取 p100 | — | — | — | 網址以模糊色塊遮蔽（非「•••」） |
| 2 | 0:08.0–0:18.9 | 10.9 | S2_t1（01:41）首頁，停 3 秒→指標移到輸入框 | — | — | — | 本機 localhost 錄製、角標「本機執行畫面」；字幕「全民查證公社｜fakenewsverify.vercel.app」拿掉網址（網址只放片尾字卡）；無網址列 |
| 3 | 0:18.9–0:33.4 | 14.5 | 終端機風格 HTML 場景，內容取自實際執行的 `--reset-sim`（01:24:03）與 `--poll`（01:24:19）stdout＋stderr；左側為實際 `mentions.json` | eb06622e-0592-4361-bfbd-0046b745cba6 | — | — | 以重繪場景取代 VS Code＋Windows Terminal 錄影（負責人變更 2）；角標「模擬模式…」＋「終端機實際輸出」；輸出文字未改動，只遮蔽 p100 網址；提示字元寫成 `PS …\code\backend>` |
| 4 | 0:33.4–0:52.4 | 19.0 | 同上場景續：poll 其餘輸出→`replies.jsonl` 實際那一行→`text` 欄逐行字卡 | eb06622e-0592-4361-bfbd-0046b745cba6 | hash | 紅「詐騙警告」、sources 1 x tier1（MyGoPen） | log 等待段剪掉（鏡 3 結尾停在等待游標、鏡 4 接其餘輸出）；字卡逐字取自 `text` 欄（含實際的 🔴） |
| 5 | 0:52.4–1:12.9 | 20.5 | S56_t1（01:39）手機模擬 `/r/eb06622e…`：頂部停留→捲到查核來源→停留 | eb06622e-0592-4361-bfbd-0046b745cba6 | hash | 紅「詐騙警告」、信心 高、快取命中・相同內容、來自 Threads @tester_a、查核機構 mygopen.com | 真手機改網頁手機模擬（負責人變更 1）；頁面經本機 Vite 開啟（非 Vercel＋tunnel）；兩段靜止畫面以重複靜止影格延長（5.6 秒、4.3 秒）；「你查的內容」網址模糊遮蔽 |
| 6 | 1:12.9–1:25.9 | 13.0 | S56_t1 續：點「分享到 Threads」→按鈕「已開啟 Threads」＋提示（5.0 秒）→解碼後的分享網址字卡（8.0 秒） | eb06622e-0592-4361-bfbd-0046b745cba6 | — | — | 不開 Threads、不登入，改呈現實際產生的 `threads.com/intent/post` 網址（分鏡備援 B）；旁白微調成符合畫面 |
| 7 | 1:25.9–1:43.9 | 18.0 | S7_t3（01:47）首頁貼改寫句 P2→結果頁→點快取 chip | af72a34b-2b20-4a82-99e1-44e2b8c2d83c | vector（kb_id 3e47b40d…＝p100 gold 列） | 紅「詐騙警告」、快取命中・語意相似 | 分鏡範例句實測 0.7364 未達 0.75，改用 P2（0.8026）；載入段 3.8 秒以 ×2 播放並標「畫面加速」；結果出現後剪掉 1.7 秒靜止；結尾靜止影格延長 1.4 秒 |
| 8 | 1:43.9–2:08.9 | 25.0 | S8_t1（01:46）首頁貼新訊息 N3→載入→結果頁 | 330006c9-0d5b-486d-9af9-4f2b38413e78 | null（AI，provider cgu） | 紅「假訊息」、信心 高、AI 即時判定、sources []、unverified → 「尚無查核機構證實」橫幅 | 第一句候選就出現橫幅，未動用備援 D；載入段 9.4 秒以 ×3 播放並標「畫面加速」；結果頁內容一屏放得下、未捲動；結尾靜止影格延長 8.3 秒 |
| 9 | 2:08.9–2:24.9 | 16.0 | S9_t2（01:49）`/trending` 捲動→點「知識庫」→輸入「健保」→Enter→結果 | — | — | 列表判定點（紅／綠） | 指標移到導覽列（×2）與知識庫載入＋輸入（×1.5）加速並標「畫面加速」；結果卡片中的可疑網址模糊遮蔽；畫面無 `news.google.com`（`/api/trending` 回應不含 google、知識庫頁 DOM 不含 news.google.com）；搜尋結果第一筆是錄影時 `--reset-sim` 種入的 p100 gold 列（命中 5 次、評測標註） |
| 10 | 2:24.9–2:44.9 | 20.0 | 數據字卡（HTML 逐幀渲染） | — | — | — | 只放負責人指定數字：前一版模型 gpt-5-mini、150 筆標註：accuracy 96.0%、FN=0、FP=5；後端 pytest 472 項＋前端單元測試 375 項全數通過（GitHub Actions CI）；測試計畫書 TP-FNV-2026-01 5 類 46 項；熱門牆 Google News 轉址 31 → 0、知識庫已證實 128 筆；角落「CGU gpt-5.4-mini 重跑評測：報告後」。拿掉「SCAM／MISINFO／SAFE 各 50」 |
| 11 | 2:44.9–2:55.4 | 10.5 | 片尾字卡 | — | — | — | 未放團隊與指導教授名單（需負責人確認）；最後 0.6 秒淡出 |

未採用的 take：

| take | 原因 |
|------|------|
| S7_t1 | 結果頁顯示「出了點問題 伺服器發生錯誤（500）」：`/api/result` 第一次輪詢撞上任務處理器改寫 `tasks.parquet`（見第 4 節發現 1）。後台該筆實際完成為 `vector`（result_id 862e9cc1…） |
| S7_t2 | 成功（`vector`，result_id af78c76e…），但點 chip 後滑鼠指標蓋住「快取命中・語意相似」字樣 |
| S9_t1 | 遮蔽覆蓋層算到被 line-clamp 截掉的隱藏文字，在 cofacts.tw 網域上多出一塊灰框；修正後重錄 S9_t2 |

## 3. 旁白與字幕

| 項目 | 內容 |
|------|------|
| 配音 | CGU AIR `POST /audio/speech`，`gpt-4o-mini-tts`、voice `coral`、instructions「用自然、清楚的台灣華語語氣旁白，語速適中。」、mp3；未加速 |
| 文字 | 分鏡「旁白」欄；只改鏡 5（「回覆裡的連結，打開就是這個手機版結果頁：…」）與鏡 6（「看懂之後，按一下分享到 Threads：分享網址已經帶好判定和結果頁連結，不需要 Meta 審核。」）。字幕與 SRT 用這份文字（句尾逗號句號省略） |
| 送 TTS 的讀音調整（字幕不變） | 鏡 8「長庚」送「常庚」（避免念成 zhǎng）；鏡 10「150」「96%」送「一百五十」「百分之九十六」 |
| 重錄 | 用語音轉文字（`gpt-4o-mini-transcribe`、`whisper-1`）抽查：鏡 6、11 的「Threads」、鏡 10 的「報告」聽成別的字 → 加讀音提示重生（鏡 6、10 第 2 版；鏡 11 第 3 版，whisper 轉寫與原文一致） |
| 長度 | 各鏡旁白 6.72／10.25／12.46／15.60／18.22／10.97／14.26／23.40／15.17／18.72／9.50 秒，合計 155.3 秒；每鏡片長 ≥ 旁白＋0.6 秒；密度最高鏡 10（70 字／20 秒 = 3.5 字／秒） |
| 字幕 | 42 句，燒進畫面（HTML 渲染 PNG 疊加，Noto Sans TC）；時間依停頓自動對齊，鏡 7、8、9 各一個斷點依停頓表人工校正 |
| 響度 | 每段以 ebur128 量測後調到 −18 LUFS＋限幅，成品整體 −15.1 LUFS、峰值 −0.9 dBFS |

## 4. 發現（交給負責人）

1. **`/api/result` 讀寫競態（實際 bug）**：本機送出查證後，結果頁第一次輪詢若剛好碰到背景任務改寫 `data/tasks.parquet`，後端讀到 0 byte 檔案回 500（`pyarrow ... Parquet file size is 0 bytes`），前端顯示「出了點問題」並停止輪詢（S7_t1）。錄影改在 Vite 代理對 `GET /api/result` 加 800 ms（相當於經 Vercel＋tunnel 多一跳），程式與資料未改。正式環境延遲較大比較不容易撞到，但仍可能發生；建議報告前評估修正（例如 parquet 先寫暫存檔再原子替換，或讀檔失敗時重試）。
2. 結果頁頁尾對 `--reset-sim` 種入的列顯示「評測標註」（`label_source=gold`），鏡 5、7 與知識庫卡片都看得到；若覺得字面容易被誤解，可再決定文案。
3. 熱門牆捲動時會經過一則提到外國政治人物的 MyGoPen 查核標題與幾則 Cofacts 使用者回報的詐騙訊息原文（皆為真實資料、約 2 秒）。
4. 首頁 Threads 說明卡寫「機器人會在 5 分鐘內回覆」，是網站既有文案；影片旁白與角標都已說明目前為模擬模式。

## 5. CGU AIR 用量（`GET {CGU_BASE_URL}/me/usage`，openai 池）

| 時間（UTC） | requests | cost_usd | 說明 |
|-------------|----------|----------|------|
| 2026-09-15 17:13:37 | 6 | 0.016059 | 開工前 |
| 17:32:33 | 25 | 0.094579 | `--reset-sim` 向量 1、改寫句／新訊息篩選向量 7、TTS 11 段 |
| 17:35:53 | 48 | 0.149267 | TTS 重生 4 段、語音轉文字抽查 19 次 |
| 17:50:56 | 53 | 0.155421 | 網站實錄：鏡 7 三個 take 各 1 次向量、鏡 8 向量 1＋AI 判讀 1（log 估 USD 0.003） |
| 18:27:40 | 53 | 0.155421 | 剪輯完成後（無新呼叫） |

合計花費 **USD 0.139**（上限 USD 0.50）；剩餘額度 USD 9.84。

---

# v0.4.0：demo_v0.4.0（HyperFrames 重製，2026-09-19）

故事、旁白與誠實原則不變；改用 HeyGen 開源的 [HyperFrames](https://github.com/heygen-com/hyperframes)（npm `hyperframes` 0.8.50，Apache-2.0，「HTML 寫畫面、本機 render 成影片」）重做版面、鏡頭運動、轉場與字幕。**沒有重錄**：網站畫面全部沿用 v0.3.0（2026-09-16）的實錄影格，終端機與回覆文字沿用當時留下的實際輸出。

| 項目 | 內容 |
|------|------|
| 成品 | `docs/demo/demo_v0.4.0.mp4`（未進 git）＋ `docs/demo/demo_v0.4.0.srt`（41 句） |
| 規格 | **157.2 秒（2:37）**；1920×1080、30 fps（4716 幀）、H.264 High yuv420p（bt709）；AAC-LC 48 kHz 立體聲約 120 kbps；**48.2 MB**（46.0 MiB）；整體響度 −16.2 LUFS、LRA 6.0 LU、峰值 −4.3 dBFS；`blackdetect` 0 段 |
| 專案 | `video/hf-demo/`（只提交原始碼：HTML／CSS／JS／JSON／MD；素材、旁白音檔、render、snapshot、skills 皆 gitignore） |
| 製作 | 2026-09-19，Claude 全自動；本機 render（`chrome-headless-shell` 152＋ffmpeg 9.0.1，3 workers 約 2 分 54 秒）。未執行 `publish`／`cloud`／`lambda`／`cloudrun`／`auth`／`feedback`，未登入任何服務；遙測以 `HYPERFRAMES_NO_TELEMETRY=1`、`DO_NOT_TRACK=1` 關閉 |
| 背景音樂 | **無**（負責人 2026-09-19 決定）；只有旁白，每段旁白加 0.06 秒淡入、0.22 秒淡出 |
| CGU AIR 花費 | **USD 0**：沒有啟動後端、沒有呼叫 AI 或 embedding；旁白用 edge-tts（免帳號免金鑰） |

## 1. HyperFrames 用法

| 項目 | 內容 |
|------|------|
| 建立專案 | `npx hyperframes init hf-demo --non-interactive --example blank --resolution landscape`（`HYPERFRAMES_SKIP_SKILLS=1`）；`npx hyperframes doctor`：Node、FFmpeg、FFprobe、Chrome 皆通過（whisper／Kokoro／MusicGen／Docker 為選用，未安裝） |
| agent skills | 12 個，**專案層級**安裝在 `video/hf-demo/.claude/skills`、`.agents/skills`：`hyperframes`、`hyperframes-core`、`-animation`、`-creative`、`-cli`、`-audio`、`-keyframes`、`-registry`、`-studio`、`media-use`、`general-video`、`product-launch-video`。指令：`npx skills@1.7.0 add https://github.com/heygen-com/hyperframes --skill … --agent claude-code universal --copy --full-depth --yes`。**沒有**用 `npx hyperframes skills update`：看過 CLI 原始碼，它固定帶 `--global`，會裝進使用者家目錄（`~/.claude/skills`、`~/.agents/skills`）並鏡射到其他 AI 工具的全域目錄，屬於全域設定變更 |
| 流程 | `/hyperframes` 路由 → `/general-video`（既有實錄的 footage remix＋固定分鏡與逐字旁白；`flow: automation`、`storyboard: no`）。產物：`BRIEF.md` → `STORYBOARD.md`（每景標出引用的 blueprint／rule）→ `frame.md`（設計規格）→ `compositions/`（每景一個 sub-composition）→ `hyperframes lint`／`check`／`snapshot` → `render` |
| 結構 | `index.html`（薄的 orchestrator：9 個場景 host、chrome、單一字幕軌、11 段旁白 `<audio>`、根 timeline 只放轉場）；場景 `s01-hook`、`s02-home`、`s03-sim`（鏡 3＋4）、`s05-phone`（鏡 5＋6）、`s07-vector`、`s08-ai`、`s09-wall`、`s10-numbers`、`s11-end`；`chrome`（品牌字＋底部進度線）；`captions`（41 組，一次一組、結尾硬切）。`index.html`／`captions.html`／`chrome.html`／SRT 由 `tools/build_timeline.mjs` 依 `data/plan.json`＋`data/timing.json` 產生 |
| 套用的技巧 | 實錄放在左側視窗，**虛擬攝影機**在視窗內推近／平移（`viewport-change`：寬景 1.0 → 內容欄 1.425）；手機鏡用**放大鏡**（同一段實錄的第二個 `<video>`，約 ×3）巡過判定列→摘要→來源→來歷→分享鈕；**強調框**（畫在實錄座標上的墨黑外框，跟著鏡頭走）；終端機用 `discrete-text-sequence` 逐字打入＋方塊游標；數字卡 count-up 停在精確值；開場 `waterfall-entry`；轉場以 push slide 為主、blur crossfade 標示換主題、片尾淡出；旁白淡入淡出用 `data-automation` 音量 lane；`index.motion.json` 讓 `check` 驗證出場順序與「畫面持續有動態」 |
| 檢查 | `hyperframes check --samples 48`：lint 0、runtime 0、layout 0 error／0 warning（12 個轉場瞬間的 info）、motion 14 條斷言全過（300 個取樣）、contrast 56／56 |
| 重建素材 | `node tools/build_footage.mjs <v0.3.0 raw 目錄>`（加速段、剪掉的靜止空檔、靜止延長都先烘進定速影片，因為 HyperFrames 只支援定速播放）；`tools/tts.py`（旁白）；`node tools/build_timeline.mjs`；`npm run check`；`npm run render` |

## 2. 各鏡紀錄

| 鏡 | 時間碼 | 秒 | 素材來源 | 與 v0.3.0／分鏡的差異 |
|----|--------|----|----------|------------------------|
| 1 | 0:00.0–0:07.0 | 7.0 | HTML 場景；文字取 p100 | 網址是純色遮蔽塊，**底下沒有網址文字**；右上「示意訊息（模擬測試資料）・網址已遮蔽」 |
| 2 | 0:07.0–0:17.0 | 10.0 | S2_t1 實錄（首頁） | 「本機執行畫面」；右欄三行：三層快取／Threads 機器人（註明本片為模擬模式）／長庚 CGU AIR・gpt-5.4-mini；正式網址只放片尾 |
| 3 | 0:17.0–0:30.0 | 13.0 | HTML 重繪：實際 `mentions.json`＋`--reset-sim`／`--poll` 的實際輸出（`data/captured.json`，逐字） | 全程角標「模擬模式：流程與正式串接相同，正式上線需 Meta App Review」；終端機標「終端機實際輸出・畫面重繪」；`--poll` 指令逐字打入，輸出順序與等待時間照實際執行（3.2 秒）重播；p100 網址遮蔽；等寬字關閉連字，`->` 照原樣 |
| 4 | 0:30.0–0:46.5 | 16.5 | 同上續：log 那一行拆成 5 個 token 逐一說明 → `replies.jsonl` 實際那一行＋`text` 欄五行 | 🔴 只出現在錄到的回覆文字；「第一行＝燈號」「查核機構（Tier 1）」標註；結尾標出「完整判讀」連結，銜接下一鏡 |
| 5 | 0:46.5–1:03.7 | 17.2 | S56_t1 實錄（390×844 手機模擬 `/r/eb06622e…`） | 素色圓角框（無瀏海、無狀態列）；「本機執行畫面・手機寬度模擬 390×844」；放大鏡標「同一段實錄 ×3」；卡片「由模擬模式產生／@tester_a 是測試帳號」；靜止段以靜止影格延長（3.0 秒、7.7 秒） |
| 6 | 1:03.7–1:14.2 | 10.5 | S56_t1 續（按「分享到 Threads」→「已開啟 Threads」）＋實際產生的 Web Intent 網址（解碼後） | 沒有開啟 Threads、沒有登入（錄影時連結已攔下）；卡片標「未開啟 Threads、未登入」 |
| 7 | 1:14.2–1:29.2 | 15.0 | S7_t3 實錄（改寫句 P2 → `vector`） | 載入段 3.9 秒以 ×2 播放並標「畫面加速 ×2」；剪掉兩段畫面完全靜止的空檔（原始 4.30–5.50、12.60–14.81 秒）；右欄相似度 0.80 為 `demo_posts.md` 實測 0.8026、門檻 0.75 |
| 8 | 1:29.2–1:50.7 | 21.5 | S8_t1 實錄（新訊息 N3 → AI 即時判定＋「尚無查核機構證實」） | 載入段 9.8 秒以 ×3 播放並標「畫面加速 ×3」；剪掉一段靜止空檔（4.05–5.35 秒）；結果出現後靜止延長；全片唯一一次「尚無查核機構證實」 |
| 9 | 1:50.7–2:05.7 | 15.0 | S9_t2 實錄（熱門牆捲動 → 知識庫 → 搜尋「健保」） | 指標移到分頁、移到搜尋框兩段以 ×2 播放並標「畫面加速 ×2」；剪掉兩段靜止空檔；畫面無 `news.google.com`（沿用 v0.3.0 的檢查） |
| 10 | 2:05.7–2:27.7 | 22.0 | HTML 數字卡 | 負責人核准數字：前一版 gpt-5-mini 150 筆 accuracy 96.0%、FN=0、FP=5；新模型 gpt-5.4-mini（長庚 CGU AIR）2026-09-16 重跑 150 筆 accuracy 100%、FN=0、FP=0；後端 pytest 478 項＋前端單元測試 375 項全數通過（GitHub Actions CI）；測試計畫書 TP-FNV-2026-01 5 類 46 項；熱門牆 Google News 轉址 31 → 0、知識庫已證實 128 筆 |
| 11 | 2:27.7–2:37.2 | 9.5 | HTML 片尾 | 「Threads 目前為模擬模式；公開服務需通過 Meta App Review 與企業驗證」；下一步只留「Threads 實機串接」（重跑評測已完成）；未放團隊與指導教授名單；最後 0.6 秒淡出 |

每鏡長度 ≥ 旁白字數 ÷ 3.5（分鏡的字數計法：6.0／9.7／12.6／16.3／17.1／10.0／14.3／21.1／13.7／21.7／8.6 秒）；每段旁白都在該鏡結束前至少 1.2 秒講完（以成品音軌的靜音偵測核對：各段起聲點＝排定時間＋0.14 秒）。

## 3. 旁白與字幕

| 項目 | 內容 |
|------|------|
| 配音 | edge-tts `zh-TW-YunJheNeural`（台灣華語男聲）、`--rate=+8%`；每鏡一段，實際語音長度 5.04／6.57／7.65／10.77／11.89／6.27／9.37／14.11／8.40／13.72／5.16 秒，合計 98.9 秒；每段以 EBU R128 兩段式正規化到 −16 LUFS |
| 文字 | 分鏡「旁白」欄；鏡 5、6 沿用 v0.3.0 微調；**鏡 10 依已核准的新數字改寫**：「前一版模型在 150 筆資料上，準確率 96%，而且沒有把任何詐騙或假訊息判成安全；換上長庚 CGU 的新模型重跑，150 筆全部判對。每次提交，CI 都會自動跑完測試。」（原句「重新評測排在報告之後」已不符事實） |
| 送 TTS 的讀音調整（字幕不變） | 只有鏡 10 的數字：「150」→「一百五十」、「96%」→「百分之九十六」 |
| 讀音測試（離線、零花費） | 「長庚」：分別合成「長庚／常庚／掌庚」做 log-mel DTW，長庚↔常庚 2.05、長庚↔掌庚 3.86（句中 1.72 對 3.13）→ 這個聲音念 cháng，**不需改寫**。英文詞量有聲長度：CGU 0.59 秒（≈「C G U」0.64，逐字母）、AIR 0.27 秒（單字；「A I R」0.59）、Threads 0.43、MyGoPen 0.61（≈「My Go Pen」0.56）、Cofacts 0.57（≈「Co facts」0.61）、Meta 0.33、CI 0.39、AI 0.30 → 皆不需改寫。本機沒有語音轉文字工具（whisper-cpp 未安裝，也不為此下載模型），**負責人請實際聽一次** |
| 字幕 | 41 句，時間取自 edge-tts WordBoundary；畫面字幕與 SRT 同一份資料；句尾逗號句號省略 |

## 4. 交給負責人確認

1. 鏡 10 旁白已改寫（見上表），鏡 11 片尾拿掉「CGU 模型重跑評測」；若要維持分鏡原句請告知。
2. 熱門牆捲動（約 1:51–1:56）沿用 v0.3.0 同一段實錄，一樣會經過一則提到外國政治人物的 MyGoPen 查核標題與幾則 Cofacts 使用者回報的詐騙訊息原文（真實資料）。
3. 結果頁頁尾的「評測標註」、首頁 Threads 說明卡「5 分鐘內回覆」兩點與 v0.3.0 第 4 節相同（同一批實錄）。
4. `video/` 底下另有先前用 Remotion 做到一半的 v0.4.0 專案（`video/src`、`video/tools` 等，未提交）；本次沒有動它，是否保留由負責人決定。

---

# presentation_v1.0：5 分鐘簡報影片（2026-09-20）

老師 2026-09-20 的新規定：簡報就是一支預先錄好、最長 5 分鐘、有旁白與音效的影片，像「系統開箱文」，要介紹整個系統的功能、所有操作與輸入輸出。完整規格在 `docs/demo/presentation_video_brief.md`。

**與 v0.3.0／v0.4.0 最大的不同：畫面全部重錄，而且錄的是正式站**（`https://fakenewsverify.vercel.app`），不是本機。v0.4.0 的網站畫面是 2026-09-16 的本機實錄，這一版不再沿用；只有 Threads 機器人那一段沿用當時的模擬輸出（雲端 `THREADS_MODE=off`，無法實錄）。

| 項目 | 內容 |
|------|------|
| 成品 | `docs/demo/presentation_v1.0.mp4`（未進 git）＋ `docs/demo/presentation_v1.0.srt`（45 句）＋ 網站用的 `code/frontend/public/demo/presentation_v1.mp4`（已提交） |
| 規格 | **278.0 秒（4:38）**；1920×1080、30 fps（8340 幀）、H.264 High yuv420p；AAC-LC 48 kHz 立體聲；母片 81.3 MB、網站用檔 **23.8 MB**（CRF 24、`+faststart`）；整體響度 −16.1 LUFS、LRA 4.0 LU、峰值 −3.6 dBFS；`blackdetect` 0 段、無超過 5 秒的靜音 |
| 驗證 | `node tools/verify.mjs`：片長、解析度、幀率、編碼、黑畫面、長靜音、響度、峰值、網站用檔大小與片長，12 項全過；另外把 36 張抽樣影格拼成聯絡表逐格看過 |
| 專案 | `video/hf-presentation/`（HyperFrames 0.8.50；只提交原始碼，素材、旁白、音效、render 皆 gitignore）。`video/hf-demo/` 的 v0.4.0 專案完全沒有更動，`npm run render` 仍可重現 |
| 旁白稿 | `presentations/2026-09_進度報告/06_簡報影片旁白稿.md`（由 `tools/build_narration_doc.mjs` 從剪輯資料產生，時間碼即成片時間碼） |
| 正式站 AI 用量 | **1 次**。上限自訂為 12 次，後端 `/api/health` 的 `daily_ai_calls.used` 從 0 變成 1 就沒再動過。其餘查證全部命中快取（相同內容、語意相似、相同網址） |
| 背景音樂 | 無（負責人 2026-09-19 的決定沿用）。音效為本機合成，見第 4 節 |

## 1. 錄製方式（`video/hf-presentation/tools/capture.mjs`）

| 項目 | 設定 |
|------|------|
| 瀏覽器 | headless Microsoft Edge（CDP），每個鏡頭開一個全新的暫時設定檔，沒有登入任何服務 |
| 桌機鏡 | 版面寬度 1280 CSS px（網站的桌機斷點），以 1.5 倍裝置像素擷取 → 原生 1920×1080 影格。`--force-device-scale-factor` 與 `Emulation.setDeviceMetricsOverride` 必須同時設定，只設其中一個會靜靜地錄成 1280×720 |
| 手機鏡 | 390×844 CSS、2 倍 → 780×1688，Android UA 與觸控模擬；影片中放在素色圓角框裡，沒有假的瀏海或狀態列 |
| 錄影輔助（僅視覺，不改動頁面資料與 DOM 文字） | ① 可見滑鼠指標與點擊波紋（手機鏡不顯示指標）；② 頁面文字中的 http(s) 網址一律蓋上不透明遮蔽塊，**底下沒有網址文字**，白名單只有 fakenewsverify、mygopen、tfc-taiwan、cofacts；③ 對外連結一律攔下不跳轉，只記下 href |
| 一個技術細節 | Chrome 的 screencast 只在合成器產生新影格時才送出影格，畫面靜止時會整段停錄。因此注入的游標帶一個 0.02 px 的位移動畫當節拍器——遠小於一個裝置像素，不會改變任何一個算出來的像素，只是讓「停住的畫面」真的被錄成停住的畫面 |
| 資料安全 | 全程沒有讀取或修改 `code/backend/.env`；畫面中沒有金鑰、沒有本機完整路徑、沒有個人帳號 |

## 2. 各鏡紀錄

成片 **278.0 秒（4:38）**，12 段。下表的「原始」是該鏡實錄的長度，「成片」是剪過（加速、剪掉靜止空檔、靜止延長）之後的長度。

| 鏡 | 成片時間 | 秒 | 素材 | 原始 | 內容與實際結果 |
|----|----------|----|------|------|----------------|
| 1 | 0:00–0:15 | 15.0 | HTML 場景 | — | 可疑訊息卡（本專題的模擬測試資料，網址遮蔽）→ 標題卡：正式名稱、系統名稱、系所、五位組員、指導教授黃崇源、網址 |
| 2 | 0:15–0:30.5 | 15.5 | 實錄 `home` | 24.4 s | 首頁：文字／網址分頁、0/20000 計數、三個範例、Threads 說明卡、頁尾 |
| 3 | 0:30.5–0:47 | 16.5 | 實錄 `text_flow` | 23.8 s | 點第一個範例「健保卡即日起停用，請點連結重新驗證」→ 開始查證 → 三步驟進度 → 結果頁。**這是全片唯一一次真的呼叫 AI**；等待段 ×3 加速並標示 |
| 4 | 0:47–1:26 | 39.0 | 實錄 `result_walk` | 34.3 s | 結果頁由上往下走完：紅燈「詐騙警告」、信心 高、「AI 即時判定」、黃色「尚無查核機構證實」橫幅、你查的內容、判讀摘要、詳細說明展開、查核來源（空，顯示誠實說明）、分享到 Threads（按鈕真的變成「已開啟 Threads」）、複製連結（「已複製」）、再查一則。`result_id=72a372a1-0581-450a-8e48-ac154e95e8fe` |
| 5 | 1:26–1:46 | 20.0 | 實錄 `url_check` | 24.8 s | 網址分頁：先貼「健保卡停用」被擋下（「這不是有效的網址，請以 http:// 或 https:// 開頭。」），再貼 MyGoPen 查核報導網址 → 紅燈「假訊息」、判讀摘要「此為已被查核的假訊息…」。chip 是「快取命中・相同網址」（熱門牆已收過這個網址），因此沒有花 AI |
| 6 | 1:46–2:06 | 20.0 | 實錄 `cache_hash`＋`cache_vector` | 各 14.3 s | 同一則訊息再查 →「快取命中・相同內容」；換句話說（「網傳有人搭飛機的時候拍到巴威颱風的颱風眼畫面，這是真的嗎」）→「快取命中・語意相似」。兩段都是第一次嘗試就命中，未呼叫 AI |
| 7 | 2:06–2:30 | 24.0 | 實錄 `trending`＋`knowledge` | 28.0／24.0 s | 熱門牆（來源、全部／未查證、捲動）→ 知識庫搜尋「健保」六筆、判定篩選 |
| 8 | 2:30–2:45 | 15.0 | 實錄 `theme`＋`phone`＋`policy` | 15.9／10.2／11.0 s | 深淺色切換、手機版底部分頁列、隱私政策與資料刪除說明 |
| 9 | 2:45–3:09 | 24.0 | HTML 重繪＋實錄 `phone_result` | 12.5 s | Threads 貼文與提及、機器人回覆（**逐字沿用** 2026-09-16 模擬輸出，`video/hf-demo/data/captured.json`）、手機結果頁、模擬模式說明。全程角標「模擬模式：流程與正式串接相同，正式上線需 Meta App Review」 |
| 10 | 3:09–3:46 | 37.0 | HTML 場景 | — | 架構：瀏覽器 → Vercel → Render（FastAPI）→ Supabase（Postgres＋pgvector）／長庚 CGU AIR（gpt-5.4-mini）；再切到三層判讀順序與護欄（每天 300 次、每分鐘 30／每小時 200、上傳 10 MB） |
| 11 | 3:46–4:22 | 36.0 | HTML 場景 | — | 150 筆評測 96.0% → 100%（count-up）、兩次都沒有漏判、後端 700／前端 385、測試計畫書 46 項、P0 27／30、未過的一項（語意快取命中率 65% vs 目標 70%，沒有調低門檻） |
| 12 | 4:22–4:38 | 16.0 | HTML 場景 | — | 下一步（Threads 實機串接、更大的評測集）、網站與 GitHub 網址、謝謝各位老師、免責提醒 |

沒有採用的畫面：第一次錄的 `url_check` 用了台灣事實查核中心的一篇報導，系統回「尚無查核機構證實」（黃燈），在畫面上容易被誤解成「貼了查核中心的文章卻說沒人查核」，改用 MyGoPen 那篇（紅燈「假訊息」＋清楚的判讀摘要）重錄。

## 3. 誠實標示（畫面上看得到的）

- 每個實錄鏡頭左上角：**「正式站實錄」**；網址 `fakenewsverify.vercel.app` 固定在畫面左上的片頭字樣旁，整片都在。
- 加速的段落：**「畫面加速 ×N」**。這些標籤不是手寫的——`tools/build_scenes.mjs` 直接讀 `data/footage_map.json`，畫面上標到的區間就是實際被加速的區間。
- Threads 那一段：全程「模擬模式…正式上線需 Meta App Review」。片尾再說一次。
- 所有可疑網址：不透明遮蔽塊，底下沒有文字。
- 沒有任何假造的結果；沒有 fixtures；沒有灰色「AI 暫時無法使用」卡。

## 4. 旁白與音效

| 項目 | 內容 |
|------|------|
| 配音 | edge-tts `zh-TW-YunJheNeural`（台灣華語男聲）、`--rate=+10%`，每鏡一段，各段以 EBU R128 正規化到 −16 LUFS |
| 字幕 | 45 句，時間取自 edge-tts WordBoundary；畫面字幕與 SRT 同一份資料，最多兩行 |
| 讀音處理 | 「重」當「再一次」解時這個聲音會念成 zhòng，所以旁白**直接避開**這個字（改寫成「再跑一次」「換上新模型之後」），不用同音字硬湊。數字一律以國字送合成；CGU、API、IP、AI、HTTP 逐字母；P0 念「P 零」 |
| 看過成片後改掉的兩句 | ①「答案**立刻**出現」→「很快就有答案」：快取命中實際要數秒，而且那段畫面是加速播放的。②「MyGoPen…的**最新**查核」→「的查核結果」：熱門牆畫面上的資料更新時間是 2026-07-12，不能說是最新 |
| 音效（老師新要求） | 本機用 numpy 合成，沒有授權問題：`click`（按鈕）、`tick`（三步驟進度）、`chime`（判定出現）、`whoosh`（換段）。**點擊音的時間不是憑感覺放的**：`tools/build_sfx.mjs` 把實錄裡真正的點擊時間，經過剪輯的時間映射換算成成片時間，所以聽到的每一下都對應畫面上真的按下去的那一下。落在句子前 0.3 秒內的事件一律捨棄（共 3 個），全部音效都在旁白之下 |

## 5. 交給負責人確認

1. **雲端知識庫有 24 筆的「查核來源」是 Cofacts 的回報文章／討論頁，卻被標成 Tier 1「查核機構」**（其中幾筆的來源標題甚至就是詐騙訊息原文）。這與「只有已做出判定的查核來源才算來源」的原則不符。影片已避開這些列（知識庫那一段搜尋「健保」，六筆全部引用健保署、衛福部、警政署等機關頁面），但**資料本身建議清掉或重新標記**。
2. 熱門牆的「資料更新時間」是 2026-07-12（雲端排程關閉，目前為手動更新）；影片裡這行字看得到。要不要在報告前手動更新一次由負責人決定。
3. 熱門牆捲動時仍會經過幾則 Cofacts 使用者回報的詐騙訊息原文（真實資料，標了來源與日期）。
4. 我聽不到聲音：**旁白與音效請負責人實際播一次**，特別是音效的音量是否太小或太吵。
