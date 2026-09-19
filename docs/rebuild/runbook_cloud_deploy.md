# Runbook：後端上雲（Render 免費方案 + Supabase）

> 目標：後端不再靠你的電腦 + tunnel，改跑在 Render 免費主機；資料放 Supabase；AI 仍走學校 CGU AIR 閘道。
> 前端不動，仍是 `https://fakenewsverify.vercel.app`。
>
> **負責人只需要做 Part A（約 10 分鐘 + 等待 3–8 分鐘）。** Part B 由 Claude 做。Part C、D 是說明，有空再看。
>
> 畫面上的按鈕文字都對照過官方文件（2026-09-19，來源見附錄 3）。標「以畫面為準」的是查不到官方寫法的地方。

相關檔案：

| 檔案 | 用途 |
|---|---|
| `render.yaml`（repo 根目錄） | Render Blueprint：一個免費 web service 的全部設定 |
| `code/backend/requirements-prod.txt` | 雲端只裝執行需要的套件（不含 pytest、評測繪圖等） |
| `.github/workflows/keepalive.yml` | 每 10 分鐘叫醒後端、順便碰一下資料庫 |
| `code/frontend/vercel.json` | Part B 會改其中一行，把 `/api` 導到 Render |

---

## 開始前（Claude 確認，負責人不用做）

Part A 之前這三件事要成立，否則 Render 會讀不到設定，或部署出一個沒接資料庫的空殼：

1. 儲存層（`STORAGE_BACKEND=supabase`）已完成並 push 到 `main`，Supabase 裡已有知識庫與熱門資料。
2. `render.yaml`、`code/backend/requirements-prod.txt`、`.github/workflows/keepalive.yml` 已 push 到 `main`。
3. CI 綠：`gh run list --workflow ci.yml --limit 1` 顯示 `completed success`。

三件都成立後，Claude 告訴負責人：「可以開始 Part A」。

---

## Part A — 負責人：在 Render 建立服務

> **金鑰只貼進 Render 的輸入框。不要貼到聊天、不要 commit、不要截圖到金鑰。**
> 卡住就停在那一步，把畫面截圖給 Claude（先確認截圖裡沒有金鑰）。

### A1. 把四個值準備好（約 2 分鐘）

1. 用記事本打開 `code\backend\.env`。
2. 找到 `CGU_API_KEY=` 這一行。等一下要複製等號右邊的值。
3. 找到 `EMBED_API_KEY=` 這一行。（它和 `CGU_API_KEY` 是同一把金鑰；這行是空的就用 `CGU_API_KEY` 的值。）
4. 找到 `SUPABASE_DB_URL=` 這一行。值很長，開頭是 `postgresql://`，中間有 `pooler.supabase.com`。
5. 找到 `ADMIN_TOKEN=` 這一行。是 32 個字的亂數。雲端用同一個值最簡單。
6. 記事本先不要關。

注意：

- 只複製等號右邊。值的前後如果有引號 `"`，不要複製引號。尾巴不要多複製到空白或換行。
- `SUPABASE_DB_URL` 裡不能還留著 `[YOUR-PASSWORD]` 這幾個字（那代表密碼還沒填）。

成功長這樣：四行都找到了，記事本開著。

### A2. 登入 Render（約 3 分鐘）

7. 打開 <https://github.com>，看右上角頭像，確認登入的是 **`cansfakenewsverify`**（repo 的擁有者），不是 `soymilk0211`。不是的話先登出再登入。
8. 打開 <https://dashboard.render.com>。
9. 選擇用 GitHub 登入（按鈕文字以畫面為準）。
10. GitHub 問要不要授權 Render，按同意。
11. Render 如果問問卷或工作區名稱，隨意填或略過（以畫面為準）。

如果畫面要求填信用卡：先停下來告訴 Claude，不要填。官方教學寫免費資源「No payment is required」，但網路上有人回報 Blueprint 流程偶爾會要求；遇到時改走附錄 1 的手動建立。

成功長這樣：看到 Render 的 Dashboard 首頁，上方有 **New** 按鈕。

### A3. 用 Blueprint 建立服務（約 4 分鐘）

12. 按 **New**，再按 **Blueprint**。
13. 在清單找到 `AI-Fake-News-Verification-System`，按它右邊的 **Connect**。
    - 清單裡沒有這個 repo：打開 <https://github.com/apps/render/installations/new>，選 `cansfakenewsverify`，在 **Repository access** 選 **Only select repositories**，勾這個 repo，儲存（按鈕以畫面為準）。回 Render 重新整理，再做第 13 步。
