# Runbook：cloudflared quick tunnel 與 vercel.json 換主機

> **2026-09-19 起已改為退路**：正式環境的後端在 Render（`runbook_cloud_deploy.md`）。只有 Render 出問題、要退回負責人電腦時才用這份（做法見該文件 C2）。

> 本檔由 P-04 先建立「約定與換主機步驟」段落；O-08 完成時補齊 tunnel 啟動、demo 期間守則與斷線退路（見 03_tickets.md O-08 做什麼 4）。

## 1. vercel.json 約定（P-04）

檔案：`code/frontend/vercel.json`（全專案唯一一份）。

- `rewrites[0]`：`/api/(.*)` → `https://<TUNNEL_HOST>/api/$1`，同源代理到本機後端（spec §8.2）。初始主機為 `REPLACE-ME.trycloudflare.com`。
- `rewrites[1]`：`/((?!.*\.html$).*)` → `/index.html`，SPA fallback；排除 `*.html`，讓 `privacy.html`、`data-deletion.html`、`deauthorize.html` 靜態頁不被蓋掉。
- **健康檢查只走 `/api/health`**（B-22 在後端註冊別名），**不另寫 `/health` rewrite**。OP-8 驗收一律打 `{PUBLIC_BASE_URL}/api/health`。
- 除 `$schema` 外不加其他頂層鍵（見第 3 節偏離說明）。

## 2. tunnel 重啟後換主機（O-08 與之後每次重啟）

1. 另開視窗執行 `cloudflared tunnel --url http://localhost:8000`，複製輸出中的 `https://xxxx.trycloudflare.com`。
2. **只改 `vercel.json` 的 `rewrites[0].destination` 主機名這一處**（`https://xxxx.trycloudflare.com/api/$1`）；SPA fallback 那條不動。
3. 本機確認 JSON 合法：在 `code/frontend` 執行 `node -e "JSON.parse(require('fs').readFileSync('vercel.json','utf8'))"`，退出碼 0。
4. 依 O-26 流程 commit＋push（或 `npx vercel deploy --prod` 備案）→ 等 Vercel Ready。
5. 驗證：
   - `curl -s -o NUL -w "%{http_code}" {PUBLIC_BASE_URL}/api/health` 印 `200`（B-22 完成前可改打 `/api/trending`）。
   - `curl -s -o NUL -w "%{http_code}" {PUBLIC_BASE_URL}/privacy.html` 印 `200`。

## 3. 與 P-04 票面的偏離（O-26 需確認）

- P-04 做什麼 2 原寫「檔內以 `_comment` 欄位註明此約定與 O-08 換主機步驟」。實作**未放 `_comment`**：Vercel 的 `vercel.json` schema 對未知頂層鍵可能驗證失敗導致部署失敗（未經實際部署驗證），因此約定改記錄在本檔第 1、2 節。
- 檔內另加了 `$schema`（`https://openapi.vercel.sh/vercel.json`），Vercel 接受此鍵。
- **O-26 待辦**：push 後確認 Vercel 部署為 Ready（未因 `vercel.json` 格式被拒）；若被拒，先移除 `$schema` 再試。

## 4. O-08 待補

- cloudflared 安裝與啟動細節、demo 期間不重啟 tunnel、斷線時退回本機 `localhost:5173`。
