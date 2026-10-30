# hf-scenario — 情境劇《轉傳之前》

第二次簡報（2026-11-02～11-04）的情境劇影片。老師的規定、劇本與拍攝清單在
`presentations/2026-11_第二次簡報/`（先看那裡的 README）。2026-10-27 起是「講解為主＋短劇」：
每個情境先演 10 秒，再講使用前的困擾、網站怎麼操作、使用後的好處。
**2026-10-30 起不拍真人**：旁白全部是負責人錄的 V1～V4，講解是大標題＋重點的講解畫面（`kind=talk`），
短劇併進手機畫面（`char` 角色頭像與情緒、`kind=call` 通話畫面），阿嬤、爸爸、網友的台詞用 AI 語音。

**只在本機 render。** 不執行 `publish`／`cloud`／`lambda`／`cloudrun`／`auth`／`feedback`，不登入任何服務；
遙測以 `HYPERFRAMES_NO_TELEMETRY=1`、`DO_NOT_TRACK=1` 關閉。

## 一份分鏡，兩種成品

所有畫面都由 `data/storyboard.json` 產生（`tools/build.mjs`），不要直接改 `compositions/` 與 `index.html`。
錄好的東西放進 `raw/`，重跑 `build.mjs`，有檔案的地方就自動換掉替身：

| 素材 | 檔名 | 有檔案時 | 沒有檔案時 |
|---|---|---|---|
| 旁白（負責人） | `raw/V1.m4a`～`V4.m4a`（手機錄音，副檔名不拘）；念的稿是 `presentations/2026-11_第二次簡報/04_配音稿.md`（`node tools/rec_sheet.mjs` 從分鏡產生） | 依句子之間的停頓切開，照順序對到各句 | AI 語音，右下角標「預覽版」 |
| Threads 錄螢幕（選做） | `raw/T1.mp4` | 依各步驟的 `segments` 剪（收到檔案後再設定） | 重繪的示意畫面（畫面上標明） |
| 實拍（目前不用） | `raw/<clip>`，只有 `kind=live` 的鏡頭會讀 | 實拍畫面與聲音；自動剪頭尾，字幕依停頓對齊 | 佔位字卡＋AI 語音 |

網站畫面一律是正式站實錄（`tools/capture.mjs`，三則訊息都是快取命中、不花 AI 額度），
`build.mjs` 依錄影時的標記（home、pasted、result_top…）切成教學步驟，配音比畫面長時停在最後一格；
講到判定和查核來源時，旁邊跳出那一塊畫面的放大截圖（手機畫面縮小後字太小，評審看不清楚）。
手機錄影不顯示滑鼠箭頭，只留點擊的波紋（`capture.mjs` 每次換頁都重新藏一次）。
旁白還是 AI 語音時右下角標「預覽版」；四個錄音檔都到了，標記自動消失。

`raw/`、`assets/footage/`、`assets/audio/`、`renders/` 都不進 git。網站錄影的原始影格在 `%TEMP%\fnv-scenario-raw`（`$FNV_RAW` 可改）。

## 從零重建

```bash
node tools/capture.mjs          # 到正式站錄三段手機畫面（都是快取命中，不花 AI 額度）
node tools/rec_sheet.mjs       # 配音稿（台詞有改才需要重跑）
..\..\code\backend\venv\Scripts\python tools\tts.py    # 角色台詞與預覽用旁白的 AI 語音（edge-tts，免帳號）
..\..\code\backend\venv\Scripts\python tools\mixkit.py # 配樂與音效（Mixkit；要先裝 video-shotcraft skill，見下面「聲音」）
..\..\code\backend\venv\Scripts\python tools\sfx.py    # 手機震動聲（numpy 合成）
node tools/build.mjs            # 剪步驟、處理組員的檔案、產生 compositions/、index.html、字幕
npm run check                   # lint／runtime／layout／motion／contrast
npm run render
```

PowerShell 沒有 `&&`：上面每一行請分開貼。