14. Blueprint 名稱欄輸入：`fakenewsverify`
15. 分支（branch）選：`main`
16. **Blueprint Path** 不要改（預設就是 repo 根目錄的 `render.yaml`）。
17. 看畫面列出的「即將建立的資源」：應該只有一個 web service，名稱 `fakenewsverify-api`。
    - 如果出現紅色錯誤訊息：截圖給 Claude（這個畫面沒有金鑰，可以截），先不要往下。
18. 畫面會要你填四個空白的值（位置以畫面為準）。在 `CGU_API_KEY` 那格貼上 A1 第 2 步的值。
19. 在 `EMBED_API_KEY` 那格貼上 A1 第 3 步的值。
20. 在 `SUPABASE_DB_URL` 那格貼上 A1 第 4 步的值。
21. 在 `ADMIN_TOKEN` 那格貼上 A1 第 5 步的值。
22. 按 **Deploy Blueprint**。
23. 關掉記事本（不要存檔）。

成功長這樣：畫面開始跑建立進度，出現服務 `fakenewsverify-api`。

> 這四個值只有「第一次建立 Blueprint」時會問。之後要改：服務頁左邊 **Environment** → 改值 → **Save and deploy**。

### A4. 等它變 Live（等待約 3–8 分鐘，可以離開去做別的事）

24. 點進服務 `fakenewsverify-api`。
25. 等部署狀態變成 **Live**。第一次要裝套件，會比較久。
26. （這一步可以跳過，第 28 步會用更簡單的方法確認同一件事。）按左邊的 **Logs**，在最後面附近（`Application startup complete` 上面幾行）找開頭是 `Storage backend:` 的那一行。
27. 複製服務頁上方的網址，長得像 `https://fakenewsverify-api.onrender.com`（名稱被別人用過時後面會多幾個字，以畫面為準）。
28. 瀏覽器開新分頁，網址列貼上「剛剛的網址」再加 `/health`，按 Enter。
29. 再開一個分頁，貼上「剛剛的網址」再加 `/api/knowledge/stats`，按 Enter。

成功長這樣：

- 第 28 步那一行字裡有 `"storage_backend":"supabase"`（第 26 步的 log 則是 `Storage backend: supabase`）。
  - 如果是 `"storage_backend":"local"`（log 是 `SUPABASE_DB_URL is empty: using local files`）：代表 `SUPABASE_DB_URL` 沒貼進去。左邊 **Environment** → 把它補上 → **Save and deploy** → 回到第 25 步。**這一項很重要**：沒接上 Supabase 時網站看起來一切正常，但資料其實寫在暫時硬碟，主機一休眠就全部消失。
- 第 28 步那一行字裡還有 `"status":"healthy"`、`"ai_available":true`、`"daily_ai_calls":{"used":0,"cap":300}`（`used` 的數字不一定是 0）。
- 第 29 步看到 `"total":` 後面是一個大於 0 的數字。

### 回傳給 Claude（這三樣都沒有金鑰，可以直接貼）

1. 第 27 步的網址。
2. 第 28 步頁面上的那一行字。
3. 第 29 步的 `total` 數字。

失敗時：服務頁左邊 **Logs**，把最後 30 行左右截圖給 Claude。**不要截 Environment 頁**（那頁有金鑰）。

---

## Part B — Claude：把前端接到 Render（約 10 分鐘）

前提：負責人已回傳 Render 網址。以下用 `<RENDER_URL>` 代表，例如 `https://fakenewsverify-api.onrender.com`。
PowerShell 裡請打 `curl.exe`（`curl` 在 Windows PowerShell 5.1 是別的指令的別名）。

1. 直接打 Render 確認後端活著（休眠中第一次可能要等約 1 分鐘）：
   ```powershell
   curl.exe -s -o NUL -w "%{http_code}\n" --max-time 90 <RENDER_URL>/health
   curl.exe -s --max-time 90 <RENDER_URL>/api/knowledge/stats
   ```
   成功：第一行印 `200`；第二行回 JSON 且 `total` 不是 0。
   注意：`total` 有數字**不能**證明已接上 Supabase——沒接上時後端會默默退回 repo 裡的種子檔 `data/knowledge_base.parquet`，數字看起來差不多。是否接上以第 7 步為準。

