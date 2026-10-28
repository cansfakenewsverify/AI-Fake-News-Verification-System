# AGENTS.md — 這個 repo 的規矩

給所有 AI 助理（Claude Code、Codex 或其他 agent）。**開工前先讀這份，再讀 `CLAUDE.md`**：
`CLAUDE.md` 是專案地圖（現況、架構、檔案、指令、程式慣例），這份只放規矩。規矩要改，只改這裡。

## 1. 跟負責人說話

負責人是廖晢勛，有 ADHD。每一則回覆都照下面寫：

- **繁體中文**，包括短的狀態回報與傳檔時的說明。長時間自己做事之後最容易不小心變成英文，送出前檢查整則。
- **第一行**是負責人現在就能做的事；**最後一行**是一個「Next：」，兩分鐘內做得完。清單最多 5 項，時間用分鐘估。
- 負責人不熟的後台（Render、Supabase、Meta、Vercel）**一次只給一步**，等「好了」或截圖再給下一步。
- 長的東西（要複製的文字、表格、操作手冊）寫進檔案，回覆裡只放連結。
- 給負責人跑的指令要能在 **PowerShell 5.1** 跑：用 `;` 串接、打 `curl.exe`、Python 用 `.\venv\Scripts\python`；
  需要 `cd` 時自成一行，每個指令放一個程式碼區塊。
- 公開的檔案裡不放負責人的 email 和 Threads 帳號。組員姓名：廖晢勛、石岱勳、姚睿、張宇宏、廖育翔（「育」）；
  指導教授黃崇源。

## 2. 機密（repo 是公開的）

- `code/backend/.env` 只給程式讀：要用某個設定時透過 `app.config.settings` 讀，回報時只說「有／沒有」。
  這個檔不打開、不 cat、不印出來。
- 金鑰只存在三個地方：本機 `.env`、Render 的 Environment 頁、GitHub repository secrets（只有 `ADMIN_TOKEN`；
  負責人 2026-10-28 決定不在 GitHub 放 `CGU_API_KEY`）。聊天、commit、issue、截圖、log 裡一律只寫鍵名。
  需要新金鑰時，請負責人自己貼進 `.env`、Render 或 GitHub。
- **雲端 session 只有 GitHub**：沒有金鑰，也連不到 CGU 與查核網站。要呼叫 CGU 的批次在**負責人電腦上**跑
  （那台電腦上的 Claude Code session，或負責人照指令自己跑；程式從本機 `.env` 讀金鑰）：雲端 session 寫程式、離線測試，
  再把步驟寫成一份指令檔（例：`docs/test/研究批次_本機執行.md`）。結果（不含訊息原文）commit 回分支。
  這類批次不放在 Render 跑，那是正式站。
- 這些東西不進 git：訊息原文（Cofacts 訊息可能含個資；報告只存查核網址、雜湊與判定）、Mixkit 原始音檔
  （授權不允許單獨散布原檔）、`docs/demo/*.mp4` 母片、runtime 資料。

## 3. 正式環境

- **推到 `main` 就是上線**：`code/backend/` 的變更會部署到 Render，前端會部署到 Vercel。
  程式碼等負責人說「推」才推；只動文件、影片專案或評測報告可以直接推，推完回報。
- 會寫正式資料庫的腳本預設是 dry-run，加 `--apply` 要先得到負責人同意。
- 到正式站查證會寫進正式知識庫：測試用真實、無害的訊息，確認一次就夠。

## 4. AI 額度（CGU AIR 閘道是唯一的 AI）

- 每週 USD 10、**週四重置**；週日 21:17 會跑每週評測。
- 會花錢的批次（評測、模型比較、重算 embedding）：開始前與每 100 題讀一次 `GET {CGU_BASE_URL}/me/usage`，
  保留 USD 3 給網站使用者；先試跑 50 題估花費再決定要不要全跑；排在週四重置之後，避開週日。
- `web_search` 保持關閉（每次呼叫貴 3～7 倍）。

## 5. 做事的方式

- 依票做：`docs/rebuild/03_tickets.md`。測試項目與缺陷：`docs/test/TP-FNV-2026-01.md`。
- **改程式前先讀 `CLAUDE.md` 第 7 節**（store 一律走 `store_factory`、阻塞 IO 包 `asyncio.to_thread`、外部網址走 `safe_url`、
  燈號只讀 `verdict.frame_of`、前端文案放 `i18n.js`、fallback 契約）。
- 改後端就跑 `pytest`（離線、不花額度）；改前端就跑 `npm run test:unit` 與 `npm run build`。都通過才 commit。
- **一次改完**：一個改動讓哪些文件過時（`CLAUDE.md`、各 README、runbook、`presentations/` 的報告資料、票），
  就在同一次工作全部更新，做完再回報改了哪些。兩個例外：某一天的測試紀錄保持當時的樣子；
  負責人逐字核准過的文字（例如向 Meta 登記的隱私政策）要先問再改。
- **誠實**：測試沒過就照實寫，附上輸出。門檻是實測校準出來的（例如向量快取的 0.75），不為了讓測試過關而調。
- **來源**：只有已經做出判定的查核來源才算來源（`CLAUDE.md` 第 9 節）。還在等人查證的投稿是髒資料，
  不能當來源，也不能寫成已證實資料。
- Windows 主控台是 cp950：Python 的 `print()` 只印中英文，不印 emoji 或 ✓✗。
- commit 訊息用中文，說明為什麼改；最後一行加 `Co-Authored-By: <模型名稱> <noreply@anthropic.com>`
  （不是 Claude 的 agent 寫自己的名稱與信箱）。

## 6. 影片（`video/hf-*`）

- 只在本機 render；HyperFrames 的 `publish`、`cloud`、`lambda`、`cloudrun`、`auth` 都不執行，遙測關閉。
- 每個影片專案的做法寫在它自己的 README（C 槽空間不夠時，render 的暫存目錄改到 E 槽）。
