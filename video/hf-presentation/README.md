# hf-presentation — 5 分鐘簡報影片（presentation_v1.3）

老師 2026-09-20 的規定：簡報就是一支**預先錄好、最長 5 分鐘、有旁白與音效**的影片，像「系統開箱文」，
要介紹整個系統的功能、所有操作與輸入輸出。規格在 `docs/demo/presentation_video_brief.md`，
製作紀錄在 `docs/demo/footage_log.md` 的 `presentation_v1.0`、`v1.1`、`v1.2` 三節。
v1.1（2026-09-22）只把旁白換成 `zh-TW-HsiaoChenNeural`，畫面與片長不變。
v1.2（2026-10-26）旁白改為口語版男聲 `zh-CN-YunjianNeural`（負責人從三個試聽樣本選定），事實同步到 10 月；
第 10、11 段加長到 37.5、39 秒，全片 4 分 41.5 秒。
v1.3（2026-10-28）旁白與畫面不變，只改聲音與字幕（與情境劇 `video/hf-scenario` 同一套，依 video-shotcraft skill 的準則）：
Mixkit 配樂鋪滿全片、旁白講話時自動壓低、在場景切換處重新開始；合成音效換成 Mixkit 真實音效；字幕 44 → 54 px；
開場的網址移到右上角、右欄重點清單排緊一點，讓放大的字幕不蓋到畫面上的字。

**只在本機 render。** 不執行 `publish`／`cloud`／`lambda`／`cloudrun`／`auth`／`feedback`，不登入任何服務；
遙測以 `HYPERFRAMES_NO_TELEMETRY=1`、`DO_NOT_TRACK=1` 關閉。
`video/hf-demo`（v0.4.0 進度報告 demo）完全沒有被動到，仍可獨立重現。

## 成品

| 檔案 | 說明 |
|------|------|
| `docs/demo/presentation_v1.3.mp4` | 母片 1920×1080、30 fps、H.264＋AAC（`docs/demo/*.mp4` 不進 git） |
| `docs/demo/presentation_v1.3.srt` | 字幕 |
| `code/frontend/public/demo/presentation_v1.mp4` | 網站用的壓縮版（**會提交**，<30 MB） |
| `presentations/2026-09_進度報告/06_簡報影片旁白稿.md` | 逐段旁白與時間碼，給組員重新配音用 |

## 從零重建

素材、旁白、音效、render 都不進 git。要重建全部：

```bash
node tools/capture.mjs          # 到正式站重錄畫面（會問後端要不要醒著；AI 呼叫上限 12 次）
node tools/build_footage.mjs    # 把原始影格剪成定速片段 assets/footage/*.mp4
..\..\code\backend\venv\Scripts\python tools\tts.py    # 旁白（edge-tts，免帳號）
..\..\code\backend\venv\Scripts\python tools\mixkit.py # 配樂與音效（Mixkit；要先裝 video-shotcraft skill，見 video/hf-scenario/README.md）
node tools/build_scenes.mjs     # 由 data/scenes.json 產生實錄場景
node tools/build_timeline.mjs   # 產生 index.html、字幕、SRT、schedule.json
node tools/build_sfx.mjs        # 把音效放到成片時間軸上（需要 schedule.json）
node tools/build_timeline.mjs   # 再跑一次，把音效寫進 index.html
npm run check                   # lint／runtime／layout／motion／contrast
npm run render
node tools/verify.mjs           # 片長、黑畫面、靜音、響度、抽樣影格
```

PowerShell 沒有 `&&`：上面每一行請分開貼。

## 要改東西的時候

| 想改什麼 | 改哪裡 |
|----------|--------|
| 旁白文字、讀音、聲音與語速 | `data/narration.json`（`voice`、`rate`；個別段落可另設 `rate`）→ 重跑 `tts.py`、`build_timeline.mjs`、`build_narration_doc.mjs` |
| 每段多長、段落順序、轉場 | `data/plan.json` 的 `shots`／`scenes` |
| 哪一段實錄怎麼剪（加速、剪掉空檔、靜止延長） | `data/plan.json` 的 `footage` → 重跑 `build_footage.mjs` |
| 實錄場景的鏡頭運動與右欄文字 | `data/scenes.json` → 重跑 `build_scenes.mjs` |
| 圖卡場景（開場、機器人、架構、數據、片尾） | `compositions/s01`、`s09`、`s10`、`s11`、`s12`（手寫，不是產生的） |
| 要錄哪些畫面、怎麼操作 | `tools/takes.mjs` |

`index.html`、`compositions/captions.html`、`compositions/chrome.html`、`compositions/s02`–`s08`
都是**產生的**，不要直接編輯。

## 誠實原則（畫面上看得到）

- 每個實錄鏡頭標「正式站實錄」；加速段標「畫面加速 ×N」，而且這些標籤是從實際剪輯資料算出來的，不是手寫的。
- Threads 那一段全程標「模擬模式…正式上線需 Meta App Review」。
- 可疑網址一律不透明遮蔽，底下沒有網址文字。
- 沒有假造的結果、沒有 fixtures、沒有未經查證的數字。