2. 改 `code/frontend/vercel.json` **第 6 行，只改主機名這一處**（SPA fallback 那條不動）：

   改之前：
   ```json
         "destination": "https://REPLACE-ME.trycloudflare.com/api/$1"
   ```
   改之後（主機換成負責人回傳的那個）：
   ```json
         "destination": "https://fakenewsverify-api.onrender.com/api/$1"
   ```

3. 確認 JSON 合法（在 `code/frontend` 執行，退出碼 0）：
   ```powershell
   node -e "JSON.parse(require('fs').readFileSync('vercel.json','utf8'))"
   ```

4. 取得負責人同意後 commit + push 到 `main`。Vercel 會自動重新部署，等到 Ready（通常 2 分鐘內）。

5. 驗證前端同源代理：
   ```powershell
   curl.exe -s -o NUL -w "%{http_code}\n" --max-time 120 https://fakenewsverify.vercel.app/api/health
   curl.exe -s -o NUL -w "%{http_code}\n" https://fakenewsverify.vercel.app/privacy.html
   ```
   成功：兩行都印 `200`。（Vercel 對外部代理的逾時是 120 秒，足夠等 Render 醒來。）

6. 真的查證一次，確認 Render 連得到 CGU 閘道（會花一點點 AI 額度，約 USD 0.01）。中文內容先寫成 UTF-8 暫存檔再送，避免主控台編碼問題（Git Bash；暫存檔不要放進 repo）：
   ```bash
   body="$(mktemp)"
   printf '{"content":"網傳喝高濃度酒精可以殺死體內病毒"}' > "$body"
   curl -s --max-time 120 -X POST https://fakenewsverify.vercel.app/api/analyze/sync -H "Content-Type: application/json" --data-binary @"$body"
   rm -f "$body"
   ```
   成功：回應裡 `"ai_unavailable":false`，`risk_type` 是 `SCAM`／`MISINFO`／`SAFE` 之一。記下 `result_id`。
   如果 `ai_unavailable` 是 `true`：看 Render 的 **Logs** 找 `[AI] cgu HTTP ...` 那一行（金鑰貼錯、額度用完，或閘道擋 Render 的 IP）。

7. **（必做）** 確認資料真的寫進 Supabase，而不是 Render 的暫時硬碟。`app/config.py` 的 `use_supabase` 要 `STORAGE_BACKEND=supabase`「且」`SUPABASE_DB_URL` 非空才成立；URL 沒貼到時後端只在 log 警告一行就退回本機檔案，網站表面上一切正常。兩種證據至少要有一種：
   - (a) `curl.exe -s <RENDER_URL>/health` 的回應裡有 `"storage_backend":"supabase"`，且第 1 步的 stats 回 `200`。
   - (b) 重啟測試（端到端，負責人有空時建議做一次）：請負責人在 Render 服務頁按 **Manual Deploy** → **Restart service**，等回到 **Live** 後：
     ```powershell
     curl.exe -s -o NUL -w "%{http_code}\n" --max-time 90 https://fakenewsverify.vercel.app/api/result/<result_id>
     ```
     成功：印 `200`（第 6 步的結果在重啟後還在）。

   `/health` 是 `"storage_backend":"local"`，或 (b) 印 `404`：`SUPABASE_DB_URL` 沒生效。請負責人到 **Environment** 補上 → **Save and deploy**，再重做第 6、7 步。補上後仍 `404` 才是儲存層的問題。

8. 設定 keepalive 要打的網址（這是公開資訊，用 variable 不用 secret），並手動跑一次：
   ```powershell
   gh variable set BACKEND_BASE_URL --body <RENDER_URL>
   gh workflow run keepalive.yml
   gh run list --workflow keepalive.yml --limit 1
   gh run view <run-id> --log
   ```
   成功：log 裡有 `GET /health -> http 200` 與 `GET /api/knowledge/stats -> http 200`。
   如果 `gh variable set` 回 403：請負責人用 `cansfakenewsverify` 到 repo 的 **Settings** → **Secrets and variables** → **Actions** → **Variables** 分頁 → **New repository variable**，Name 填 `BACKEND_BASE_URL`，Value 填 `<RENDER_URL>`。

