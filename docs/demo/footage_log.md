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
