# hf-scenario — 情境劇《轉傳之前》

第二次簡報（2026-11-02～11-04）的情境劇影片。老師的規定、劇本與拍攝清單在
`presentations/2026-11_第二次簡報/`（先看那裡的 README）。

**只在本機 render。** 不執行 `publish`／`cloud`／`lambda`／`cloudrun`／`auth`／`feedback`，不登入任何服務；
遙測以 `HYPERFRAMES_NO_TELEMETRY=1`、`DO_NOT_TRACK=1` 關閉。

## 一份分鏡，兩種成品

所有畫面都由 `data/storyboard.json` 產生（`tools/build.mjs`），不要直接改 `compositions/` 與 `index.html`。

- **分鏡預覽片**：組員還沒拍之前，真人鏡頭是佔位字卡，台詞用 AI 語音念，畫面右下角標「分鏡預覽版」。
- **正式片**：組員拍的影片放進 `raw/`（檔名照拍攝清單，例如 `raw/S01.mp4`），重跑 `build.mjs`，
  有影片的鏡頭就自動換成實拍畫面，台詞改用演員自己的聲音（自動降噪、響度統一）；旁白一律是 AI 語音
  （`zh-CN-YunjianNeural`，負責人 2026-10-26 選定，和開箱影片 v1.2 同一個聲音）。

`raw/`、`assets/footage/`、`assets/audio/`、`renders/` 都不進 git。

## 從零重建

```bash
node tools/capture.mjs          # 到正式站錄三段手機畫面（都是快取命中，不花 AI 額度）
node tools/build_footage.mjs    # 依 data/plan.json 剪成定速片段（加速段在畫面上標倍數）
..\..\code\backend\venv\Scripts\python tools\tts.py    # 旁白與預覽用的台詞（edge-tts，免帳號）
..\..\code\backend\venv\Scripts\python tools\sfx.py    # 音效（numpy 合成：叮咚、轉傳、震動、倒帶…）
node tools/build.mjs            # 產生 compositions/、index.html、字幕
npm run check                   # lint／runtime／layout／motion／contrast
npm run render
```

PowerShell 沒有 `&&`：上面每一行請分開貼。

**C 槽空間不夠時**：多個 worker 的 render 會先把影格存成暫存檔（約 70 GB）。可以把暫存目錄改到空間夠的磁碟：
`$env:TEMP='E:\hf-render-tmp'; $env:TMP='E:\hf-render-tmp'`，再 render；或用 `npm run render`（單一 worker 串流，不需要暫存空間，但慢很多）。

## 要改東西的時候

| 想改什麼 | 改哪裡 |
|----------|--------|
| 鏡頭順序、長度、台詞、字卡、好處標籤 | `data/storyboard.json` → `tools/tts.py`（有改台詞時）→ `tools/build.mjs` |
| 某個實拍鏡頭只用一段 | 該鏡頭加 `"trim": [開始秒, 結束秒]` |
| 台詞在實拍影片中的時間 | 該句的 `at`（字幕會跟著移動） |
| 網站實錄怎麼剪、哪段加速 | `data/plan.json` 的 `footage` → `tools/build_footage.mjs` |
| 要錄哪些網站畫面 | `tools/takes.mjs` |

## 誠實原則（畫面上看得到）

- 片頭說明「本片情節虛構；系統畫面皆為正式站實錄」。
- 網站畫面標「正式站實錄」，加速的部分標「畫面加速 ×N」（倍數從剪輯資料算出來，不是手寫的）。
- Threads 那一段在組員錄影之前是示意畫面，畫面上標明；機器人目前是測試版，只回覆測試人員，片中有字幕說明。
- 簡訊的電話號碼遮蔽；群組聊天是示意介面，不是任何 App 的截圖。