9. 收尾：更新 `CLAUDE.md`（部署現況、第 5 節指令、第 8 節待辦）與 `docs/rebuild/runbook_tunnel.md`（註明 tunnel 現在是退路）。

---

## Part C — 免費方案會怎樣、怎麼退回、安全檢查

### C1. 免費方案的行為（白話版）

| 你會遇到的事 | 原因 | 怎麼辦 |
|---|---|---|
| 一陣子沒人用，第一次打開要等約 1 分鐘，或前端暫時顯示連不到後端 | Render 免費服務 **15 分鐘沒有流量就休眠**，下一個請求進來才喚醒，喚醒約 1 分鐘 | 等 1 分鐘再試。`keepalive` 每 10 分鐘叫它一次，大幅減少這種情況，但不保證（GitHub 排程尖峰時會延遲或漏跑） |
| 月底服務突然全停 | 每個 workspace 每月 **750 小時**免費時數；用完後所有免費服務暫停到下個月 | 一個服務整月開著最多 744 小時，剛好夠。**同一個 Render 帳號不要再開第二個免費 web service** |
| 重新部署或重啟後，本機檔案不見了 | 免費主機的硬碟是暫時的，每次部署、重啟、休眠都會清空；Render 也可能隨時重啟免費服務 | 所以資料放 Supabase（`STORAGE_BACKEND=supabase`）。沒搬進 Supabase 的東西不要指望它留著 |
| 速度比你的電腦慢 | 免費主機規格是 0.1 CPU、512 MB 記憶體 | 正常。本機實測後端閒置約 140 MB、讀知識庫後約 190 MB，記憶體夠用 |
| 收到 Supabase 的警告信 | Supabase 免費專案 **7 天內資料庫活動太少會被暫停**，暫停前約一週會寄信 | `keepalive` 每輪打一次 `/api/knowledge/stats`（會讀資料庫）就是為了這個。真的被暫停：到 Supabase Dashboard 點進專案，按 **Resume project**（官方文件寫暫停後 1 年內可還原，以畫面為準） |
| keepalive 自己停了 | 公開 repo **連續 60 天沒有任何活動**，GitHub 會自動停用排程 | 到 repo 的 **Actions** 頁重新啟用（按鈕以畫面為準），或隨便 push 一次 |
| AI 額度 | CGU 額度 USD 10（spec §9）。雲端已關掉最花錢的兩項：`USE_WEB_SEARCH=false`、`ENABLE_SCHEDULER=false`；三層快取命中時不花額度 | 見下方「額度護欄現況」 |

額度護欄（2026-09-19 已實作，數值寫在 `render.yaml`）：

- **每日 AI 次數上限** `DAILY_AI_CALL_CAP=300`（spec FR-14）：一天最多真的呼叫 AI 300 次，台灣時間 00:00 歸零。達上限後，沒查過的內容回 429「今日查證額度已用完」，**已查過的內容照常命中快取**。計數存在 Supabase（`ai_usage_daily` 表），主機休眠、重啟不歸零。`<RENDER_URL>/health` 的 `"daily_ai_calls":{"used":12,"cap":300}` 就是今天的用量；顯示 `null` 代表上限被關掉（設成 0）。以實測單價估算，300 次約 USD 0.3–0.6。
- **每 IP 限速** `RATE_LIMIT_PER_MINUTE=30`、`RATE_LIMIT_PER_HOUR=200`：超過回 429「查證太頻繁」。數字刻意寬鬆，因為同一間教室／校園 Wi-Fi 的所有人對外是同一個 IP。這一項存在記憶體，重啟歸零（沒關係，守預算的是上一項）。
- **請求大小上限**：一般請求 1 MB、圖片 10 MB，超過回 413。
- 要調整：改 `render.yaml` 的數值再 push（後台改的值下次 Blueprint 同步會被檔案蓋回去）。
- 仍建議每隔幾天查一次 CGU 用量（`GET {CGU_BASE_URL}/me/usage`，做法見 `scripts/batch_verify_pending.py`）。

Render 官方對免費方案的原話是「不要用在 production」。對專題 demo 與報告足夠；要長期公開服務再考慮付費方案。

### C2. 怎麼退回（回到你的電腦 + tunnel）

