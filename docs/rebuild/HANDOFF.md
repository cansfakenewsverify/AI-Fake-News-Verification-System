# 交接說明（2026-09-20 下午）

給下一個接手的 AI 助理。**不要重新掃描整個專案**：先讀 `CLAUDE.md` 最上面的現況區塊與第 12 節，再讀這份，就能開始做事。

## 現況（都已完成並推上 GitHub main）

- 系統已上線：<https://fakenewsverify.vercel.app>（前端 Vercel → 後端 Render `https://fakenewsverify-api.onrender.com` → Supabase Postgres + pgvector；AI 走學校 CGU AIR `gpt-5.4-mini`）。金鑰只在負責人本機 `code/backend/.env` 與 Render 後台。
- 專案位置已從 `OneDrive\桌面` 搬到 **`C:\Users\user\Desktop\AI-Fake-News-Verification-System`**。舊位置不要再用。venv 搬過家：一律用 `.\venv\Scripts\python -m pytest／pip／uvicorn`。
- 測試：後端 700 passed（另 24 個 Postgres 契約測試需 `RUN_PG_TESTS=1`）、前端 385 passed、CI 綠。
- 測試計畫書 `docs/test/TP-FNV-2026-01.md` **v1.5**（6.5 是 9/19–20 重測：P0 27／30；PF-2 仍未通過、UI-1 與 UI-6 未執行）。PDF 在 `presentations/2026-09_進度報告/04_測試計畫書_TP-FNV-2026-01_v1.5.pdf`。
- 報告資料夾 `presentations/2026-09_進度報告/`：投影片（pptx／pdf）、報告內容說明、demo 影片網址、測試計畫書 PDF、分工表。
- 團隊：廖晢勛（負責人，A 測試負責人；就是跟你對話的人）、石岱勳（B 介面測試）、姚睿（C 績效與品質數據）、張宇宏（D 文件與審查）、廖育翔（E 影片與簡報；「育」不是「昱」）。指導教授黃崇源。正式專題名稱「AI 為核心的假訊息驗證系統」，網站名稱「全民查證公社」。

## 老師 2026-09-20 的新規定（最重要）

1. 簡報（9/21–9/23）**就是一支預先錄好的影片，最長 5 分鐘**，要有旁白與音效，像「系統開箱文」：介紹整個系統的功能、所有操作、輸入與輸出。黃崇源、陳仁暉兩位老師現場看影片評分；張哲維老師事後看 GitHub 評分。
2. 書面報告要給指導教授簽名；報告當天繳紙本：**書面報告、自評表、評分表，各印 3 份**；自備筆電。
3. 空白表單在 `docs/course_forms/`（自評表、評分表，各 3 頁，九項核心能力）。

## 待辦（依優先順序；第 1 項已完成）

1. ~~**5 分鐘簡報影片**~~ **已完成（2026-09-20）**：`presentation_v1.0`，4 分 38 秒。
   網址 <https://fakenewsverify.vercel.app/demo/presentation_v1.mp4>，網站用檔已提交在
   `code/frontend/public/demo/presentation_v1.mp4`；母片與字幕在 `docs/demo/presentation_v1.0.mp4`／`.srt`。
   原始碼 `video/hf-presentation/`（該資料夾的 README 寫了怎麼重建與怎麼改），旁白稿
   `presentations/2026-09_進度報告/06_簡報影片旁白稿.md`，製作紀錄 `docs/demo/footage_log.md`。
   **畫面全部是正式站實錄**（2026-09-20 用 headless Edge 重錄），整支片只花掉 1 次正式站的 AI 查證。
   負責人還沒聽過聲音：旁白與音效請實際播一次。

2. **自評表草稿**：`presentations/2026-09_進度報告/07_自評表草稿.md` 已寫好九項的等級建議與說明文字，請負責人確認後抄到紙本（或做成可列印的 PDF）。評分表只要填表頭（團隊成員、指導教授、專題名稱）。
3. **列印與簽名**（只有負責人能做）：測試計畫書 PDF 給黃崇源老師簽 §6.4；三種文件各印 3 份。
4. PF-2 重測：等姚睿填好 `docs/test/pf2_worksheet.csv`（說明在 `docs/test/PF-2_出題說明.md`），負責人確認後，用本機後端跑 20 句、記錄 `cache_layer`，結果寫進計畫書 6.5（**不可調低 0.75 門檻、不可回頭改句子**）。
5. 後端防休眠：GitHub Actions 的 keepalive 實際每 2–5 小時才跑一次，Render 還是會睡（前端已能撐過冷啟動約 1 分鐘）。建議在 Supabase 用 `pg_cron` + `pg_net` 每 10 分鐘打 `/health`——**這是在負責人的資料庫新增常駐設定，要先得到他明確同意**（已問過兩次，尚未回答）。
6. 雲端知識庫補 demo 用的 gold 列（細節在 `CLAUDE.md` 第 8 節待辦）。
7. UI-1（深色全套截圖＋石岱勳勾核、張宇宏覆核）、UI-6（OpenCC 簡繁比對；英文字允許清單要老師裁定）。
8. **雲端知識庫有 24 筆的「查核來源」是 Cofacts 的回報文章／討論頁，卻標成 Tier 1「查核機構」**
   （2026-09-20 讀 `/api/knowledge?limit=200` 發現；其中幾筆的來源標題就是詐騙訊息原文）。
   這違反「只有已做出判定的查核來源才算來源」。簡報影片已避開這些列，但資料本身要清掉或重新標記。
9. 熱門牆的「資料更新時間」停在 2026-07-12（雲端排程關閉，目前為手動更新），簡報影片裡看得到這行字。

## 和負責人合作的規則（他已經講過，不要讓他再講一次）

- 他有 ADHD：每則回覆第一行就是他現在可以做的事，最後一行是「Next：一個兩分鐘內能做的動作」；清單最多 5 項；繁體中文；不要前言與客套。要他操作陌生網站時，一次只給一步。
- 他的終端機是 PowerShell 5.1：給他的指令不能用 `&&`，路徑用反斜線並加引號。
- 絕不讀、不印、不改 `code/backend/.env`；金鑰不進聊天、不進 git。
- 改了東西就把所有受影響的文件、投影片、腳本一次同步完，不要逐項問他；但「當時的紀錄」（例如測試計畫書第一輪結果）不改寫。
- 只有已做出判定的查核來源才算來源；沒有就顯示「尚無查核機構證實」。不為了讓測試通過而放寬準則。
- commit 訊息結尾加 `Co-Authored-By: <模型名稱> <noreply@anthropic.com>`；直接推 main（他要的工作方式）。
