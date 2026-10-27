# hf-scenario — 情境劇《轉傳之前》

第二次簡報（2026-11-02～11-04）的情境劇影片。老師的規定、劇本與拍攝清單在
`presentations/2026-11_第二次簡報/`（先看那裡的 README）。2026-10-27 起是「講解為主＋短劇」：
每個情境先演 10 秒，再由組員講使用前的困擾、網站怎麼操作、使用後的好處。

**只在本機 render。** 不執行 `publish`／`cloud`／`lambda`／`cloudrun`／`auth`／`feedback`，不登入任何服務；
遙測以 `HYPERFRAMES_NO_TELEMETRY=1`、`DO_NOT_TRACK=1` 關閉。

## 一份分鏡，兩種成品

所有畫面都由 `data/storyboard.json` 產生（`tools/build.mjs`），不要直接改 `compositions/` 與 `index.html`。
組員錄的東西放進 `raw/`（檔名照拍攝清單），重跑 `build.mjs`，有檔案的地方就自動換掉替身：

| 素材 | 檔名 | 有檔案時 | 沒有檔案時（分鏡預覽片） |
|---|---|---|---|
| 對鏡頭講解、短劇 | `raw/S01.mp4`～`S13.mp4`（`.mov` 也可以；沒有 `S04.mp4` 時用最後一次 `S04_N`） | 實拍畫面與聲音；自動剪掉講話前後的空白，字幕依停頓對齊 | 佔位字卡＋AI 語音 |
| 網站操作的配音 | `raw/V1.m4a`～`V4.m4a`（手機錄音，副檔名不拘） | 依句子之間的停頓切開，照順序對到各句 | AI 語音 |
| Threads 錄螢幕 | `raw/T1.mp4` | 依各步驟的 `segments` 剪（收到檔案後再設定） | 示意畫面（畫面上標明） |

網站畫面一律是正式站實錄（`tools/capture.mjs`，三則訊息都是快取命中、不花 AI 額度），
`build.mjs` 依錄影時的標記（home、pasted、result_top…）切成教學步驟，配音比畫面長時停在最後一格。
預覽片右下角標「分鏡預覽版」；所有替身都換掉後，標記自動消失。

`raw/`、`assets/footage/`、`assets/audio/`、`renders/` 都不進 git。網站錄影的原始影格在 `%TEMP%\fnv-scenario-raw`（`$FNV_RAW` 可改）。

## 從零重建

```bash
node tools/capture.mjs          # 到正式站錄三段手機畫面（都是快取命中，不花 AI 額度）
..\..\code\backend\venv\Scripts\python tools\tts.py    # 預覽用的 AI 替身語音（edge-tts，免帳號）
..\..\code\backend\venv\Scripts\python tools\sfx.py    # 音效（numpy 合成：叮咚、點擊、震動…）
node tools/build.mjs            # 剪步驟、處理組員的檔案、產生 compositions/、index.html、字幕
npm run check                   # lint／runtime／layout／motion／contrast
npm run render
```

PowerShell 沒有 `&&`：上面每一行請分開貼。

**C 槽空間不夠時**：多個 worker 的 render 會先把影格存成暫存檔（約 70 GB）。可以把暫存目錄改到空間夠的磁碟：
`$env:TEMP='E:\hf-render-tmp'; $env:TMP='E:\hf-render-tmp'`，再加 `--workers 5` render；或用 `npm run render`（單一 worker 串流，不需要暫存空間，但慢很多）。

## 要改東西的時候

| 想改什麼 | 改哪裡 |
|----------|--------|
| 鏡頭順序、台詞、字卡、步驟清單 | `data/storyboard.json` → `tools/tts.py`（有改台詞時）→ `tools/build.mjs` |
| 網站畫面每一步從哪裡切到哪裡 | 該步驟的 `segments`（錄影標記名稱或秒數；`speed` 加速、`label` 標示） |
| 要錄哪些網站畫面、標記放哪裡 | `tools/takes.mjs` |
| 實拍鏡頭的頭尾 | 預設自動（第一句前保留 `lead` 秒、最後一句後 0.6 秒）；要自己指定就設 `"trim": [開始秒, 結束秒]` |
| 配音切句切錯 | `"recCuts": { "V1": [[開始, 結束], …] }`（秒數，以清理後的 `assets/audio/rec/V1.wav` 為準） |
| 字卡出現的時間 | `at`：秒數，或 `line1`（第 2 句開始）、`line1.1`（第 2 句的第 2 段字幕）、`line0@0.5`（第 1 句一半）、`line0end` |

## 誠實原則（畫面上看得到）

- 片頭說明「本片情節虛構；系統畫面皆為正式站實錄」。
- 網站畫面標「正式站實錄」，加速的部分標「畫面加速 ×N」（倍數從分鏡的 `speed` 來，不是另外手寫的）。
- Threads 那一段在組員錄影之前是示意畫面，畫面上標明；機器人目前是測試版，只回覆測試人員，片中有說明。
- 簡訊的電話號碼遮蔽；群組聊天是示意介面，不是任何 App 的截圖。