1. 本機啟動後端：專案根目錄執行 `.\start.bat`。
2. 另開視窗啟動 tunnel，複製 `https://xxxx.trycloudflare.com`（步驟見 `runbook_tunnel.md` 第 2 節）。
3. 把 `code/frontend/vercel.json` 第 6 行的主機改回 tunnel 主機：
   ```json
         "destination": "https://xxxx.trycloudflare.com/api/$1"
   ```
4. commit + push，等 Vercel Ready。
5. 確認 `https://fakenewsverify.vercel.app/api/health` 回 `200`。
6. 停掉 keepalive，免得白白叫醒 Render：`gh workflow disable keepalive.yml`（要恢復時 `gh workflow enable keepalive.yml`）。

整個退回不到 5 分鐘，Render 上的服務不用刪（沒流量會自己休眠，不耗時數）。
注意：本機 `.env` 若是 `STORAGE_BACKEND=local`，退回後看到的是本機檔案裡的舊資料，不是 Supabase 那一份。

### C3. 安全檢查清單

- [ ] 金鑰只存在兩個地方：本機 `code/backend/.env`（已 gitignore）與 Render 的 **Environment** 頁。`render.yaml` 裡只有鍵名、沒有值（這個 repo 是公開的）。
- [ ] 沒有把金鑰貼到聊天、issue、commit、截圖。貼錯了就當作已外洩：換一把（CGU 金鑰找學校重發；資料庫密碼到 Supabase 重設，位置以畫面為準），本機 `.env` 與 Render 兩邊都要更新。
- [ ] `ADMIN_TOKEN` 有設、長度 32 字以上。沒設時管理端點一律回 403（安全的預設），但也就不能用 `/api/trending/refresh` 等管理功能。
- [ ] 雲端 `THREADS_MODE=off`。Threads 機器人目前只在本機跑；雲端和本機同時開 live 會重複回覆同一則貼文。
- [ ] 知道這些是公開的：`<RENDER_URL>` 本身（不經 Vercel 也打得到）、`/docs`、`/redoc`、`/openapi.json`（看得到 API 長相，看不到金鑰）、`/api/analyze/*`（會花 AI 額度；有每 IP 限速與每日 300 次上限保護，見 C1）。
- [ ] 改雲端設定的方法：Render 服務頁 → **Environment** → 改值 → **Save and deploy**。注意 `render.yaml` 裡有寫值的設定（非 `sync: false`）下次同步 Blueprint 時會被檔案裡的值蓋回去，這類設定要改就改 `render.yaml`。
- [ ] 分享 Render 的 **Logs** 截圖前先掃一眼有沒有敏感內容（程式設計上 log 不含 token）。

---

## Part D — 目前仍只在本機跑的東西

| 項目 | 為什麼還在本機 | 怎麼跑 |
|---|---|---|
| Threads 查核機器人（`THREADS_MODE=live`／`sim`） | 狀態檔是本機檔案（`data/threads_state.json`、`data/threads_replies.jsonl`、`data/threads_token.json`、`data/threads_sim/`）；雲端硬碟是暫時的，重啟就忘記回過誰，會重複回覆 | 本機 `.env` 設 `THREADS_MODE`，`.\start.bat` |
| 自動抓熱門新聞排程（`ENABLE_SCHEDULER`） | 雲端刻意關閉以保護 AI 額度 | 本機跑 `scripts\batch_verify_pending.py`；本機 `.env` 也設 `STORAGE_BACKEND=supabase` 時，結果會直接寫進雲端看得到的同一份資料 |
| 評測與資料腳本（`scripts/evaluate.py`、`batch_verify_pending.py`、`clean_sources_2026_09.py`、`check_db.py`、`check_supabase.py`、`test_ai_provider.py`…） | 需要 `requirements.txt` 的完整套件（scikit-learn、matplotlib、seaborn），`requirements-prod.txt` 刻意不裝；且會花額度，要有人看著 | `code\backend\venv\Scripts\python scripts\<名稱>.py` |
| 單元測試 | 跑在 GitHub Actions（`ci.yml`）與本機，不在 Render | `venv\Scripts\python -m pytest tests -q` |
| demo 影片工具（`video/`：Remotion、hyperframes、edge-tts、ffmpeg） | 只是製作素材，與線上服務無關 | 見 `video/` |
| cloudflared tunnel | 保留當退路（C2） | `runbook_tunnel.md` |
| 離線備援查核儀（`legacy/`） | 斷網 demo 用 | 雙擊 HTML |

---

## 附錄 1：Blueprint 走不通時，手動建立同一個服務

