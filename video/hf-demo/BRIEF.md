---
workflow: general-video
flow: automation
storyboard: no
message: "全民查證公社：可疑訊息先比對已查核的知識庫，查不到才問 AI，而且只把已做出判定的查核機構當來源"
destination: classroom-projector
aspect: 1920x1080
language: zh-TW
audience: 進度報告的老師與同學（2026-09-21～09-23）
length: 150-180s
narration: yes
---

## Intent

進度報告用的 3 分鐘內 demo 影片（demo_v0.4.0），故事與 v0.3.0 相同：一則可疑訊息 →
Threads 模擬模式的機器人命中快取（L1）→ 手機結果頁、分享 → 換句話說也認得（L2 向量）→
全新訊息才問 AI（L3），找不到查核來源就明說 → 熱門牆與知識庫 → 評測與測試數據 → 誠實交代限制。
語氣平實、可信，像產品本身：白底、墨黑字，紅黃綠只出現在錄到的介面判定上。

路由理由：素材是既有的實錄畫面（footage remix）＋固定分鏡與逐字旁白，約 2.5–3 分鐘，
不重新擷取網站也不另外發想故事，所以走 `/general-video`（不是 `/product-launch-video`）。
負責人要求全程不提問、直接交付成品 → `flow: automation`、`storyboard: no`（autonomous）。

## Assets

- assets/footage/s02_home.mp4 — v0.3.0 實錄 S2_t1（首頁），鏡 2。
- assets/footage/s05_phone.mp4 — v0.3.0 實錄 S56_t1（手機寬度結果頁＋分享按鈕），鏡 5、6。
- assets/footage/s05_phone_lens.mp4 — 同一段實錄的第二份檔名（放大鏡是第二個 video；lint 要求媒體項目不重複）。
- assets/footage/s07_vector.mp4 — v0.3.0 實錄 S7_t3（改寫句命中語意快取），鏡 7。
- assets/footage/s08_ai.mp4 — v0.3.0 實錄 S8_t1（新訊息 AI 即時判定＋尚無查核機構證實），鏡 8。
- assets/footage/s09_wall.mp4 — v0.3.0 實錄 S9_t2（熱門牆＋知識庫搜尋），鏡 9。
- data/captured.json — 2026-09-16 實際執行 `--reset-sim`／`--poll` 的終端機輸出、`mentions.json`、`replies.jsonl`、分享網址（逐字）。
- assets/audio/shotNN.mp3 — edge-tts `zh-TW-YunJheNeural`（rate +8%）旁白，`tools/tts.py` 產生。

素材由 `tools/build_footage.mjs` 從 v0.3.0 的原始擷取影格重建（加速段與靜止延長預先烘進檔案）；
大型媒體檔不進 git。

## Customizations

- 旁白：分鏡「旁白」欄逐字（鏡 5、6 用 v0.3.0 微調版；鏡 10 依 2026-09-16 核准數字改寫）。
- 字幕：旁白逐句燒進畫面（單一 caption track），另輸出 `docs/demo/demo_v0.4.0.srt`。
- 實錄畫面加虛擬攝影機推近（punch-in）與放大鏡，讓判定、chip、橫幅、來源列看得清楚；不改動畫面內容。
- 強調框：在實錄座標上畫墨黑外框（chip、說明列、橫幅、空的來源區、知識庫規則句），跟著鏡頭移動；只標註、不取代介面像素。
- 鏡 10 數字卡：count-up。
- 不加背景音樂（負責人 2026-09-19 決定）；旁白片段加輕微淡入淡出。

## Notes

- 誠實原則：鏡 3–4 全程角標「模擬模式：流程與正式串接相同，正式上線需 Meta App Review」；
  網站畫面標「本機執行畫面」；加速段標「畫面加速」；可疑網址一律遮蔽；不用 fixtures；
  不放灰色「AI 暫時無法使用」卡；畫面無 news.google.com；無金鑰；不仿製 Threads／手機 UI 外框
  （手機鏡＝真實頁面放在素色圓角框）。
- 只在本機 render。不執行 `publish`、`cloud`、`lambda`、`cloudrun`、`auth`、`feedback`；遙測以
  `HYPERFRAMES_NO_TELEMETRY=1`／`DO_NOT_TRACK=1` 關閉。
- 視覺語言＝產品：白／#F7F7F8 底、墨黑 #111111、系統 CJK 字體（"Microsoft JhengHei", "Noto Sans TC", sans-serif），
  除了錄到的回覆文字以外不用 emoji。
- 成品規格：1920×1080、30 fps、H.264 yuv420p＋AAC、≤180 秒、<60 MB。
