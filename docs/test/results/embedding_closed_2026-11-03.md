# 學校閘道關閉 embedding 的紀錄（DEF-13，2026-11-03）

測試計畫書 6.10 的證據檔。全部在負責人電腦上取得，金鑰只從本機 `.env` 讀，這裡不記金鑰。
時間標 UTC 的是系統回傳的原值；台灣時間 = UTC + 8。

## 1. 學校公告（負責人 2026-11-03 截圖）

AIR 閘道網站的「重要公告」：因資安考量，已關閉 API 服務與生圖、語音轉文字的外部模型服務；
已申請 API 金鑰的使用者仍可正常使用 Codex，本地模型也開放呼叫。公告沒有寫恢復日期。

## 2. `POST https://air.cgu.edu.tw/cgullmapi/v1/embeddings`（2026-11-03，輸入 `test`）

| 模型 | HTTP | 閘道訊息 |
|---|---|---|
| `text-embedding-3-small`（本系統使用） | 404 | 目前的上游模式（codex）不支援 /v1/embeddings |
| `text-embedding-3-large` | 404 | 同上 |
| `text-embedding-ada-002` | 404 | 同上 |
| `gpt-5.6-luna` | 404 | 同上 |
| `gemma-4-26b-a4b-it` | 404 | Not Found |
| `gpt-oss-120b` | 404 | Not Found |
| `nemotron-3-super-120b-a12b` | 404 | Not Found |

## 3. `GET /models`（2026-11-03，HTTP 200）

共 10 個，沒有 embedding 模型：`gpt-5.6-luna`、`gpt-5.6-sol`、`gpt-5.6-terra`、`gpt-6-luna`、`gpt-6-sol`、
`gpt-6.1-sol`、`gpt-6.1-terra`（以上 owned_by openai）；`gemma-4-26b-a4b-it`、`gpt-oss-120b`、
`nemotron-3-super-120b-a12b`（以上 owned_by local）。

## 4. `scripts/cgu_diagnose.py`（2026-11-03）

- 模型清單 HTTP 200；額度 `/me/usage` HTTP 200。
- embedding HTTP 404（訊息同第 2 節）。本機與正式站結果相同，所以不是 Render 的設定問題。
- 判讀（`gpt-5.6-luna`，很短的一句）HTTP 200。

## 5. 正式站 `GET /api/health` 的 embedding 欄位

| 時間（UTC） | ok | error |
|---|---|---|
| 2026-11-02 08:31:05 | false | ReadTimeout |
| 2026-11-02 14:45:46 | false | HTTP 404 |
| 2026-11-02 16:18:10 | false | HTTP 404（負責人在正式站查證的那一次） |
| 2026-11-02 16:24:17 | false | HTTP 404 |

同一段時間 `ai_available` 都是 true，所以網站看起來正常。16:07 左右負責人手動重新部署後曾短暫回 `ok: null`（重啟後還沒呼叫過）。

## 6. `factcheck-sync`（GitHub Actions，查於 2026-11-03）

- 最近 30 次：成功 25、失敗 5（83.3%）。
- 最後一次成功：2026-10-31 05:26 UTC。之後連續失敗：10-31 17:13、10-31 22:47、11-01 05:52、11-01 17:54、11-02 05:52（UTC）。
- 11-02 05:52 那次的紀錄：`embed_check` 為 HTTP 403，同步停在 `/embeddings`。

## 7. 知識庫（正式站 `GET /api/knowledge`，字面比對內容與摘要）

- `GET /api/knowledge/stats`：總數 18,806（MISINFO 18,588、SCAM 194、SAFE 24），沒有減少。
- 情境一冷水煮蛋：查核中心的報告**在**知識庫（2026-10-21 寫入，`boiling-eggs-cold-water-nutrition`）。原文和情境劇訊息不是一字不差，命中要靠語意比對。
- 情境二法國暴動豬肉：查核中心的報告 [ai-generated-image-frozen-pork-not-looted-during-france-riots](https://tfc-taiwan.org.tw/fact-check-reports/ai-generated-image-frozen-pork-not-looted-during-france-riots/) **不在**知識庫。以「豬肉」（71 筆）、「法國」（217）、「暴動」（30）、「巴黎」（88）、「超市」（125）、「洗劫」（12）、「frozen」（7）、「AI生成」（6）檢索，都沒有這篇。

## 8. 使用者看到的結果（負責人手機截圖，2026-11-03 00:18 台灣時間）

輸入「巴黎超市被搶，只剩下豬肉沒人搶」（改寫過的短句，不是情境劇原文），結果：假訊息、信心低、AI 即時判定、
分類「內容農場」；頁面顯示「尚無查核機構證實」，查核來源是空的。查核中心其實查過這則，系統找不到。