用在：A2 被要求信用卡、或 A3 第 17 步一直報錯。設定值與 `render.yaml` 完全相同。

1. Render Dashboard 按 **New** → **Web Service**，來源選 Git Provider，選這個 repo。
2. 依下表填寫（欄位名稱以畫面為準；找不到的欄位在 **Advanced** 區塊裡）：

| 欄位 | 值 |
|---|---|
| **Name** | `fakenewsverify-api` |
| **Region** | Singapore（建立後不能改） |
| **Branch** | `main` |
| **Language** | Python |
| Root Directory | `code/backend` |
| **Build Command** | `pip install -r requirements-prod.txt` |
| **Start Command** | `uvicorn app.main:app --host 0.0.0.0 --port $PORT` |
| 方案（Instance Type） | Free |
| Health Check Path（Advanced） | `/health` |
| 環境變數（Advanced） | `render.yaml` 的 `envVars` 全部 16 個：12 個有值的照抄，4 個金鑰照 A1 貼 |

3. 按 **Create Web Service**，接著回到 A4。

`PYTHON_VERSION` 一定要填完整三段 `3.12.9`；沒填的話 Render 會用它的預設版本（目前是 3.14.3），與本機和 CI（3.12）不同。

## 附錄 2：常見狀況

| 症狀 | 多半是 | 處理 |
|---|---|---|
| Build 失敗，log 有 `No matching distribution` 或編譯錯誤 | Python 版本不對 | 確認 **Environment** 裡 `PYTHON_VERSION=3.12.9` |
| Build 失敗，log 有 `Could not open requirements file` | Root Directory 不是 `code/backend` | 檢查服務 Settings 的 Root Directory |
| 一直停在部署中，最後失敗 | 程式沒有聽在 Render 指定的 port，或啟動時就崩潰 | 看 **Logs**。Start Command 必須含 `--host 0.0.0.0 --port $PORT` |
| 一切看起來正常，但查過的結果隔一陣子就 404、熱門牆資料倒退回舊的 | `SUPABASE_DB_URL` 是空的，後端默默退回暫時硬碟上的本機檔案（log 有 `SUPABASE_DB_URL is empty: using local files`） | **Environment** 補上 `SUPABASE_DB_URL` → **Save and deploy**；用 Part B 第 7 步驗證 |
| `/health` 正常，但 `/api/knowledge/stats` 回 500 | 連不上 Supabase（後端設計成資料庫連不上也照常啟動，log 有 `Supabase init failed`） | `SUPABASE_DB_URL` 貼錯或含 `[YOUR-PASSWORD]`；要用 Session pooler 的 URI（主機含 `pooler.supabase.com`、port 5432）。Direct connection 是 IPv6，雲端主機常連不到 |
| `/health` 顯示 `"ai_available":false` | `CGU_API_KEY` 沒貼到或是空的 | **Environment** 補上 → **Save and deploy** |
| 查證回「AI 分析暫時無法使用」 | 金鑰錯、CGU 額度用完，或閘道擋了 Render 的 IP | 看 **Logs** 的 `[AI] cgu HTTP <碼>`；401 = 金鑰錯 |
| push 了但 Render 沒重新部署 | 改的檔案不在 `code/backend` 底下 | 這是設計（`rootDir`）。要強制部署：**Manual Deploy** → **Deploy latest commit** |
| 改了 `render.yaml` 的金鑰項目沒反應 | `sync: false` 的項目只在第一次建立時生效 | 到 **Environment** 頁手動改 |
| 前端 `/api/...` 回 502／504 | Render 正在喚醒或部署中 | 等 1 分鐘重試；持續發生就看 Render **Logs** |

## 附錄 3：查證過的事實與來源（2026-09-19）