**C 槽空間不夠時**：多個 worker 的 render 會先把影格存成暫存檔（約 70 GB）。可以把暫存目錄改到空間夠的磁碟：
`$env:TEMP='E:\hf-render-tmp'; $env:TMP='E:\hf-render-tmp'`，再加 `--workers 5` render；或用 `npm run render`（單一 worker 串流，不需要暫存空間，但慢很多）。

## 聲音（2026-10-28 起）

照 [video-shotcraft](https://github.com/Vincentwei1021/video-shotcraft) skill 的聲音設計原則（安裝在 `~/.claude/skills/video-shotcraft`）：

- **配樂**：一首 Mixkit 音樂鋪滿全片（`storyboard.music`），在章節字卡重新開始；台詞之間音量 `gap`，有人講話時自動降到 `under`。
- **音效**：用真實的錄音（訊息通知、按鍵、唱片刮擦…）取代原本合成的電子音；手機震動仍用 `tools/sfx.py` 合成。
  短劇定格「先暫停一下」配唱片刮擦聲。
- 來源與授權記在 `data/mixkit_sources.json`：音樂 Mixkit Stock Music Free License、音效 Mixkit Sound Effects Free License，
  都可用在影片與教學用途、不需署名（片尾仍列出）。**授權不允許單獨散布原檔，所以 `assets/audio/` 不進 git。**
- 換配樂：改 `data/mixkit_sources.json` 的 `music.bgm.file`（skill 裡還有 `cat-walk`、`house-vibez`、`tonight-hiphop` 可選）→ `tools/mixkit.py` → `build.mjs`。

## 要改東西的時候

| 想改什麼 | 改哪裡 |
|----------|--------|
| 鏡頭順序、台詞、字卡、步驟清單 | `data/storyboard.json` → `tools/tts.py`（有改台詞時）→ `tools/rec_sheet.mjs`（改了旁白時，要重錄）→ `tools/build.mjs` |
| 講解畫面的大標題、重點 | 該鏡頭（`kind=talk`）的 `headline`、`chips`（`plain` 不加 ✓✕）；`slogan` 是置中的口號 |
| 短劇的角色 | 該鏡頭的 `char`（`who`、頭像字 `face`、情緒 `mood`）；`counter`、`pause` 可放在任何鏡頭 |
| 網站畫面每一步從哪裡切到哪裡 | 該步驟的 `segments`（錄影標記名稱或秒數；`speed` 加速、`label` 標示） |
| 要錄哪些網站畫面、標記放哪裡 | `tools/takes.mjs` |
| 實拍鏡頭的頭尾 | 預設自動（第一句前保留 `lead` 秒、最後一句後 0.6 秒）；要自己指定就設 `"trim": [開始秒, 結束秒]` |
| 配音切句切錯 | `"recCuts": { "V1": [[開始, 結束], …] }`（秒數，以清理後的 `assets/audio/rec/V1.wav` 為準） |
| 字卡出現的時間 | `at`：秒數，或 `line1`（第 2 句開始）、`line1.1`（第 2 句的第 2 段字幕）、`line0@0.5`（第 1 句一半）、`line0end` |
| 配樂的音量、從哪裡重新開始 | `storyboard.music`（`gap`、`under`、`restartAt`）；音效音量在 `build.mjs` 的 `SOUND`，單次可加 `vol` |
| 手機旁放大的訊息原文 | 該鏡頭的 `quote` |
| 網站畫面某一塊的放大截圖（判定、查核來源） | 該步驟的 `zoom`：`time` 取哪一刻（錄影標記，可寫 `result_top-2`）、`box` 是 [x, y, 寬, 高]（手機畫面的 CSS 像素） |

## 誠實原則（畫面上看得到）

- 片頭說明「本片情節虛構；系統畫面皆為正式站實錄」。
- 網站畫面標「正式站實錄」，加速的部分標「畫面加速 ×N」（倍數從分鏡的 `speed` 來，不是另外手寫的）。
- 阿嬤、爸爸、網友的台詞是 AI 語音，片頭與片尾寫明；旁白是負責人本人。
- Threads 那一段在負責人錄 T1 之前是重繪的示意畫面，畫面上標明；機器人目前是測試版，只回覆測試人員，片中有說明。
- 簡訊的電話號碼遮蔽；群組聊天是示意介面，不是任何 App 的截圖。