| 事實 | 來源 |
|---|---|
| Blueprint 欄位：`type`／`name`／`runtime` 必填；`plan: free`；`region` 允許 `oregon`（預設）、`ohio`、`virginia`、`frankfurt`、`singapore`；`rootDir`、`buildCommand`、`startCommand`、`healthCheckPath`、`branch`、`autoDeployTrigger`（`commit`／`checksPass`／`off`，取代已棄用的 `autoDeploy`） | <https://render.com/docs/blueprint-spec>、<https://render.com/schema/render.yaml.json> |
| env 的 `value` 只收字串或數字（所以 `"false"` 要加引號）；`sync: false` 只在第一次建立 Blueprint 時詢問，之後更新會被忽略 | 同上 |
| 建立流程：**New > Blueprint** → **Connect** → 名稱與分支 → **Blueprint Path**（預設根目錄 `render.yaml`）→ **Deploy Blueprint**；關閉自動同步：Blueprint Settings 的 **Auto Sync** 設 **No**，用 **Manual Sync** | <https://render.com/docs/infrastructure-as-code> |
| 在後台手動改的設定若與 `render.yaml` 衝突，下次 Blueprint 同步會被檔案蓋回去；push 有改到 Blueprint 檔才會觸發同步；從檔案移除資源不會刪掉既有服務 | 同上 |
| `rootDir` 以外的檔案在 build 與執行時都拿不到；只有 rootDir 底下的變更會觸發自動部署；指令相對 rootDir 執行 | <https://render.com/docs/monorepo-support> |
| `PYTHON_VERSION` 要完整三段版號；可指定 3.7.3 以後任何已發行版本；新服務預設 3.14.3 | <https://render.com/docs/python-version> |
| web service 必須綁 `0.0.0.0`，`PORT` 預設 10000；FastAPI 官方範例 `uvicorn main:app --host 0.0.0.0 --port $PORT` | <https://render.com/docs/web-services>、<https://render.com/docs/deploy-fastapi> |
| 免費 web service：15 分鐘無流量休眠、喚醒約 1 分鐘；每 workspace 每月 750 小時，休眠不計時，用完暫停到下月；暫時性檔案系統；可能隨時被重啟；無 shell／SSH／persistent disk；「Do not use them for production applications」 | <https://render.com/docs/free> |
| 免費方案規格 0.1 CPU／512 MB | <https://render.com/docs/compute-plans> |
| 區域建立後不能更改 | <https://render.com/docs/regions> |
| 健康檢查：2xx／3xx 且 5 秒內回應算健康；連續失敗 60 秒會重啟 | <https://render.com/docs/health-checks> |
| 部署成功狀態為 **Live**；服務頁可找到 `onrender.com` 網址；「No payment is required」 | <https://render.com/docs/your-first-deploy> |
| **Environment** 頁、**+ Add Environment Variable**、**Save, rebuild, and deploy**／**Save and deploy**／**Save only**；**Manual Deploy** 選單含 **Deploy latest commit**、**Clear build cache & deploy**、**Restart service** | <https://render.com/docs/configure-environment-variables>、<https://render.com/docs/deploys> |
| repo 沒出現在清單：到 GitHub App 設定頁的 **Repository access** 勾選 | <https://render.com/docs/github> |
| Supabase 免費專案 7 天低活動會暫停、暫停前約一週寄警告信、**Resume project** 還原、1 年內可還原；免費方案 2 個 active 專案、500 MB | <https://supabase.com/docs/guides/platform/free-project-pausing>、<https://supabase.com/pricing> |
| Supabase：**Connect** 按鈕；Session pooler（`...pooler.supabase.com:5432`）給 IPv4 網路用；Direct connection 為 IPv6 | <https://supabase.com/docs/guides/database/connecting-to-postgres> |
| GitHub 排程最短 5 分鐘、尖峰（尤其整點）會延遲甚至漏跑、公開 repo 60 天無活動自動停用排程、cron 為 UTC | <https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows> |
| repository variable：**Settings > Secrets and variables > Actions > Variables > New repository variable**；workflow 用 `${{ vars.NAME }}`，沒設時是空字串；API 需要 collaborator 權限 | <https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-variables>、<https://docs.github.com/en/rest/actions/variables> |
| 手動觸發 workflow 需要檔案在預設分支、需要 write 權限；`gh workflow run` | <https://docs.github.com/en/actions/how-tos/manage-workflow-runs/manually-run-a-workflow> |
| Vercel 外部 rewrite（代理）逾時 120 秒，逾時回 `ROUTER_EXTERNAL_TARGET_ERROR` | <https://vercel.com/docs/limits> |

查不到官方說法、文件中標「以畫面為準」的項目：Render 登入頁與授權頁的按鈕文字、Blueprint 建立畫面上四個金鑰輸入框的位置、免費方案是否會被要求信用卡、每月免費頻寬與 build 分鐘數、Supabase 重設資料庫密碼的位置、GitHub 重新啟用排程的按鈕文字。
