# 01 · 重做規格書（功能 + UX）

## 0. 文件資訊

| 項目 | 內容 |
|------|------|
| 文件版本 | v1.4（2026-09-22 增補 FR-20 查核結果回補、FR-21 本站熱門查證；v1.3 為 v1.2 審查修訂第二輪：21 條一致性／可行性意見全部採納，主要為 FR-16～19 內部一致性、Day 2.5 工時重排、`verified` 計算位置；變更紀錄見文末） |
| 日期 | 2026-09-22（v1.0：2026-09-14；v1.1：2026-09-15 上午；v1.2：2026-09-15 下午；v1.3：2026-09-15） |
| 上游依據 | `docs/rebuild/00_consensus.md`（2026-09-14 grill 結論 + 2026-09-15 §4「AI 額度已解決」、§9「來源品質與資料清潔」補充；§9 插入後原「掃描發現的既有事實」為 **§10**）。本文件每條決策皆可回溯至該檔章節，標示為「共識 §n」；本文件與共識衝突時以共識為準。**已知共識內部矛盾**：共識 §6「要買：OpenAI API 額度 USD 5–10」已被 §4（2026-09-15「不買 OpenAI 直連額度」）取代，本文件不採 §6 該行；建議下次更新共識時刪除（本次修訂不改共識檔） |
| 事實來源 | 掃描結果 `ai_engine / backend_api / pipeline_store / crawler_news / frontend_react / offline_ops / tests_eval / docs_usecases / threads_code / threads_gap_analysis / threads_verify_10`（後者的 `refuted` 條目視為對前者的修正）；程式碼行號以掃描時 Read 輸出為準 |
| 狀態 | 待負責人審閱（Day 0 必答 D-1／D-3（僅品牌名與顯示名稱，handle 已定 `@factcheck_tw_bot`）／D-5／D-9；Day 1 答 D-13／D-16／D-18；Day 2.5 前答 D-15／D-17）→ Day 1 上午 S1／S2 mockup + grill with mockup → Day 1 下午 ticket（primitives → screens）→ implement → visual review。S3–S6 不另做 mockup，以 8.3 元件清單 + 8.7 文案表為驗收基準（第 11 節） |
| 下游文件 | 測試計畫書 `TP-FNV-2026-01`（共識 §7）：本文件第 10 節 = 計畫書 §4.2 通過準則（含 4.3 中止／再繼續）；10.6 = 計畫書 §2.3 參考文件、§4.1 測試環境、§4.4 交付項目；第 4 節 FR 編號供 §3.2 引用；3.2 = `tests/`、3.3 = visual review、3.4／3.5 = `evaluate.py`（依共識 §7，不新增 `bench.py`） |
| 讀者 | 專案負責人（唯一實作者，AI 輔助）、4 位組員（申請／文件／測試／影片）、指導教授 |
| 適用範圍 | 本次重做（一週）：共識 §2「做」的全部項目；「不做」項目不再以需求出現 |

寫作慣例：識別字、路徑、API、設定鍵一律保留原文；文案以「」或表格標示為**逐字**文案；FR 編號固定，ticket 需引用；`{BRAND}`／`{PUBLIC_BASE_URL}`／`{CONTACT_EMAIL}` 為佔位，第 13 節定案後全文取代；`{BOT_HANDLE}` 自 v1.2 起**已定案為 `factcheck_tw_bot`**（帳號已建立，第 2 節），全文出現的 `@{BOT_HANDLE}` 即 `@factcheck_tw_bot`，實作時 `BOT_HANDLE` 設定鍵預設值改為此值。

---

## 1. 產品概述與目標

**一句話定位**（共識 §1）：台灣繁中的假訊息／詐騙查證平台——貼上文字或網址（圖片 P1），AI 判定 SCAM／MISINFO／SAFE 並附查核來源；同一套判定在 Threads 上 @機器人 即可取得，網站結果可一鍵分享回 Threads。

**下週 demo 的成功定義**（課程優先，共識 §1、§7）：

1. 進度報告 + 3 分鐘 demo 影片如期交出。
2. 影片完整走一遍閉環：Threads 可疑貼文 → Tester 回覆並 @機器人 → 機器人回覆 🔴／🟡／🟢 + 來源 + `/r/{id}` 連結 → 點開手機版結果頁 → 「分享到 Threads」回到 Threads。若 Meta 憑證未到，模擬 Threads 模式（FR-10）在畫面上呈現同一閉環而不穿幫（畫面主體為終端機 log + `replies.jsonl` + 最小 `/bot` 只讀狀態卡，見第 11 節分鏡）。
3. 網站四個主畫面（首頁／結果頁／熱門牆／知識庫）在手機寬度可用；淺色預設；紅黃綠只出現在判定。
4. AI 真的能跑（共識 §4：新學期 CGU AIR 金鑰已於 2026-09-15 02:00 填入並實測，`gpt-5.4-mini` 判定正常、embedding 1536 維正常，provider 鏈 `['cgu']`；**不買 OpenAI 直連額度**）：影片至少展示一次「未命中快取 → AI 判定」與一次「改寫版命中向量快取（`cache_layer="vector"`）」；全程零「AI 分析暫時無法使用」畫面。
5. `pytest tests` 全綠、CI 通過；評測數字（舊 accuracy 96%／FN=0 與 CGU `gpt-5.4-mini` 新跑值並列）與三層快取證據可在報告引用。
6. **demo 資料乾淨**（共識 §9，負責人明確要求）：影片與網站出現的每一個「查核來源」都是 Tier 1／2（已做出判定的查核機構或媒體查核報導）；熱門牆無 Google News 轉址項目；知識庫頁不出現 `verified=false` 的記錄；找不到查核來源時畫面明示「尚無查核機構證實」且不出現綠燈。

**非目標**（共識 §2「不做」；本文件不再討論）：影片查證（yt-dlp + Whisper）、FB/IG 封閉平台（Playwright）、文字輸入的 Google 搜尋抓取、熱門牆的 Google News 來源、管理者覆寫 UI（`/api/admin` API 保留）、使用者帳號／登入、英文介面、Threads Webhook、Threads 私訊（API 不存在）、公開讓陌生人 @機器人（需 App Review + 企業驗證，論文寫明為上線條件）。

---

## 2. 品牌名稱 3 個候選（handle 已定案）

**機器人 handle 已由負責人建立為 `@factcheck_tw_bot`**（v1.2；公開 Threads 帳號，C7 完成一半），Threads 顯示名稱待定（例：「查核小幫手」），可與品牌名不同。Threads handle 一旦建立即綁死（改名 = 重做帳號與 Tester 邀請），因此 v1.1 表中的主／備 handle 候選**全部作廢**，僅保留品牌名 3 個候選供 D-3 選擇；機器人帳號必須是**公開帳號**（threads_gap_analysis `must_obtain`：私人帳號授權 90 天不可續期，且私人帳號貼文不會出現在 mentions）——C9 驗收時再確認一次 `@factcheck_tw_bot` 為公開。

| # | 品牌名稱（網站 `{BRAND}`） | 機器人顯示名稱建議 | 一句理由 |
|---|---------|------------------------|---------|
| A | **全民查證公社**（保留，共識 §8） | 「全民查證公社 查核小幫手」 | 既有 OOSE 文件、評測報告、程式碼與回覆模板都已用此名，零改名成本；「公社」點出開放共享的知識庫與社群共查定位，與「熱門牆＋知識庫」一致。 |
| B | **查一下** | 「查一下」 | 名字就是使用者在 Threads 回覆時會打的動詞——「@factcheck_tw_bot 這是真的嗎？」下方出現「查一下」的回覆，讀起來像自然對話，最貼合 @機器人 的互動模式。 |
| C | **真假燈** | 「真假燈」 | 把產品最醒目的視覺（🔴🟡🟢 判定燈）變成名字，在 Threads 動態牆一眼看出是查核燈號；適合影片與簡報的記憶點。 |

決策方式：負責人挑一個品牌名 + 一個顯示名稱（第 13 節 D-3）；定案後同步改 `threads_service.py` 署名、React `<title>`／頂欄、隱私政策頁、`CLAUDE.md`，並在 Threads App 設定機器人顯示名稱。程式碼用設定鍵 `BRAND_NAME`（預設「全民查證公社」）、`BOT_HANDLE`（預設 **`factcheck_tw_bot`**，不再是佔位）。

---

## 3. 使用者與情境

| 代號 | 使用者 | 情境 | 裝置／入口 | 成功條件 | 對應 FR |
|------|--------|------|-----------|---------|---------|
| U1 | **從 Threads 被 @回覆點進來的訪客** | 在 Threads 看到機器人對某貼文的紅燈回覆，點「完整判讀」連結 | 手機、Threads 內建瀏覽器（375–430 px 寬、無外掛、不習慣輸入網址） | 3 秒內看懂燈號與一句摘要；不需登入；能一鍵分享回 Threads；能再貼一則自己想查的內容 | FR-04、FR-05、FR-01 |
| U2 | **直接來網站查證的人** | 家人 LINE 傳來「普發現金登記」，想確認真假 | 手機為主、桌機次之 | 貼上即查、進度可見、失敗有交代；看得懂「快取命中」；查過的紀錄還在（不登入） | FR-01～03、FR-08 |
| U3 | **進度報告評審／demo 影片觀眾** | 3 分鐘內判斷「這組做了什麼、能不能動、有沒有 Threads、有沒有測」 | 投影／影片 | 閉環清楚、狀態文字大而明確、快取命中與 AI 判定可區分、數據可信（評測、成本、測試） | FR-04、FR-09、FR-10、第 11 節分鏡 |
| U4 | **Threads 上 @機器人 的 Tester**（負責人、示範組員、被加為 Threads Tester 的評審） | 回覆一則可疑貼文並 @機器人 | Threads App（手機） | ≤ 輪詢間隔 + 60 秒內收到 ≤500 字回覆；回覆讀得懂、有來源、兩個連結皆可點；無法查核時也有回應 | FR-09、7.7 |
| U5 | **操作者（負責人）** | demo 前確認 AI 可用與 CGU 額度（`/v1/me/usage`）、token 有效、機器人狀態；必要時切模擬模式 | 桌機、終端機、`/bot` 只讀狀態頁 | 一眼看到 `mode`／`last_error`／最近回覆；能以 `scripts/test_threads_bot.py --poll` 或 `curl -H X-Admin-Token … /api/threads/poll` 手動觸發一輪；30 秒內可切模擬模式 | FR-10、FR-11、FR-14、第 7 節 |

**開發模式的硬事實**（共識 §3；threads_verify_10 confirmed Claim 8／9）：未通過 App Review 前，`GET /{user_id}/mentions` 只回傳 **Threads Tester** 的提及，`GET /{media-id}` 只能讀 Tester 的貼文，私人帳號貼文不會出現。因此 U4 一律是 Tester，且被查核的「原貼文」也必須是 Tester 發的——demo 由組員 A 發可疑貼文、組員 B 回覆並 @機器人，兩人都加為 Threads Tester **且兩個帳號都必須設為公開**（私人帳號的貼文不會出現在 mentions，機器人也讀不到；threads_verify_10 confirmed Claim 8）。

**端到端主迴圈**（所有畫面設計的骨幹）：
`Threads 貼文 → Tester 回覆並 @機器人 → 後端輪詢 mentions → 讀原貼文 → 三層快取／AI → 寫入 tasks.parquet（id）→ 回覆 🔴🟡🟢 + 來源 + /r/{id} → 訪客點進結果頁 → 「分享到 Threads」Web Intent → 新貼文帶判定與連結回到 Threads`。

---

## 4. 功能規格 FR-xx

優先級：P0 = 沒有就無法 demo；P1 = 報告後補做才算完整（**不排進 Day 1–6**）；P2 = spec 寫、可不實作（共識 §2）。v1.1 依審查把 P1／P2 全部移出一週時程，P0 只留共識 §2「做」清單 + 支撐它們的最小工程項（第 11 節）。v1.2 依共識 §9 新增 FR-16～FR-19（來源分級／知識庫寫入門檻／既有資料清洗／web_search 網域限制）：前三者為 **P0**（demo 資料必須乾淨，負責人明確要求），為了不撐爆時程，`similar_news` 向量近鄰（FR-02 第二段、S2 元件 5）降為 **P1**（第 11 節「v1.2 範圍調整」）。

### FR-01 文字查證（P0）
- **描述**：使用者貼上 1–20,000 字文字（`AnalyzeTextRequest` analyze.py:85-87），走「L1 hash → L2 向量（門檻 0.75，以使用者原文比對，**只比對 `verified=true` 列**，FR-17）→ L3 AI（provider `cgu`／`gpt-5.4-mini`；web_search 依 FR-19 限 Tier 1／2 網域）」。共識 §4：文字輸入**不再送 Google**——`pandas_task_processor.py` 的 `crawler.process_input(原文, "keyword")` 分支移除，`googlesearch-python` 自 `requirements.txt` 移除。
- **輸入**：`POST /api/analyze/text` `{content}`。
- **輸出**：`{task_id, result_id, status:"pending", message}`（`result_id` = `task_id`）；最終結果由 `GET /api/result/{id}` 取得（第 5 節）。
- **驗收**：
  1. 同一段文字第二次送出 → `cached=true, cache_layer="hash"`，回應 ≤3 秒，AI 呼叫 0（以後端 log `[AI]` 行數為證）。
  2. 改寫版同一謠言（實測相似度 0.79–0.82，config.py:57-61 校準註解不動）→ `cache_layer="vector"`，AI 呼叫 0。
  3. 全新內容 → `cached=false, cache_layer=null`，`knowledge_base.parquet` 新增 1 列且 `raw_content` = 使用者原文（`tests/test_processor_flow.py` 既有守門）；新增 mock 斷言 `crawler.process_input` 未被呼叫。該列 `verified` 依 FR-17 門檻決定：有 Tier 1／2 來源 → `true`，否則 `false`（仍保存，但不參與向量命中）。
  4. 空字串／>20,000 字 → HTTP 422；前端在送出前 inline 擋（不用 `alert()`）。
  5. provider 鏈（現為 `['cgu']`；`_run_analysis` 只加入有設定 key 的 provider，ai_service.py:118-122）全失敗 → HTTP 200、`ai_unavailable=true`、`summary` 仍以「AI 分析暫時無法使用」開頭（共識 §10 契約不變）、不寫知識庫；前端顯示 8.3 「AI 不可用」狀態。
  6. AI 回傳的 `sources` 經 FR-16 分級後只留 Tier 1／2；結果無任何 Tier 1／2 來源且非規則命中 → `verified=false`、結果頁顯示「尚無查核機構證實」、不得綠燈（7.8 新列）。

### FR-02 網址查證（P0）
- **描述**：`http(s)://` 網址走「L0 URL → L1 hash(網址) → trafilatura 爬取（共識 §4 保留）→ L2 向量（以爬到內文）→ L3 AI（帶 `url`）」。
- **`similar_news` 的來源（FR-15 移除 `googlesearch` 後；v1.2 降 P1）**：現況網址輸入的 `similar_news` 來自 `crawler.py:516-533` 以標題再搜一次 googlesearch，隨套件移除而消失；文字輸入本就不爬。重做後 `similar_news` **只**來自知識庫向量近鄰 top-3（`find_similar_by_vector` 改可回多筆，零 AI 成本；相似度 ≥0.6、排除自己、**只取 `verified=true` 列**），文字／網址／Threads 三種來源一致；S2 元件 5 改名「知識庫中的相似查證」。**v1.2：此近鄰功能降為 P1、不排進一週時程**（時程空間讓給 FR-16～18）；本次 `similar_news` 固定回 `[]`、S2 元件 5 空時隱藏。provider web_search 的 `url_citation` 仍只進 `sources`（既有），再經 FR-16 分級。
- **輸入**：`POST /api/analyze/url` `{content}`。後端**必須驗證** `content.strip()` 以 `http://`／`https://` 開頭且 `urlparse` 有 host，否則 422 `code:"invalid_url"`（修正 analyze.py:165 直接委派 `/text`、`task_type` 誤記 `analyze_text`、`data_type` 存成 `TEXT` 的問題）。
- **輸出**：同 FR-01；`task_type="analyze_url"`、`input_type="url"`，知識庫 `data_type="URL"`。
- **驗收**：
  1. 同網址二次 → `cache_layer="url"`。
  2. 私網／保留位址（`127.0.0.0/8`、`10/8`、`172.16/12`、`192.168/16`、`169.254/16`（含 `169.254.169.254`）、`::1`、`fc00::/7`、`localhost`、`*.local`、非 http/https 協定、轉址到私網）→ 422 `code:"blocked_url"`，且**不發出任何 HTTP 請求**（第 9 節 SSRF）。
  3. 爬取失敗（非 2xx、連線逾時 10 s 或總逾時 `CRAWLER_TIMEOUT`（config.py:64，預設 30 s）、回應 >2 MB、內文 <50 字；與第 9 節 SSRF 列同一組數字，FN-2a 以 mock 驗證兩個逾時各自生效）→ 任務 `completed`、`risk_type="UNVERIFIABLE"`、`frame_type="yellow"`、`explanation`=「無法讀取此網頁內容（{原因}），請改貼文字內容再試」；不呼叫 AI、不寫知識庫（取代現行 raise「爬取失敗」→ 500）。
  4. 影音／FB／IG 網址（`crawler.detect_platform` 舊分支）→ 同 3 的 UNVERIFIABLE 路徑，`explanation`=「目前不支援影片與 Facebook／Instagram 連結，請貼上文字內容」；Playwright、yt-dlp 依賴移除（共識 §2、§4）。
  5. `threads.net`／`threads.com` 貼文網址不特別處理，走一般爬取（多半 UNVERIFIABLE）；結果頁加提示文案 `unverifiable_threads_hint`。
  6. 爬取成功者 `sources` 經 `url_validator.filter_valid_sources` 過濾（既有），再經 FR-16 `tier_of()` 分級，只留 Tier 1／2；被查的網址本身不得被當成自己的查核來源（`sources[].url` 與輸入網址同網域時剔除）。

### FR-03 圖片查證（P1）
- **描述**：上傳 PNG/JPG/WEBP（≤10 MB），後端存 `data/uploads/{task_id}.{ext}`，視覺模型先 OCR 再判定（ai_service.py:369-394）。
- **輸入**：`POST /api/analyze/image` multipart `file`。
- **輸出**：同 FR-01；`input_type="image"`。
- **驗收**：
  1. 伺服器端檢查 magic bytes（PNG `89 50 4E 47`、JPEG `FF D8`、WEBP `RIFF....WEBP`），不符 → 415 `code:"unsupported_media"`；>10 MB → 413 `code:"payload_too_large"`（修正 analyze.py:209-225 只看副檔名、無大小上限）。
  2. L1 hash 改為對**檔案位元組** SHA-256（修正 pandas_task_processor.py:147 對暫存路徑 hash 永不命中）；同一張圖二次上傳 → `cache_layer="hash"`。
  3. 圖片結果回寫知識庫 `data_type="IMAGE"`、`raw_content`=AI 回傳 `summary`、`content_vector=None`（不做向量層）。
  4. 分析後刪除暫存檔（既有 pandas_task_processor.py:164-167）。

### FR-04 結果頁 `/r/{id}`（P0）
- **描述**：每次查證（web／Threads／模擬）有獨立網址（共識 §2）。`{id}` = `task_id`（uuid4），資料來源 `tasks.parquet`。頁面自己輪詢 `GET /api/result/{id}` 直到 `completed`／`failed`，因此送出後**立刻**導向 `/r/{id}`，URL 從第一秒起就可分享。
- **輸入**：路由參數 `id`。
- **輸出**：第 8 節 S2 全部狀態。
- **驗收**：
  1. 送出後 ≤500 ms 進入 `/r/{id}` 並顯示載入態。
  2. 直接在新分頁開啟 `/r/{id}` 可完整渲染（Vercel `vercel.json` rewrite 全部路徑到 `index.html`）；重新整理仍顯示同一結果（`tasks.parquet` 上限提高到 5,000，第 6 節）。
  3. 不存在或已修剪的 id → 404，畫面「找不到這筆查證」+ 回首頁。
  4. `<html lang="zh-Hant">`；`<title>` =「{frame_label}｜{BRAND}」由 SPA 動態設定（瀏覽器分頁用）。OG 標籤：`index.html` 提供**一組通用**靜態 OG（`og:title`=品牌名、`og:description`=`home_tagline`、固定 `og:image`）；Threads／Meta 連結預覽爬蟲不執行 JS，每筆結果的動態 OG 列為**上線後工作**（需 Vercel Edge Function 或後端 SSR），本次不做。
  5. 結果頁 API：對同一 id 以 `curl` 迴圈連打 50 次 `GET /api/result/{id}`（本機），p50 <300 ms；手機寬 360 px 無橫向捲動。

### FR-05 分享到 Threads（P0）
- **描述**：結果頁「分享到 Threads」以 Web Intent 開新視窗 `https://www.threads.com/intent/post?text={text}&url={url}`（共識 §3 模式 c；threads_verify_10 confirmed Claim 17：純前端、零 token、零審核、零配額）。
- **輸入**：目前結果（後端 `share` 欄位已組好，5.3）。
- **輸出**：`text` = 7.7 分享文案（≤200 字，percent-encoding）；`url` = `{PUBLIC_BASE_URL}/r/{id}`。
- **驗收**：
  1. 本專案可控部分：點擊後開啟的 URL 為 `https://www.threads.com/intent/post?text=<percent-encoded>&url=<percent-encoded>`，解碼後 `text`／`url` 與 `share` 欄位逐字相同（含 `&`、`#` 不截斷）；iOS Safari 與 Android Chrome 各一台實測可開到 threads.com 預填頁。Threads App 內是否深連結到 composer 屬 Meta 端行為，官方只保證「開新視窗到 threads.com」（threads_verify_10 Claim 17），列為**觀察紀錄**不作通過條件。
  2. 不帶 `tag`／`reply_control`（Web Intent 的 `reply_control` 枚舉與 API 不同——threads_verify_10 additional_findings 第 3 條——本次不用）。
  3. 用 `<a target="_blank" rel="noopener">` 而非 `window.open`（Threads 內建瀏覽器相容）；點擊後按鈕文字 3 秒內顯示「已開啟 Threads」，並 toast「發佈前可自行修改文字」。
  4. 另有「複製連結」（`navigator.clipboard.writeText`），失敗時退回顯示可選取的 URL 文字。
  5. 不需 access token；離線亦可組出網址。

### FR-06 熱門牆（P0）
- **描述**：`/trending` 顯示 `fact_check_records` 中 `is_trending=True` 的查核新聞（trending.py:23-51 既有排序：已查證優先、Cofacts ≤3 筆排尾）。來源只剩 MyGoPen／TFC／Cofacts（共識 §2 移除 Google News；`search_service.py:152-173` 四組查詢刪除）；既有 31 筆 `news.google.com` 轉址記錄由 FR-18 清洗腳本移除或解析真實網址後去重；Cofacts 只收「有 RUMOR／NOT_RUMOR 回覆」的文章（共識 §9 Tier 1 定義；`search_service` 現已只抓 RUMOR-verified，補 NOT_RUMOR 不在本次範圍）。
- **輸入**：`GET /api/trending?limit=20&risk_type=`。
- **輸出**：卡片列表（S3）。
- **驗收**：
  1. 首屏 20 筆；篩選 chip（全部／詐騙／假訊息／安全／未查證）。
  2. 每張卡顯示燈號點、標題、來源機構、日期、`label_source` 小字（「查核機構標記」／「AI 判定」）；PENDING／UNVERIFIABLE 顯示灰色「未查證」chip，不用紅黃綠。
  3. 「立即更新」按鈕對一般訪客**移除**（`POST /api/trending/refresh` 改需管理 token）；改顯示「資料更新時間：{max(created_at)}」與排程狀態文案（不再硬編「每 6 小時」）。
  4. 後端不可用 → 顯示錯誤態「暫時連不上伺服器」而非空狀態（修正 App.jsx:159 靜默 return）。
  5. 卡片點擊：有 `result_id` → `/r/{id}`，否則外連 `source_url`（`rel="noopener"`）。**D-01 註記：`result_id` 本次不回填**（新聞分析不建任務），熱門卡一律外連 `source_url`。**D-01 決策（`verified` 單一定義）**：熱門列 `verified` 只依 6.3 由 `label_source` 與 `source_url` 的分級決定，AI 回傳的 `sources` 只影響知識庫列的 `verified`（FR-17 (a)，經 url_validator）；`_save_rss_record`／`_analyze_record` 與 FR-18 規則 4 用同一公式，規則 4 重跑結果收斂。
  6. `source_url` 不得為 `news.google.com` 轉址（FR-18 清洗後 + `_save_rss_record` 不再寫入 Google News 來源）；`label_source="ai"` 且 `verified=false` 的記錄一律顯示灰色 `chip_pending`、不顯示紅黃綠。

### FR-07 知識庫搜尋（P0）
- **描述**：`/knowledge` 伺服器端瀏覽／關鍵字搜尋已快取判定（knowledge.py:45-86）。**只回 `verified=true` 列**（FR-17；`verified=false` 列仍在 Parquet 內供稽核與重新驗證，但不出現在知識庫頁、不計入 `stats`）。
- **輸入**：`GET /api/knowledge?q=&risk_type=&limit=30&offset=0`。
- **輸出**：列表 + `GET /api/knowledge/stats`。
- **驗收**：
  1. `q` 含 `(`、`[`、`*` 不得 500（knowledge.py:59-60 改 `regex=False`）。
  2. 新增 `offset` 分頁；前端「載入更多」每次 30 筆；`total` 為篩選後總數；分頁不重複不遺漏。
  3. 統計列顯示 `total` 與詐騙／假訊息／安全／無法查證（含 UNKNOWN/UNVERIFIABLE）四格，加總 = `total`（修正 App.jsx:282-290 對不上）。
  4. 每筆顯示 `label_source` chip（第 6 節新欄位）；有 `last_result_id` 者可點到 `/r/{id}`，否則展開摘要。
  5. 回應中每筆 `sources` 只含 Tier 1／2（FR-16）；`GET /api/knowledge?q=` 對 `verified=false` 列不命中（FN-13）；`stats.total` = `verified=true` 列數。

### FR-08 localStorage 查證歷史（首頁「最近查證 5 筆」P0；`/history` 全頁 P2）
- **描述**：個人歷史存瀏覽器（共識 §5；CLAUDE.md §10 方案 A）。首頁「最近查證」顯示最近 5 筆即滿足共識 §5；`/history` 獨立頁（顯示全部 + 清除）降為 P2，不排進一週時程（審查：範圍擴充）。
- **格式**：key `fcc_history_v1`，值 `[{id, input_type, preview(≤80 字), risk_type|null, frame_type|null, created_at}]`，最多 50 筆、最新在前；送出時寫入，結果頁完成後回寫 `risk_type/frame_type`。
- **驗收**：
  1. 重新整理後仍在；清除瀏覽器資料後消失（無伺服器副本）。
  2. 每筆可點回 `/r/{id}`；「清除全部」需二次確認。
  3. 所有讀寫包 try/catch；localStorage 不可用（無痕／拋錯）時頁面照常運作並顯示 `history_unavailable`。

### FR-09 Threads @機器人回覆（P0，開發模式 + Tester）
- **描述**：Tester 在 Threads 回覆一則可疑貼文並 @機器人（或直接 @機器人貼可疑文字）→ 後端輪詢 `GET /{user_id}/mentions` → 讀 `replied_to` 原貼文 → 走與 FR-01 **完全相同**的管線（threads_bot.py:116-117 既有設計）→ 依 7.7 模板回覆紅黃綠 + 來源 + `/r/{id}`（≤500 字、≤5 連結）。細節在第 7 節。
- **輸入**：Threads mention 物件。
- **輸出**：一則回覆；`tasks.parquet` 一列 `origin="threads"`、`threads_mention_id`、`threads_reply_id`；`data/threads_replies.jsonl` 一行。
- **驗收**：
  1. `scripts/test_threads_bot.py --live` 回 profile 與 mentions 皆 200。
  2. Tester 發文 → @機器人 → 手動 `POST /api/threads/poll`（帶管理 token）或等一個輪詢週期 → Threads 上出現回覆；回覆第一行為 🔴／🟡／🟢 + 判定；含 `/r/{id}` 連結且可開，燈號與網頁一致；`threads_len ≤ 500`。
  3. 再 poll 一次 → 不重複回覆（`replied_ids` + 每則後原子寫檔 + 輪詢互斥）。
  4. AI fallback（`ai_unavailable=true`）或每日 AI 額度用盡 → 不回覆、不標記，下輪補回（既有 threads_bot.py:123-127）。
  5. 原貼文為圖片／影片且無可用文字（**正向清單** `media_type in ("IMAGE","VIDEO","CAROUSEL_ALBUM")` 且 `strip_mentions(text)` <8 字）→ 回覆固定文案 `reply_media_only` 並標記（取代現況靜默跳過 threads_bot.py:110-113）。**永不**以 `media_type == "TEXT"` 判斷文字貼文——`TEXT` 只是發佈時的參數值，Media 物件回傳的枚舉推測為 `TEXT_POST`／`IMAGE`／`VIDEO`／`CAROUSEL_ALBUM`／`AUDIO`／`REPOST_FACADE`，未經官方文件核對；Day 2.5 `--live` 必須 log 一則真實 mention 的原始 JSON，把實際值寫回本條、7.5 與 7.9 fixture。
  6. 抓不到原貼文（非 Tester／私人帳號／HTTP 4xx）→ 回覆 `reply_cannot_read` 並標記；**不得**把「@bot 幫我查」這種請求句送去 AI（修正 threads_bot.py:70-71）。
  7. 不回覆機器人自己的貼文；原貼文作者為機器人時（有人回覆機器人的判定貼文再 @它）跳過並標記，不把自己的判定文當謠言分析。判斷方式見 7.5（`replied_to` 只有 `{id}`，沒有 owner 欄位——threads_verify_10 Claim 15）。

### FR-10 模擬 Threads 模式（P0）
- **描述**：`THREADS_MODE=sim` 時以 `FakeThreadsService` 取代真 API：mentions 讀 `data/threads_sim/mentions.json`，回覆寫 `data/threads_sim/replies.jsonl`（共識 §2「demo 保險兼離線測試」）。其餘流程（管線、模板、去重、狀態、`/bot` 頁）與 live 完全相同。
- **輸入**：本機 JSON（格式見 7.9）。
- **輸出**：`replies.jsonl` 每行一則；`/bot` 頁與 `GET /api/threads/replies` 可看。
- **驗收**：
  1. 無網路、**無 Threads token（但 `.env` 已設 `ADMIN_TOKEN`）**下 `scripts/test_threads_bot.py --poll` 或 `curl -X POST -H "X-Admin-Token: …" /api/threads/poll` 跑完一輪，`replies.jsonl` 新增 ≥1 行，內容符合 7.7 模板且 `threads_len ≤ 500`。
  2. `tests/test_threads_bot_sim.py`（新增）在 CI 離線跑通：固定 fixture + 假 AI → 斷言回覆文字、去重、圖片貼文文案、錯誤注入分流。
  3. `GET /api/threads/status.mode == "sim"`（機器可驗）；最小 `/bot` 頁（FR-11 P0 部分）醒目顯示「模擬模式」徽章，live 模式顯示「開發模式（僅 Threads 測試者）」。
  4. `scripts/test_threads_bot.py --reset-sim` 清 `replies.jsonl` 與 `replied_ids`，demo 前可重播。

### FR-11 機器人狀態頁 `/bot`（最小只讀版 P0；進階 P1）
- **P0 最小版（只讀、無輸入）**：讀 `GET /api/threads/status` 與 `GET /api/threads/replies?limit=10`，顯示：模式徽章（live「開發模式（僅 Threads 測試者）」／sim「模擬模式」／off「已停用」）、`threads_last_poll`（時間 + `checked/replied/skipped/errors`）、`last_error`（紅色）、`dev_mode_notice`、最近 10 則回覆（燈號點 + 原貼文摘要 + 回覆全文可展開 + 「原貼文」外連 + 「結果頁」內連）。頁面每 2 秒重讀 `status`，`last_poll_at` 變動時重讀 `replies`（供 demo：終端機觸發一輪後畫面自動出現新回覆）。**沒有「執行一輪」按鈕、不輸入管理 token**——觸發一律走 `scripts/test_threads_bot.py --poll` 或 `curl`。
- **P1 進階（報告後）**：token 到期日與 <7 天黃色警示、今日回覆數／Threads 配額、「執行一輪」按鈕（管理 token 存 sessionStorage）。
- **驗收（P0）**：`THREADS_MODE=off` 顯示 `threads_off` 而非錯誤；sim／live 徽章正確；終端機跑一輪後 ≤4 秒內列表出現新回覆；demo 影片可用此頁作為「機器人真的動了」的證據。

### FR-12 每日查核貼文（P2，spec 寫、可不實作）
- **描述**：每天 09:00（Asia/Taipei）從 `fact_check_records` 挑過去 24h 內 `risk_type in (MISINFO, SCAM)`、`platform IS NULL`、`ai_score ≥ 0.8`、**`verified=true`**（FR-16：只有 Tier 1／2 來源證實的項目才可對外貼文，共識 §9 第 2 點）的最多 3 筆，組成 ≤500 字貼文，用機器人帳號 `publish_text()`（threads_service.py:126-137 現為死碼；共識 §3 模式 b：有 App 角色的帳號發文不需送審，250 則/24h）。發文前查 `threads_publishing_limit`（`quota_usage/config`）。
- **輸入**：排程觸發或 `POST /api/threads/daily-post`（管理 token）；`scripts/daily_post.py --dry-run` 只印不發。
- **輸出**：貼文；被選中的記錄寫回 `platform="threads"`、`post_id=<media id>`（第 6 節，防重發）；紀錄寫 `data/threads_posts.jsonl`。
- **模板**：
  ```
  📌 今日查核（{YYYY/MM/DD}）
  🔴 {title1 ≤40 字}
  🔴 {title2}
  🔴 {title3}
  詳情與來源：{PUBLIC_BASE_URL}/trending
  AI 自動整理，請自行查證。
  ```
- **驗收**：同日重跑不重發；無合格記錄則不發；`ENABLE_DAILY_POST=false` 預設關。

### FR-13 隱私政策／資料刪除靜態頁（P0）
- **描述**：Meta Threads use case 設定必填 Privacy Policy URL 與 Data Deletion URL（共識 §2；threads_verify_10 refuted Claim 24 更正：出處是 **Threads Use Case 頁**「發佈前需提供」清單，非基本設定頁；切 Live Mode 另需 ToS URL——本次不切 Live，故服務條款以一段落併入隱私頁）。
- **路由與實作**：`/privacy`、`/data-deletion`、**`/deauthorize`**（新增；Threads use case 設定另要求 Deauthorization Callback URL——threads_verify_10 Claim 25）三頁做成 `code/frontend/public/privacy.html`、`data-deletion.html`、`deauthorize.html` **純 HTML**（Vercel 直接服務，`vercel.json` rewrites 排除 `*.html`；SPA 無 JS 時只有空 `<div id="root">`，故不用 React 頁）；React 頁尾連過去。`/deauthorize` 內容一句：「本服務不保存授權狀態，取消授權後不需額外處理。」若 Meta 後台不接受靜態頁作為 Data Deletion Callback，改為後端 `POST /api/meta/data-deletion` 回 200 `{url, confirmation_code}`（Day 1 實填時確認並記回本條）。
- **內容要點**（逐字見 8.7）：蒐集什麼（貼上的文字／網址／圖片、Threads 上被 @ 的公開貼文文字、判定結果）、存多久（知識庫無限期、任務紀錄 5,000 筆滾動）、不蒐集什麼（無帳號、無 cookie 追蹤、localStorage 僅存本機、Threads 只存公開貼文的 `post_id`／`username`／`permalink`）、如何刪除（來信 `{CONTACT_EMAIL}` 附 `/r/{id}` 或貼文連結，7 日內刪除 `tasks.parquet` 該列、`threads_replies.jsonl` 該行與知識庫對應列）、AI 判讀免責、開發模式說明。
- **驗收**：三個 URL 在 Meta App 後台可儲存成功；`curl` 取回的 HTML 不含 JS 也有完整可讀內容（純 HTML）；手機 Safari／Chrome 可讀；全站頁尾連到隱私與資料刪除頁。

### FR-14 AI 額度護欄（P1，報告後）
- **demo 週的護欄**（不需新程式；共識 §4：CGU AIR 新學期金鑰，OpenAI 成本額度 **USD 10** + 本地模型 1,000 萬 tokens，**不買 OpenAI 直連額度**）：(a) **CGU `GET {CGU_BASE_URL}/me/usage` 用量查詢**——`scripts/batch_verify_pending.py:36` 已有現成呼叫（每回合前查、超過 `--budget-cap` 就停），demo 週每日開工前與每次評測前後各查一次並記入 `docs/test/cgu_usage.txt`；(b) `USE_WEB_SEARCH` 開關（評測／批次一律 `false`；demo 現場依 OP-2 實測決定）；(c) `OPENAI_REASONING_EFFORT=low`（config.py:34 預設，openai/cgu 共用此引擎）。預算分配：評測 150 筆 + demo 週查證 + 彩排 ≤ USD 5，保留 USD 5 給報告後補測與 `gpt-5.4` 比較組（可選）。`/health.daily_ai_calls` 與 `ai_usage.jsonl` 改為 P1 一併做。審查意見：FR-14 不符本文件 P0 定義（沒有它 demo 照樣能跑），且會擠壓主線。
- **描述（P1）**：`DAILY_AI_CALL_CAP`（預設 300）達上限後，未命中快取的查證在**建立任務前**回 429 `code:"daily_cap_reached"`（附 `Retry-After` 至隔日 00:00 +08:00）；快取命中不受影響。計數存 `data/ai_usage.json`（`{"date","calls","usd_est"}`），`ai_service` 記錄回應 `usage` 至 `data/ai_usage.jsonl`；`usd_est` 以 `/me/usage` 前後差校準。
- **驗收**：`DAILY_AI_CALL_CAP=1` 時第二次未命中回 429 且 AI mock 未被呼叫；前端顯示 `quota_exceeded_*` 文案；Threads bot 遇此狀態同 AI 不可用（不回覆、不標記）。
- **實作紀錄（2026-09-19，因後端上雲公開而提前實作）**：`app/services/ai_budget.py` + `tests/test_ai_budget.py`、`tests/test_launch_guards.py`（FN-10）。與上述描述的差異：(1) 計數改存 SQL 表 `ai_usage_daily(day, calls)`（與 `database_sql.engine` 同一個資料庫：本機 SQLite／雲端 Supabase），不用 `data/ai_usage.json`——雲端主機的硬碟每次休眠／重啟都會清空，存檔案等於每次重啟歸零；(2) 扣額度是原子操作（`UPDATE … WHERE calls < cap`），在處理器真的要呼叫 AI 之前扣（L3 與圖片分析），所以同時送出與 Threads 機器人也受限；端點在建立任務前先檢查，上限已滿時只放行快取命中（L0 URL／L1 hash／文字輸入的 L2 向量；網址輸入的 L2 需要先爬內文，上限已滿時不做）；(3) 資料庫出錯時退回行程內計數，仍有上限；(4) `ai_usage.jsonl` 與 `usd_est` 未做（每次查證的估算成本已在處理器的 verification log）；(5) `/health.daily_ai_calls` = `{used, cap}`，不讀資料庫（用行程內最近一次看到的數字），`DAILY_AI_CALL_CAP=0` 時為 `null`。

### FR-15 工程清理（P0，支撐上述 FR；共識 §4、§5）
移除死碼：Serper（search_service.py:248-284、`SERPER_API_KEY`）、`TRENDING_KEYWORDS`、Google News 查詢、`googlesearch` 關鍵字爬蟲、Playwright／yt-dlp 管線（crawler.py:188-435）、Gemini embedding 備援（ai_service.py:446-454，768 維汙染風險）、死設定 `DEBUG`／`ENVIRONMENT`／`EMBEDDING_MODEL`。`fake-news-detector.html` 與 `_run_detector.bat` 移至 `legacy/`，README／CLAUDE.md 標示不再維護，`start.bat`／`start.sh` 不再提及。`news_fetcher` 內同步 `requests`／`analyze_content` 呼叫改 `asyncio.to_thread`（news_fetcher.py:350,396,400）。`.gitignore` 修正為 `code/backend/data/factcheck.db`、`code/backend/data/tasks.parquet`、`code/backend/data/threads_*.json*`、`code/backend/data/ai_usage.*` 並 `git rm --cached`（offline_ops tech_debt 第 1 條；`knowledge_base.parquet` 維持提交當種子——FR-18 `--apply` 通過 OP-9 後**重新提交一次**作清洗後種子，其後恢復不提交 runtime 變動）。`ci.yml` 註解移除測試數字，並加 `npm ci && npm run build`（Day 1 就上，讓 Day 3 Vercel 部署前 CI 已驗證前端 build）。

**隨 yt-dlp／Playwright 一起變成死碼、一併移除**：`AIService.transcribe_audio`（ai_service.py:397-422，只有 crawler 抓音軌後呼叫）、設定鍵 `STT_MODEL`／`CGU_STT_MODEL`（config.py:35,42）、`CRAWL_WITH_SCREENSHOT`（:68）、`SEARCH_RESULTS_LIMIT`（:69，關鍵字搜尋專用）及 `.env.example` 對應行；`scripts/seed_data.py`（灌的資料對三層快取隱形，tests_eval 指出已無價值；刪除後 `label_source` 不需 `seed` 值）。CLAUDE.md §2 表格「影片語音轉文字」列刪除（QA-4 勾核）。

**保留（不得改動）**：共識 §4 明列「標記規則（第 9 節三道防線）」——`news_fetcher._title_says_false`／`_title_indicates_debunk`／`_is_real_claim`／`_save_rss_record` 的決策樹與 `tests/test_marking_rules.py` 斷言原樣保留；6.3 的 `label_source` 回填只讀 `category`，不改任何規則函式；`news_fetcher` 的 `to_thread` 改寫只包呼叫、不動判斷邏輯。FR-16 的 Tier 2 判定**直接呼叫** `_title_indicates_debunk()`，不複製、不改寫。

### FR-16 來源分級與顯示（P0；共識 §9 第 1、2 點）
- **描述**：所有進入回應的來源（AI `sources`、provider web_search `url_citation`、RSS／Cofacts 記錄的 `source_url`）先經 `app/utils/source_tier.py:tier_of(url, title="", meta=None) -> 1 | 2 | 3` 分級：
  - **Tier 1**（已有判定的查核機構）：`tfc-taiwan.org.tw`、`mygopen.com`；`cofacts.tw`／`cofacts.g0v.tw` **且**該文章有回覆、回覆類型為 `RUMOR`／`NOT_RUMOR`（以 Cofacts GraphQL **`https://api.cofacts.tw/graphql`**（以程式碼為準：search_service.py:216 既有客戶端打的就是此端點）查 `articleReplies.reply.type`；查不到或無回覆 → Tier 3）；政府機關 `*.gov.tw`（**精確網域尾綴比對** `hostname == "gov.tw" or hostname.endswith(".gov.tw")`，不用子字串）；`who.int`、`cdc.gov`、`cdc.gov.tw`（含於 gov.tw）等官方機構。白名單常數 `TIER1_DOMAINS` 初版依此，D-15 由負責人確認增刪。
  - **Tier 2**（主流媒體查核報導）：標題同時含查核語境詞＋判定詞——**直接呼叫 `news_fetcher._title_indicates_debunk(title)`**（第 9 節三道防線之①，不改動）；無標題可用時（AI 只給 URL）→ Tier 3。
  - **Tier 3**：其餘（一般新聞、部落格、社群貼文、求證平台**未回覆**的貼文、`news.google.com` 轉址、`threads.com`／`facebook.com`／`line.me` 等）。
- **顯示規則（三處一致）**：Web 結果頁 S2、Threads 回覆 7.7、每日貼文 FR-12 **只顯示 Tier 1／2** 作為「查核來源」；Tier 3 不進 `sources`，保留於 `result.related_discussions`（本次 P0 畫面**不顯示**，供稽核；P2 可加「相關討論（未查證）」折疊區）。`sources[]` 每項帶 `tier` 與 `tier_label`（「查核機構」／「媒體查核報導」）。
- **無 Tier 1／2 來源時**：`result.verified=false`、`verification_status="unverified"`，結果頁顯示 `no_verified_source_*` 橫幅「尚無查核機構證實」，且 **`frame_type` 不得為 `green`**（7.8 新列：SAFE 未證實 → 黃「尚無查核機構證實」）；紅燈判定仍可為紅（詐騙訊息本身常無查核報導，AI 判定風險不依賴外部來源），但橫幅照顯示、Threads 回覆的「查核來源」行改為「尚無查核機構證實」。
- **輸入**：`sources` 清單 + 可選標題；**輸出**：`tier`（int，1／2／3；與簽名一致），`tier_label` 由 `TIER_LABELS[tier]` 查表（1「查核機構」、2「媒體查核報導」、3「相關討論（未查證）」）；**成本**：零 AI。**Cofacts 查詢**：同一請求內對多個 Cofacts 來源**並行**查詢（`asyncio.gather` 包 `to_thread`）、整組總逾時 5 s、結果快取於程序內 LRU（`functools.lru_cache(maxsize=512)`，鍵為 article id），失敗／逾時視為 Tier 3（保守）；`tier_of(..., offline=True)` 離線模式**不發任何網路請求**、Cofacts 一律視為 Tier 3（供 `PandasStore.save_record` 與 `_load()` 路徑使用，FR-17）。§9 效能列的「未命中 AI p50 ≤15 s」**不含**此 5 s（Cofacts 查詢時間另計，log 分開記 `tier_ms`）。
- **驗收**：
  1. `tests/test_source_tier.py`（FN-12）：表格測試 ≥15 組 URL／標題 → tier（含 `gov.tw.evil.com` 必須是 Tier 3、`news.google.com/rss/articles/…` Tier 3、Cofacts 有回覆／無回覆兩種以 mock 區分、MyGoPen 標題無判定詞仍 Tier 1（網域即判定）、ETtoday「查核：網傳…是假的」Tier 2、ETtoday 一般新聞 Tier 3）。
  2. `GET /api/result/{id}.result.sources` 每項 `tier ∈ {1,2}`；Tier 3 只出現在 `related_discussions`。
  3. `verified=false` 的結果 `frame_type != "green"`（FN-6 表格新增 2 組輸入）。

### FR-17 知識庫寫入門檻（P0；共識 §9 第 3 點）
- **描述**：AI 判定要寫進 `knowledge_base.parquet` 且**參與向量命中**，必須滿足 (a) 至少一個 Tier 1／2 來源通過 `url_validator.filter_valid_sources`（既有存活檢查），或 (b) 規則命中確定性標記（`label_source="rule"`，即 `_title_says_false`／`_title_indicates_debunk` 命中，或 `gold`／`admin`）。否則以 **`verified=false` 保存**（仍寫列：保留原文與判定供稽核、`label_source` 照記、`hit_count` 仍累計 hash 命中），但：`find_similar_by_vector` 過濾 `verified==True`（pandas_store.py:105-114 同維度過濾旁加一條）、`GET /api/knowledge` 與 `/stats` 只算 `verified==True`。**L1 hash 命中不受影響**（同一段文字再問仍直接回上次結果並帶 `verified=false` 標記——避免重複花 AI 點數；結果頁照顯示「尚無查核機構證實」）。
- **計算位置（v1.3 定案，守住 FN-1 五檔不改斷言）**：`verified`／`source_tier` 由 **`PandasStore.save_record(..., label_source="ai", verified=None)` 內部**計算，不在 `pandas_task_processor` 回填時各自算：對 `sources`（處理器已先過 `url_validator.filter_valid_sources`）逐項取 `tier`——項目已帶 `tier`（處理器經 FR-16 線上分級寫入者）直接採用，否則以 `tier_of(url, title, offline=True)` 離線計算（不發網路請求；Cofacts 網址視為 Tier 3）；`label_source ∈ {rule, gold, admin}` → `verified=True`；否則 `verified = (source_tier ∈ {1,2})`；呼叫端可傳 `verified=True/False` 明確覆寫。`sources` 為空但 `source_url` 為 Tier 1／2（RSS 索引列常見）→ 先把 `source_url` 補進 `sources`（`{title: raw_content 前 40 字, url: source_url}`）再計算，保證 `rule`／`verified` 狀態的來源區不會空白（5.3）。`pandas_task_processor`、`news_fetcher._index_factcheck_claim`、`evaluate.py --seed-db` 只需傳 `label_source`。因此 `tests/test_cache_and_store.py` 直接呼叫 `save_record` 的既有 fixture（`AI_RESULT.sources[0].url = https://165.npa.gov.tw/`，`gov.tw` 尾綴 = Tier 1）自然得 `verified=true`，`test_vector_search_exact_hit` 斷言原樣通過。
- **欄位**（第 6 節）：`knowledge_base.parquet` 加 `source_tier`（int|None：該列來源中的最高等級 1／2／3，無來源為 None）、`verified`（bool）；`tasks.parquet` 同步保存 `verified`／`source_tier` 供 `/api/result`。
- **驗收**：
  1. `tests/test_kb_write_gate.py`（FN-13）：mock AI 回 (i) 一個 Tier 1 來源存活 → `verified=true`；(ii) 只有 Tier 3 來源 → `verified=false` 且 `find_similar_by_vector` 對同向量查詢回空；(iii) `sources=[]` + `label_source="rule"` → `verified=true`；(iv) Tier 1 來源但 `url_validator` 判死 → `verified=false`。
  2. `GET /api/knowledge` 與 `/stats` 對 fixture 中 `verified=false` 列不可見（FN-8 加一組）。
  3. `scripts/check_db.py` 加印 `verified` 分佈（true／false 筆數）供 OP-9 前後比對。

### FR-18 既有資料清洗腳本（P0；共識 §9 第 5 點）
- **描述**：一次性、冪等、預設 `--dry-run` 的 `scripts/clean_sources_2026_09.py`，處理 2026-09-15 稽核發現：知識庫 236 筆中 **52 筆沒有任何來源**、`cofacts.tw` 被引用 33 筆（需逐筆確認有回覆）；熱門牆 63 筆中 `news.google.com` 轉址 31 筆（其中 12 筆 UNVERIFIABLE）。
- **規則**（順序執行，每條可獨立以 `--only=kb|trending` 跑；旗標：`--dry-run`（預設）／`--apply`／`--only=kb|trending`／`--retry-cofacts`）：
  1. 知識庫每列：`sources` 為空但 `source_url` 為 Tier 1／2 → 先把 `source_url` 補進 `sources`（`{title: raw_content 前 40 字, url}`，與 FR-17「計算位置」同一規則；`_index_factcheck_claim` 現況已寫 `sources=[{title,url}]`，此條只補舊列）；再對 `sources` 逐項 `tier_of()`（Cofacts 逐筆查 GraphQL 有無回覆；結果快取到 `data/clean_sources_cache.json` 使重跑零網路；**`--retry-cofacts`** 忽略快取檔中結果為逾時／錯誤者重新查詢，成功者才覆寫快取）→ 寫 `source_tier`；無 Tier 1／2 且 `label_source not in ("rule","gold","admin")` → `verified=false`，否則 `true`；Tier 3 來源自 `sources` 移到新欄位 `related_discussions`（JSON str）。
  2. 知識庫：`raw_content` 為 Cofacts LINE 對話片段（`_is_real_claim()` 既有規則判否、或 `source_url` 為 Cofacts 且無回覆）→ `verified=false` 並標 `content_vector=None`（不索引）。
  3. 熱門牆：`source_url` 為 `news.google.com` → 嘗試以 `HEAD`／`GET` 解析最終網址（走 `safe_url.py`，逾時 10 s）；解析成功 → 覆寫 `source_url` 並以 `(標準化標題, 網域)` 去重（保留 `created_at` 最早者）；解析失敗或仍為 Google → **刪除該列**（12 筆 UNVERIFIABLE 全屬此類，預期刪除）。
  4. 熱門牆每列：`verified` 回填——`label_source="rule"` → `true`；`ai` 且 `source_url` 為 Tier 1／2 → `true`（`source_url` 為 Cofacts 網域時**同規則 1 逐筆查 GraphQL 有無 RUMOR／NOT_RUMOR 回覆**，共用 `clean_sources_cache.json`；無回覆 → Tier 3 → `false`）；其餘 `false`；同時寫 `source_tier`。
- **輸出**：`--dry-run` 只印 diff 摘要（各規則影響筆數 + 每筆 `id/title/before→after`）並寫 `data/clean_sources_report.txt`（UTF-8，勿 `print` emoji，CLAUDE.md §7）；`--apply` 先備份 `knowledge_base.parquet.bak-{date}`／`factcheck.db.bak-{date}` 再寫入；第二次 `--apply` 影響筆數為 0（冪等）。**`--apply` 通過 OP-9 後，把清洗後的 `knowledge_base.parquet` 提交一次**（commit 訊息註明「FR-18 清洗後種子」；`factcheck.db` 仍 gitignored 不提交），否則全新 clone 的 `_load()` 對舊列預設 `verified=False`，知識庫頁 0 筆、向量層對 236 筆全部隱形（OP-1、PF-2 跑不出命中）；提交後恢復 CLAUDE.md §4「runtime 變動不用 commit」慣例（QA-4 勾核加此例外）。
- **驗收**：
  1. OP-9：`--dry-run` 報告經負責人審閱（D-17）後才 `--apply`；apply 後 `check_db.py` 前後比對：知識庫筆數不變（236，只改欄位）、`verified=true` 筆數 ≥ 150（預估：52 無來源 + Cofacts 無回覆者降級）、熱門牆 Google News 列 0 筆、總筆數 63 → 63 − 刪除數。
  2. QA-5：dry-run diff 中不得出現 `label_source="rule"` 被降級的列（規則命中 = 確定性）；抽查 10 筆降級列人工同意 ≥9。
  3. `tests/test_clean_sources.py`（FN-14）：對 fixture Parquet／SQLite 跑 `--dry-run` 不改檔、`--apply` 兩次結果相同（冪等）、Google News 解析以 mock 回公網網址與失敗兩種。
  4. **評測資料不動**：`eval_set.csv`／`eval_*.csv` 不在清洗範圍；`evaluate.py --seed-db` 寫入的 `gold` 列一律 `verified=true`。

### FR-19 AI web_search 網域限制與 prompt 規則（prompt 規則 P0；`allowed_domains` P1，視閘道支援）
- **prompt 規則（P0，零風險）**：`ai_service.py` 系統 prompt「雙重事實查核」段（ai_service.py:42）加逐字規則：「`sources` 只能列出**已對這則訊息做出判定**的查核機構或媒體查核報導（TFC、MyGoPen、Cofacts 有回覆的文章、政府機關公告、主流媒體的查核報導）。找不到這類來源就回 `sources: []`，不要列出求證平台上尚未回覆的貼文、一般新聞或社群貼文，不要猜測或編造網址。」——與 FR-16 後端分級**雙保險**（prompt 減少 Tier 3 產生，`tier_of()` 兜底）。
- **`allowed_domains`（P1，優先級不隨實測改變）**：OpenAI Responses API 的 `web_search` 工具支援 `filters.allowed_domains`（≤20 個網域）；CGU AIR 閘道為 OpenAI-compatible，是否原樣轉發**未驗證**。Day 1 OP-2 以 `test_ai_provider.py --web-search --allowed-domains` 打一次，**只記錄結果、不改優先級**：回 200 且 `url_citation` 全在清單內 → 閘道支援，**維持 P1**，實作（設定鍵 `WEB_SEARCH_ALLOWED_DOMAINS` 於 `_responses_analyze` 帶入 `filters`，ai_service.py:237-238 旁，約 30 分鐘）排在 **Day 6 下午有餘裕時順手做**（D-16），不進 P0 時程；回 400／被忽略 → 閘道不支援，**不做**，靠 prompt + `tier_of()`。設定鍵預設 = `TIER1_DOMAINS`（≤20 個、**不含萬用字元**；`gov.tw` 以裸網域列入，OpenAI 是否以此涵蓋子網域於 OP-2 一併驗證並記錄）；主流媒體網域不在預設內（Tier 2 以標題判定、無網域白名單，留待 P1 實作時決定）。
- **驗收**：FN-1 加「prompt 含上述逐字規則」斷言（字串比對）；OP-2 記錄 `allowed_domains` 實測結果（含 `gov.tw` 子網域涵蓋與否）；P1 實作時 `tests/test_ai_service_contract.py` 加「`WEB_SEARCH_ALLOWED_DOMAINS` 非空時 body 帶 `filters`」案例。

### FR-20 查核結果回補（P1；2026-09-22 新增）
- **描述**：FR-17 讓沒有 Tier 1／2 來源的判定以 `verified=false` 保存，而 URL／hash 層不過濾 `verified`，所以一字不差的重複查詢會一直拿到當初「尚無查核機構證實」的結果，即使查核機構之後已經發布查核。處理分三部分：
  1. **快取層（自動）**：URL／hash 命中 `verified=false` 列時，以該列的向量（本機版列內已存；Postgres 版 `find_*` 不載入向量，改以 `raw_content` 算一次 embedding）到向量層**只比對確定性標記**（`label_source ∈ {rule, gold, admin}`，`find_similar_by_vector(..., label_sources=...)`），達 `SIMILARITY_THRESHOLD` 就改回那一筆，`cache_layer="vector"`。一般「AI 判定＋來源」的列不能取代舊結果：舊結果是針對這段原文判的，換掉它要有查核機構層級的證據，長得像的另一則訊息不夠。不呼叫判讀模型。
  2. **查核文章進庫（不耗判讀模型）**：`POST /api/trending/refresh?analyze=false&per_feed=25&cofacts=false` 只做熱門牆第一階段——抓 MyGoPen／TFC RSS 與 Cofacts、確定性標記、把已判定不實的主張以 `label_source="rule"` 寫進知識庫（`_index_factcheck_claim`，標記規則不變）；只耗 embedding。預設 `analyze=true`、`per_feed=4`、`cofacts=true` 與排程行為相同。`cofacts=false` 只抓 MyGoPen／TFC：Cofacts 的 RUMOR 文章常是對話片段，寫進知識庫前需另外審閱。抓取時一律擋下徵才、闢謠 TOP10、小考題等非查核文章；`_cleanup_legacy_strings` 不再依標題把 Cofacts 已查核的謠言退回 PENDING（2026-09-22 盤點正式資料，原本會誤退 8 筆）。
  3. **唯讀盤點**：`scripts/recheck_unverified.py [--cloud] [--no-fetch]` 對每筆未證實列找最接近的已證實列、最新查核文章，以及該列引用過、現在已有回覆的 Cofacts 文章，依 `hit_count` 排序輸出 `data/recheck_unverified_*.csv`（內含使用者原文，gitignored）。不寫入任何資料。
- **2026-09-22 盤點結果**：正式資料未證實 101 筆（有 1536 維向量 86 筆），對已證實列與 66 篇最新查核文章都沒有達 0.75 者；0.65～0.75 之間 8 筆，皆為同類詐騙話術而非同一則主張。本機資料 75 筆可比對，同樣 0 筆可回補。
- **驗收**：`tests/test_factcheck_supersede.py`（確定性標記取代、AI 判定不取代、低於門檻不取代、已證實列不查向量層、無向量時以原文 embedding、embedding 不可用照舊、查詢出錯照舊回原列、store 標記過濾）；`tests/test_pg_store.py::test_vector_label_sources_filter`；`tests/test_news_fetcher_async.py::test_run_trending_fetch_without_analysis_skips_the_ai_step`。

### FR-21 本站熱門查證（P1；2026-09-22 新增）
- **描述**：熱門頁（S3）分成兩個分頁：「查核機構最新」（原熱門牆，預設）與「本站熱門查證」（`?tab=hot`）。後者列出最近 7 天在本站被查證最多的**已證實**內容。每一次查證只要對應到知識庫某一列（快取命中或新寫入）即計一次；分數 = Σ 0.5^(距今小時數 ÷ 3)（半衰期 3 小時：剛發生算 1 次、3 小時前 0.5 次），同分時最近一次查證較新者在前（`app/services/hot_claims.py`）。卡片沿用知識庫頁，次數 chip 改為「近 24 小時 N 次・近 7 天 M 次」。
- **只公開已證實內容**：尚未證實的列是使用者送出的原文，可能含個資，也可能被人灌量推上排行；公開頁只列 `verified=true` 列，即 `/api/knowledge` 已經公開的同一批資料。提供查核機構的熱搜名單（含未證實內容）沿用同一套分數，但需另以管理端點提供，並先在隱私政策增列用途、遮蔽電話／帳號／人名後才對外——本版未實作。
- **API**：`GET /api/knowledge/hot?limit=10`（`1 ≤ limit ≤ 50`），回 `{window_days: 7, half_life_hours: 3.0, total, records}`；`records` 欄位與 `/api/knowledge` 相同，另加 `recent_24h`、`recent_7d`、`last_seen_at`。資料來源為 `tasks` 的 `kb_id`／`created_at`（`TaskStore.recent_kb_refs`／`PgTaskStore.recent_kb_refs`，只取 `status=completed` 且有 `kb_id` 者，不讀使用者輸入）。
- **文案**（8.7 之外，`i18n.js` EXTRA）：`trending_tabs_label`「熱門內容」、`trending_tab_feed`「查核機構最新」、`trending_tab_hot`「本站熱門查證」、`hot_sub`「大家最近在查的內容，依最近 7 天的查證次數排序，越近的查證權重越高。只列出已有查核來源佐證的判定。」、`hot_count`「近 24 小時 {day} 次・近 7 天 {week} 次」、`hot_empty`「最近 7 天還沒有已證實的熱門查證。」
- **驗收**：`tests/test_hot_claims.py`（衰減排序、視窗、同分順序、查證紀錄篩選、端點只回已證實列且欄位與 `/api/knowledge` 一致、`limit` 界線）；`tests/test_pg_store.py::test_recent_kb_refs_matches_local_store`；前端 `src/pages/trending/hot.test.js`；fixture `knowledge_hot.json`／`knowledge_hot_empty.json`（`/trending?tab=hot`、`?fixture=empty`）。

---

## 5. API 契約

基底：`https://{api-host}`（demo 週為 Cloudflare Tunnel 網址，共識 §6）；無版本前綴；所有回應 `application/json; charset=utf-8`。

### 5.1 保留（行為不變或只加欄位）

| 端點 | 說明 | 備註 |
|------|------|------|
| `GET /health` | 健康檢查 | 加 `ai_available: bool`（`AIService._available`）、`threads_mode`、`scheduler: {enabled: bool, interval_hours: int}`（讀 `ENABLE_SCHEDULER`／`TRENDING_FETCH_INTERVAL_HOURS` config.py:81，供 S3 `scheduler_on/off` 文案；FN-3 斷言欄位存在）、`daily_ai_calls:{used,cap}`（`DAILY_AI_CALL_CAP=0` 時回 `null`）、`storage_backend: "local"|"supabase"`（2026-09-19 新增：雲端沒接上資料庫時後端會退回本機檔案，這個欄位看得出來）；不呼叫付費 API |
| `GET /` | `{message, version:"0.3.0", docs}` | 版本號升 |
| `GET /api/analyze/task/{id}/status` | 任務狀態 | 不變（analyze.py:275-292） |
| `GET /api/analyze/task/{id}` | 舊結果端點 | 保留相容；pending／processing 改回 **202** `{task_id, status}`（不再回 200 SAFE 佔位，backend_api tech_debt 第 3 條）；前端改用 `/api/result/{id}` |
| `GET /api/trending` | 熱門列表 | `limit` 加 `ge=1`；記錄加 `platform`、`post_id`、`label_source`、`result_id`、`verified`、`source_tier`（FR-16／18） |
| `GET /api/knowledge` | 知識庫 | 加 `offset`（`ge=0`）、`regex=False`；**只回 `verified=true` 列**（FR-17）；記錄加 `id`、`data_type`、`label_source`、`last_result_id`、`source_tier`；`sources` 只含 Tier 1／2 |
| `GET /api/knowledge/stats` | 統計 | 只統計 `verified=true` 列；加 `unverified_count`（供 S6 `/bot` **P1** 元件「知識庫未證實筆數」與 `check_db.py`／稽核，不顯示於 S4） |
| `POST /api/admin/tasks/{task_id}/override` | 管理者覆寫（API 保留、無 UI，共識 §2） | 加 `X-Admin-Token` 驗證 |
| `POST /api/feedback/tasks/{task_id}` | 使用者回饋 | 不變；前端本次不接 |

### 5.2 修改

| 端點 | 變更 | 理由／出處 |
|------|------|-----------|
| `POST /api/analyze/text` | 回應加 `result_id`（= `task_id`）。每 IP 速率限制**本次不做**（P2；demo 週只有本機與 tunnel，公開上線才需要），每日額度護欄為 FR-14 P1 | FR-01、第 9 節 |
| `POST /api/analyze/url` | 伺服器端驗證 URL 與私網過濾；`task_type="analyze_url"`；不再委派 `/text` | analyze.py:165；FR-02 |
| `POST /api/analyze/image` | magic bytes（415）、10 MB 上限（413）、bytes hash | analyze.py:209-225；FR-03 |
| `POST /api/analyze/sync` | 回應 `AnalysisResult` v2：加 `result_id`、`ai_unavailable`、`similar_news`（response_model 補宣告）、`category_label`、`analyzed_at`；文字不爬 Google；網址爬取失敗回 200 UNVERIFIABLE 而非 500；`cached`／`cache_layer` 保留（共識 §4）；fallback 契約見 5.5 | backend_api tech_debt 第 1 條 |
| `POST /api/trending/refresh` | 需 `X-Admin-Token`；2026-09-22 加 `analyze`（預設 `true`；`false` 不呼叫判讀模型）、`per_feed`（預設 4，1～25）與 `cofacts`（預設 `true`） | backend_api gaps 第 1 條；FR-20 |
| `GET /api/threads/status` | 欄位擴充（5.3） | — |
| `POST /api/threads/poll` | 需 `X-Admin-Token`；**非同步**啟動一輪（維持現況），立即回 202 `{started:true}`；`/bot` 頁與 `scripts/test_threads_bot.py --poll` 改輪詢 `GET /api/threads/status.last_poll_at` 直到變動（腳本印出 `last_poll_stats`）。理由：單則最壞路徑（爬蟲 ≤`CRAWLER_TIMEOUT` + AI provider 鏈每個 60 s；現為單一 `cgu` 但程式仍支援多個，且 `_run_analysis` 最後會關 web_search 再試一次）可達 2–4 分鐘，且 Cloudflare Tunnel 單請求上限 100 s 會回 524。進行中 → 409 `poll_in_progress`；`THREADS_MODE=off` → 200 `{started:false, code:"threads_disabled"}`。demo 週 `THREADS_MAX_REPLIES_PER_POLL=2` | 共識 §10；審查 |

### 5.3 新增

**`GET /api/result/{id}`**（FR-04）— 公開、無驗證、`Cache-Control: max-age=5`。

```json
{
  "id": "6f0d1c2e-....-uuid4",
  "status": "pending | processing | completed | failed",
  "input_type": "text | url | image",
  "input_preview": "前 200 字；url 為完整網址；image 為「[圖片]」",
  "source_url": null,
  "origin": "web | threads | threads_sim",
  "platform_post": {
    "platform": "threads",
    "post_id": "1793xxxx",
    "permalink": "https://www.threads.com/@user/post/Cxxxx",
    "username": "user"
  },
  "created_at": "2026-09-16T10:21:00+08:00",
  "completed_at": "2026-09-16T10:21:14+08:00",
  "ai_unavailable": false,
  "result": {
    "frame_type": "red | yellow | green | grey",
    "frame_label": "詐騙警告 | 假訊息 | 風險訊息 | 查無異常 | 尚待確認 | 尚無查核機構證實 | 無法查證 | AI 暫時無法使用",
    "is_risk": true,
    "risk_type": "SCAM | MISINFO | SAFE | UNKNOWN | UNVERIFIABLE",
    "category": "Phishing",
    "category_label": "釣魚詐騙",
    "confidence_score": 0.93,
    "confidence_level": "高 | 中 | 低",
    "confidence_note": "模型自評信心，未經機率校準（實際效能請參考評測報告）",
    "summary": "≤120 字一句摘要",
    "explanation": "白話說明",
    "sources": [{"title": "MyGoPen：健保卡停用是假的", "url": "https://www.mygopen.com/...", "tier": 1, "tier_label": "查核機構"}],
    "related_discussions": [{"title": "Tier 3 來源（不顯示於 P0 畫面）", "url": "https://...", "tier": 3}],
    "verified": true,
    "verification_status": "verified | rule | unverified",
    "source_tier": 1,
    "similar_news": [{"title": "raw_content 前 60 字", "url": "{PUBLIC_BASE_URL}/r/{last_result_id} 或 null", "date": "2026-09-10", "source": "知識庫", "similarity": 0.81}],
    "cached": true,
    "cache_layer": "url | hash | vector | null",
    "label_source": "ai | rule | gold | admin",
    "kb_id": "knowledge_base 列 id | null"
  },
  "error": null,
  "share": {
    "text": "🔴 AI 判定這則訊息是詐騙：{summary≤80}。查核來源：{source_domain}",
    "url": "https://{PUBLIC_BASE_URL}/r/6f0d1c2e-..."
  }
}
```
- `platform_post` 只在 `origin` 為 `threads*` 時有值，否則 `null`。
- `status != completed` → `result: null`、`share: null`；`failed` → `error: {code:"analysis_failed", message}`（訊息為通用文案，原始例外只進 log）。
- `ai_unavailable=true` 時 `status="completed"`、`result.frame_type="grey"`（**第四種框色，僅此情況**）、`frame_label`=「AI 暫時無法使用」、`share=null`。
- `category_label` 由後端統一中文化（取代前端各自 `CAT_MAP`）。
- **來源與證實狀態**（FR-16／17）：`sources[]` 只含 Tier 1／2，每項 `tier ∈ {1,2}`、`tier_label ∈ {"查核機構","媒體查核報導"}`；Tier 3 在 `related_discussions[]`（P0 畫面不顯示，可為 `[]`）。`verification_status` **推導順序（固定）**：① `label_source ∈ {rule, gold, admin}` → `rule`；② 否則 `source_tier ∈ {1,2}`（≥1 個 Tier 1／2 來源存活）→ `verified`；③ 否則 `unverified`（rule 與 Tier 1 來源同時成立時取 `rule`）。`verified` = `verification_status != "unverified"`。**`rule`／`verified` 狀態保證 `sources` 非空**：`sources` 為空但列的 `source_url` 為 Tier 1／2 時，後端已在寫入時把 `source_url` 補進 `sources`（FR-17「計算位置」、FR-18 規則 1），因此結果頁來源區與 Threads「查核來源」行只在 `unverified` 時才會出現「尚無查核機構證實」。`unverified` 時 `frame_type ≠ "green"`（7.8），結果頁顯示 `no_verified_source_*` 橫幅，`share.text` 不含「查核來源：」段。**例外**：`risk_type = UNVERIFIABLE`（爬取失敗，不呼叫 AI）與 `ai_unavailable = true` 兩種結果無來源，`verification_status` 固定 `unverified`、`verified=false`，但**不觸發** `no_verified_source_*` 橫幅（各自以 S2 狀態 7 `unverifiable_body`／狀態 5 `ai_unavailable_*` 呈現；8.7 `frame_yellow_no_source` 註解已強調兩者語意不同）。`source_tier` = `sources` 中最高等級（1 或 2），無來源為 `null`。
- 404 `{"detail":"找不到這筆查證","code":"result_not_found"}`。

`GET /api/threads/status`（擴充；公開唯讀、不含 token 本體）：
```json
{
  "enabled": true, "mode": "live | sim | off", "configured": true,
  "poll_minutes": 5, "replied_count": 12,
  "last_poll_at": "iso | null",
  "last_poll_stats": {"checked": 3, "replied": 2, "skipped": 1, "errors": 0},
  "last_error": "string | null", "backoff_until": "iso | null",
  "token_expires_at": "iso | null", "token_days_left": 41,
  "authorized_at": "iso | null", "auth_days_left": 71,
  "reply_quota": {"usage": 12, "total": 1000},
  "daily_replies": 3, "daily_cap": 50,
  "dev_mode_notice": "目前為開發模式：只有被加入為測試人員的 Threads 帳號 @{BOT_HANDLE} 才會收到回覆。"
}
```

`GET /api/threads/replies?limit=10`（FR-10、FR-11；公開唯讀）：`{records:[{mention_id, mode, result_id, frame_type, risk_type, username, source_text_preview, reply_text, reply_id, permalink, replied_at}]}`，資料來自 `data/threads_replies.jsonl` 倒序。

`POST /api/threads/refresh-token`（管理 token；**P1，報告後**）：呼叫 `GET https://graph.threads.net/refresh_access_token?grant_type=th_refresh_token&access_token=…`，成功寫 `data/threads_token.json`，回 `{expires_at}`；token <24 h 舊 → 400 `token_too_young`。demo 週以 60 天 token 撐過即可，續期先由 `scripts/threads_auth.py --refresh` 手動執行（同一段邏輯，無端點）。

`POST /api/threads/daily-post`（P2，管理 token）：FR-12。

`GET /api/knowledge/hot?limit=10`（FR-21；公開唯讀、只回 `verified=true` 列）：`{window_days, half_life_hours, total, records:[{…/api/knowledge 記錄欄位, recent_24h, recent_7d, last_seen_at}]}`。

### 5.4 `POST /api/analyze/sync` 回應欄位（完整）

`AnalysisResult` v2（analyze.py:113-130 擴充）：既有 `frame_type, frame_label, border_color, display_info, related_links, is_risk, risk_type, category, confidence_score, confidence_level, confidence_note, summary, explanation, sources, cached, cache_layer` 保留；新增 `result_id: str`、`ai_unavailable: bool`、`similar_news: list`（v1.2 本次固定 `[]`，P1 後填向量近鄰）、`category_label: str`、`label_source: str`、`analyzed_at: str`、`verified: bool`、`verification_status: str`、`source_tier: int|None`、`related_discussions: list`（FR-16／17；`sources[]` 每項加 `tier`／`tier_label`）。`timeline` 不再產生（`similar_news` 已含日期）。`GET /api/analyze/task/{id}`（completed）與 `GET /api/result/{id}.result` 回同一結構。

### 5.5 fallback 契約（AI 不可用）

- 後端仍回 **HTTP 200**（維持 CLAUDE.md §2 契約；Threads bot 與舊查核儀依賴此契約。`evaluate.py` 與 `test_ai_provider.py` 直接呼叫 `AIService.analyze_content`、不經 HTTP，不依賴 200，但依賴下一條的字樣）。
- `summary` 仍以「AI 分析暫時無法使用」開頭（`ai_service._default_fallback_result` ai_service.py:92-102）。現有 **7 處**辨識點：ai_service.py:99、App.jsx:9、threads_bot.py:50、pandas_task_processor.py:42、news_fetcher.py:150、`scripts/evaluate.py:46`、`scripts/test_ai_provider.py:43`（另有封存的查核儀）。後端與腳本統一改呼叫 `app/utils/verdict.py:is_fallback()`（清單含 `evaluate.py`、`test_ai_provider.py`，否則改字樣時評測腳本會靜默失效），測試守住字樣。
- **新增** `ai_unavailable: true` 布林；所有**新寫**的客戶端一律用布林判斷，前綴只留給舊碼相容。
- `explanation` 改為固定通用文案「AI 服務暫時無法使用（額度用盡或連線問題），請稍後再試。」；上游閘道錯誤原文只寫 log（修正 ai_engine tech_debt 第 4 條洩漏）。
- 不寫知識庫、Threads 不回覆、結果頁顯示灰框（8.3）。

### 5.6 授權

- 管理端點（`/api/threads/poll`、`/api/threads/refresh-token`、`/api/threads/daily-post`、`/api/trending/refresh`、`/api/admin/*`）：標頭 `X-Admin-Token: {ADMIN_TOKEN}`；缺或錯 → 401 `unauthorized`；`ADMIN_TOKEN` 為空字串時這些端點一律 403 `admin_disabled`（避免忘記設而全開）。`ADMIN_TOKEN` ≥32 字亂數。
- 公開端點：`/api/analyze/*`（本次無速率限制；每日額度 FR-14 P1）、`/api/result/{id}`、`/api/trending`、`/api/knowledge*`、`/api/threads/status`、`/api/threads/replies`、`/health`；前端靜態頁 `/privacy.html`、`/data-deletion.html`、`/deauthorize.html`、`/oauth/callback`。
- `start.bat`／`start.sh` 首次建立 `.env` 時自動產生 32 字亂數 `ADMIN_TOKEN` 寫入（避免 demo 前忘記設而把 `/api/threads/poll` 擋住）。

### 5.7 錯誤格式

```json
{ "detail": "人可讀訊息（繁中）", "code": "machine_code" }
```
沿用 FastAPI 預設 `detail`；`code` 為新增機器碼。列舉：`invalid_url`（422）、`blocked_url`（422）、`validation_error`（422；`detail` 為 pydantic 陣列時另附 `message` 字串供前端顯示）、`unsupported_media`（415）、`payload_too_large`（413）、`result_not_found`／`task_not_found`（404）、`analysis_failed`（500）、`unauthorized`（401）、`admin_disabled`（403）、`daily_cap_reached`（429，附 `Retry-After`；FR-14 P1）、`rate_limited`（429；P2 保留碼名）、`poll_in_progress`（409）、`threads_disabled`（200）、`token_too_young`（400；P1）。

---

## 6. 資料模型變更（最小必要）

原則：只加欄位、不改型別、不改主鍵；舊資料讀入時補預設值；單機 SQLite + Parquet（共識 §4）。**不寫獨立遷移腳本**（v1.0 的 `scripts/migrate_2026_09.py` 取消）：Parquet 由 `_load()` 缺欄位補預設、SQLite 由 `init_sql_db()` 冪等 `ALTER TABLE` 完成，OP-7 改驗證「舊檔載入後新欄位為預設值、筆數不變」。

### 6.1 `tasks.parquet`（task_store.py:34-46）— 承載 `/r/{id}`

| 新欄位 | 型別 | 預設（舊列） | 為什麼 |
|--------|------|-------------|--------|
| `input_type` | str | 由 `task_type` 推得 | `/api/result` 要回 `input_type`，不再靠字串前綴 |
| `origin` | str | `"web"` | 區分 web／threads／threads_sim（`/bot` 頁、論文統計「來自 Threads 的查核量」） |
| `threads_mention_id` | str\|None | None | mention ↔ task ↔ 回覆對應（threads_code gaps 第 3 條） |
| `threads_reply_id` | str\|None | None | 同上；重複回覆稽核 |
| `platform_post` | JSON str\|None | None | `{platform, post_id, permalink, username}` |
| `ai_unavailable` | bool | False | 5.5 契約 |
| `label_source` | str | `"ai"` | 5.3 |
| `kb_id` | str\|None | None | 指回 `knowledge_base` 列 |
| `verified` | bool | **舊列一律 False**（不在 `_load()` 重算：`tier_of` 對 Cofacts 網址要查 GraphQL，會違反 6.3「啟動時不發網路請求」與 OP-7 離線載入；舊任務不在 demo 範圍，其 `/r/{id}` 顯示「尚無查核機構證實」橫幅可接受） | FR-16／17；`/api/result` 的 `verified`／`verification_status` |
| `source_tier` | int\|None | None | 同上 |
| `related_discussions` | JSON str\|None | None | Tier 3 來源（稽核用，P0 不顯示） |

`_MAX_TASKS` 500 → **5,000**（task_store.py:13）；修剪只砍 `status in (completed, failed)` 且最舊者，不砍 `pending/processing`。啟動 reaper（把 >10 分鐘仍 `pending/processing` 的任務標 `failed`）降為 **P1**——結果頁 90 秒超時態已涵蓋 demo 需求。`_load()` 對缺欄位 `df[col] = default`（同 pandas_store.py:24-25 對 `source_url` 的既有做法；這就是本次唯一的「遷移」）。

### 6.2 `knowledge_base.parquet`（pandas_store.py:28-34）

| 新欄位 | 型別 | 預設（舊列） | 為什麼 |
|--------|------|-------------|--------|
| `label_source` | str | `"ai"`；`news_fetcher._index_factcheck_claim` 寫入者改 `"rule"`；`evaluate.py --seed-db` 改 `"gold"`；管理者覆寫改 `"admin"`（`scripts/seed_data.py` 已刪，無 `seed` 值；值域全文統一為 `ai\|rule\|gold\|admin`） | 共識 §10：`ai_score` 混用規則硬編 0.9/0.95 與模型信心，缺 `label_source`；FR-07 chip |
| `origin` | str | `"web"` | 統計 Threads 來源 |
| `last_result_id` | str\|None | None | 知識庫卡片可連到結果頁 |
| `source_tier` | int\|None | 由 FR-18 清洗腳本回填（`_load()` 補 None） | 共識 §9 第 3 點；FR-16 |
| `verified` | bool | `_load()` 補 **False**（保守：未經清洗腳本回填的舊列一律不參與向量命中；FR-18 `--apply` 後依規則回填，**且清洗後的 parquet 提交一次作新種子**——否則全新 clone 知識庫頁 0 筆，OP-1）；新寫入者由 `save_record` 內部計算（`label_source ∈ {rule, gold, admin}` → True，否則依 `source_tier`，FR-17「計算位置」） | 共識 §9 第 3 點；`find_similar_by_vector` 與 `/api/knowledge` 過濾條件 |
| `related_discussions` | JSON str\|None | None | Tier 3 來源自 `sources` 移出後的存放處 |

`data_type` 新增 `"IMAGE"`（FR-03）。**寫入門檻**（FR-17）：`verified`／`source_tier` 由 `PandasStore.save_record` **內部**以 `tier_of(..., offline=True)` 計算（`pandas_task_processor` 與 `news_fetcher._index_factcheck_claim` 只傳 `label_source`，見 FR-17「計算位置」；`test_cache_and_store.py` 既有 fixture 因此不需改）；`find_similar_by_vector` 加 `verified == True` 過濾（與既有同維度過濾並列）；`get_knowledge`／`stats` 同。不清除既有 768/3072 維混雜向量（pipeline_store 流程 7）：`find_similar_by_vector` 既有同維度過濾（pandas_store.py:105-114）已讓它們隱形；`_load_knowledge_base` 後 log 一次「非 1536 維列數」供論文說明。既有 236 筆與 `eval_*.csv` 不動（評測數據要能延續）。

### 6.3 `fact_check_records`（fact_check_record.py:10-23，SQLite）

| 新欄位 | 型別 | 為什麼 |
|--------|------|--------|
| `platform` | String(20) NULL | 共識 §10；`rss`／`cofacts`／`threads`；FR-12 每日貼文寫 `"threads"` 防重發 |
| `post_id` | String(64) NULL | Threads media id |
| `label_source` | String(10) NULL | 值域同 6.2 `ai\|rule\|gold\|admin`（`_save_rss_record` 規則分支寫 `rule`，`_analyze_record` 寫 `ai`；只加寫入欄位，**不改**規則函式本身） |
| `result_id` | String(36) NULL | 熱門卡可連 `/r/{id}`（D-01：本次不回填，新聞分析不建任務，熱門卡一律外連） |
| `verified` | Boolean NULL | FR-16／18：`rule`／`gold`／`admin` → true；`ai` 且 `source_url` 為 Tier 1／2 → true；其餘 false；S3 `verified=false` 顯示 `chip_pending`。**D-01 決策：此為唯一定義**——管線寫入（`news_fetcher._fill_record_provenance`，`_save_rss_record` 與 `_analyze_record` 共用）與 FR-18 規則 4 同公式；AI 回傳 `sources`（含快取命中列的舊來源）不參與熱門列 `verified`，只決定知識庫列 `verified`（6.2、FR-17 (a)）。`_analyze_record` 對 `source_url` 線上分級（Cofacts 查回覆），`_save_rss_record` 離線；Cofacts 離線得 3 時不降級先前的 1／2 |
| `source_tier` | Integer NULL | `tier_of(source_url, title)` 結果，由 FR-18 回填、`_save_rss_record` 新寫入時計算 |

遷移：`init_sql_db()`（database_sql.py:29-31）在 `create_all` 後執行冪等 `ALTER TABLE fact_check_records ADD COLUMN …`（先 `PRAGMA table_info` 檢查）。`to_dict()` 回傳新欄位。既有 63 筆 `label_source` 回填：`category in ("已查核假訊息","官方衛教","官方資訊")` → `rule`，其餘非 NULL `risk_type` → `ai`；`label_source=rule` 時前端顯示「查核機構標記」而非信心。`verified`／`source_tier` 回填與 Google News 轉址列清理由 FR-18 腳本負責（不放在 `init_sql_db()`，避免啟動時發網路請求）。

### 6.4 新檔案（皆 gitignored）

- `data/threads_token.json`：`{"access_token","obtained_at","expires_at","authorized_at","user_id"}`（`authorized_at` = 首次授權時間，供 90 天授權期限計算，7.3）；存在時優先於 `.env` 的 `THREADS_ACCESS_TOKEN`（`ThreadsService.__init__` Day 2 一併改）。
- `data/threads_state.json`：由 `{"replied_ids":[...]}` 擴為 `{"replied_ids", "last_since": int, "last_poll_at", "last_stats", "last_error", "daily": {"date","replies"}, "backoff_until", "backoff_n"}`；讀取缺鍵補預設；寫入改 temp 檔 + `os.replace` 原子替換；**每處理完一則就寫一次**（現行整輪結束才寫，crash 會重複回覆）。
- `data/threads_replies.jsonl`：每行 `{mention_id, mode, result_id, frame_type, risk_type, username, source_text_preview, reply_text, reply_id, permalink, replied_at}`；live／sim 共用；供 `/api/threads/replies`。
- `data/threads_sim/mentions.json`、`data/threads_sim/replies.jsonl`：7.9。
- `data/ai_usage.json`／`data/ai_usage.jsonl`：FR-14（P1）。
- `data/threads_poll.lock`：7.4 互斥。
- `data/clean_sources_cache.json`（Cofacts 逐筆回覆查詢快取）、`data/clean_sources_report.txt`（dry-run diff 報告）、`data/knowledge_base.parquet.bak-{date}`／`data/factcheck.db.bak-{date}`（`--apply` 前備份）：FR-18；皆 gitignored（`.gitignore` 加 `code/backend/data/clean_sources_*`、`code/backend/data/*.bak-*`）。

---

## 7. Threads 整合規格

全部依 threads_gap_analysis（官方文件核對）與 threads_verify_10（更正）為準；程式基底 `threads_service.py`／`threads_bot.py`／`api/threads.py`。

### 7.1 權限清單與模式
- App 用途 Threads API；權限：`threads_basic`（不可移除）、`threads_content_publish`、`threads_manage_replies`、**`threads_manage_mentions`**（共識 §3 補列；threads_service.py:5-6、`.env.example:48-49`、CLAUDE.md §11 的清單要改）。`threads_read_replies` **不需要**（只有讀回覆樹才用）。開發模式下這四個權限對 App 角色使用者（Administrator／Threads Tester）直接可用，不送審、不需企業驗證（threads_verify_10 confirmed Claim 20；additional_findings 第 4 條）。
- 模式：`THREADS_MODE=off|live|sim`（預設 `off`；取代 `ENABLE_THREADS_BOT`，舊鍵 `true` 視為 `live`）。`DEMO_MODE` 不再影響 Threads（單一由 `THREADS_MODE` 控制）。

### 7.2 帳號與角色
- 機器人：**已建立**的公開 Threads 帳號 `@factcheck_tw_bot`（第 2 節；2025-09 起可不綁 Instagram；C7 剩餘工作 = 確認公開、設顯示名稱、填 bio），以 **Threads Tester** 身分加入 App（App Dashboard > App roles > Roles > Add People > Threads Tester；threads_verify_10 Claim 4）——Administrator 是 Facebook 開發者帳號的角色，只保留給負責人的開發者帳號（App 擁有者），純 Threads 帳號不走這條。bio 建議：「AI 假訊息查證機器人（開發中）。回覆可疑貼文並 @我，我會給 🔴🟡🟢 判定與來源。判讀由 AI 產生，請自行查證。{PUBLIC_BASE_URL}」
- 測試者：機器人帳號、組員 A、組員 B、（可選）指導教授 → App roles → Roles → Add People → Threads Tester；受邀者在 Threads App 設定 →「網站權限」接受邀請；**四個帳號全部設為公開**。Day 2 非程式線驗收：四個帳號皆已接受邀請且為公開。
- 開發模式限制的使用者說明（`/bot` 頁、隱私頁、`/api/threads/status.dev_mode_notice`，逐字）：「目前為開發模式：只有被加入為測試人員的 Threads 帳號 @{BOT_HANDLE} 才會收到回覆。公開服務需通過 Meta App Review 與企業驗證，為本專題論文所述之上線條件。」

### 7.3 token 生命週期
1. 取得：`scripts/threads_auth.py`（新增，**Day 2 程式線約 1 小時**：純 `requests`、三步——印授權 URL → 貼 code 換短效 → 換長效並寫 `threads_token.json`；另有 `--refresh` 子命令）印出授權 URL `https://threads.com/oauth/authorize?client_id={THREADS_APP_ID}&redirect_uri={PUBLIC_BASE_URL}/oauth/callback&scope=threads_basic,threads_content_publish,threads_manage_replies,threads_manage_mentions&response_type=code` → 負責人以機器人帳號登入授權 → 前端 `/oauth/callback` 靜態頁顯示 `code` + 複製鈕 → 貼回腳本 → `POST https://graph.threads.com/oauth/access_token`（短效 1 h；回應含 `user_id`，直接當 `THREADS_USER_ID`，不必另呼叫 `/me`）→ `GET https://graph.threads.net/access_token?grant_type=th_exchange_token&client_secret=…&access_token=…` 換 60 天長效 → 寫 `data/threads_token.json`。redirect URI 需登錄於 App 的 Valid OAuth Redirect URIs。
2. 續期：demo 週**手動** `scripts/threads_auth.py --refresh`（`age ≥ 24h` 才可；`GET /refresh_access_token?grant_type=th_refresh_token`，成功覆寫檔案）。APScheduler job `threads_token_refresh`（每日 03:00、`days_left ≤ 14` 自動續）與 `POST /api/threads/refresh-token` 皆 **P1、報告後**——60 天 token 撐過 demo 綽綽有餘。
3. 顯示：`/api/threads/status.token_days_left`；<0 或 API 回 HTTP 401 → `last_error="token_invalid"`、輪詢暫停；`/bot` 頁的到期黃色警示為 P1。
4. 保存：`THREADS_APP_ID`、`THREADS_APP_SECRET`（注意取自 **Threads use case 頁的 Threads App ID／Secret**，不是 Meta App ID）只在 `.env`；不進 git、不進 Docker image（補 `.dockerignore`）；log 不含 token。
5. 授權期限（與 token 分開）：公開帳號的授權本身 **90 天**到期、refresh 可再延；私人帳號到期需重新授權（threads_verify_10 Claim 4／5）。`threads_token.json` 記 `authorized_at`，`/api/threads/status` 回 `auth_days_left`；報告後若機器人續跑，第 90 天前需重跑 `threads_auth.py`（R9）。

### 7.4 輪詢演算法（`run_threads_poll`）
```
if mode == off or not svc.available: return {started:false}
if backoff_until and now < backoff_until: return {skipped:"backoff"}
acquire poll_lock (asyncio.Lock + data/threads_poll.lock; busy → 409 / log "poll_in_progress")
since = max(state.last_since - 120, 1688540400)        # 重疊 2 分鐘，避免時鐘偏差漏件；官方下限 1688540400
url = f"{user_id}/mentions?fields=id,text,username,permalink,media_type,replied_to,timestamp&since={since}"
# root_post,is_reply 只在 retrieve-replies 頁定義，mentions 上是否可取為推論（verify_10 additional_findings 7）：
# Day 2.5 --live 加上後回 200 才納入；程式對缺欄位一律容忍（.get），未知欄位若回 error 就退回上列七個
mentions = []
loop ≤ 5 pages:                                          # limit/分頁參數在 mentions 頁未文件化（verify_10 refuted Claim 8）
  page = GET url ; mentions += page.data                 # 以 Threads Media 頁的 paging.next / paging.cursors.after 模式處理
  if not page.paging?.next: break ; url = page.paging.next
mentions.sort(by timestamp asc)
quota = GET {user_id}/threads_publishing_limit?fields=reply_quota_usage,reply_config   (失敗視為未知、不擋)
replied_this_run = 0
for m in mentions:
  if m.id in replied_ids or m.username.lower() == bot_username: continue
  if replied_this_run ≥ THREADS_MAX_REPLIES_PER_POLL(5) or daily.replies ≥ THREADS_MAX_REPLIES_PER_DAY(50): break
  if quota and quota.usage ≥ quota.total - 10: last_error="reply_quota_near_limit"; break
  handle(m)                                              # 7.5；每則處理完立即原子寫 state
state.last_since = max(m.timestamp for m in mentions) or now
save_state atomically; release lock; return stats
```
`THREADS_POLL_MINUTES` demo 週設 1（config.py:98 預設 5）。APScheduler 與 `POST /api/threads/poll` 共用同一把鎖；uvicorn 單 worker（文件明載）。

### 7.5 單則 mention 處理 `handle(m)`
```
if m.replied_to.id 在本機 threads_replies.jsonl 的 reply_id 中 → skip + mark      # 零 API 成本先判：別把自己的判定貼文當謠言
                                                                                # 注意 replied_to 只有 {id}，沒有 owner 欄位（verify_10 Claim 15）
target = resolve_target(m):
  1. m.replied_to.id 存在（dict 形狀，webhook 範例證實；threads_bot.py:60-61 dict/純值雙處理保留）
     → GET /{id}?fields=id,text,username,permalink,media_type
     回傳 username.lower() == bot_username → kind="self"（skip + mark，第二道自我判斷）
     成功且 strip_mentions(text) ≥ 8 字 → kind="text"                              # 主要依據是「有無可用文字」
     media_type in ("IMAGE","VIDEO","CAROUSEL_ALBUM") 且 strip_mentions(text) < 8 字 → kind="media_only"
                                                                                # 正向清單；永不與 "TEXT" 比對（FR-09 驗收 5）
     HTTP 401/403/404（非 Tester、私人帳號、權限）→ kind="unreadable"               # 以 HTTP 狀態碼為主，error.code 只 log
     其他未列入的 4xx（HTTP 400 等；429 除外）→ kind="failed"                       # 2026-09-19 修訂：同 7.10「參數錯／未知 4xx」保守路徑
     HTTP 429／5xx／逾時 → kind="transient"（不回覆、不標記，下輪重試）            # 429 另依 7.10 設 backoff_until 並中止本輪
  2. 無 replied_to → 用 mention 本文 strip_mentions；≥ 8 字 → "text"，否則 "too_short"
  3. text 內含 http(s) 網址且去網址後 < 8 字 → input_type="url"（走 FR-02），否則 input_type="text"
if kind == self: mark; return
if kind == failed: 標 failed（寫 state.failed，終態）+ log 全文; 不回覆、不重試、不進 replied_ids; return   # 2026-09-19 修訂
if kind == transient: return                                     # 不回覆、不標記，下輪補回
if kind in (media_only, unreadable, too_short): reply(固定文案 7.7); mark; write replies.jsonl; return
task_id = create_task("threads_mention", text, origin=mode, threads_mention_id=m.id, platform_post={...})
result = await process_analysis_task_async(task_id, text, input_type)
if result.ai_unavailable or daily_cap_reached: return           # 不回覆、不標記，下輪補回
reply_text = format_verdict_reply(result, result_url=f"{PUBLIC_BASE_URL}/r/{task_id}")   # 7.7
reply_id = svc.reply_to(m.id, reply_text)                        # 7.6
if reply_id: mark; update_task(threads_reply_id); append replies.jsonl; daily.replies += 1; write state
```

> **2026-09-19 修訂（票 T-13；統一 7.5 與 7.10／FN-4 的文字衝突）**：原文「HTTP 401/403/404 **或其他 4xx** → `kind="unreadable"`」與 7.10「任何未列入的 4xx 走保守路徑：該 mention 標 failed + log 全文，不重試、不回覆」及測試準則 FN-4「未知 4xx → 標 failed 不回覆」互相矛盾。**以 7.10／FN-4 為準**：讀原貼文時只有 HTTP 401／403／404 視為「讀不到」並回 `reply_cannot_read`（401 在此端點當作讀不到；token 失效由 mentions 端點的 401 判定，見 7.10）；其他未列入的 4xx（HTTP 400 等）→ `kind="failed"`：寫入 `threads_state.json` 的 `failed[mention_id]`（終態）並把回應 body 寫 log，不回覆、不重試、不計入 `replied_ids`，也不擋 `last_since` 游標；HTTP 429／5xx／逾時 → `kind="transient"`，該筆不回覆、不標記、下輪重試，429 另依 7.10 設 `backoff_until` 並中止本輪。回覆端點（建 container／publish）的錯誤同樣依 7.10 以 HTTP 狀態碼分流。

### 7.6 發佈與 container 狀態檢查
- **主要路徑（依共識 §3，兩段式 + 狀態檢查）**：`POST /{user_id}/threads` form `{media_type:"TEXT", text, reply_to_id:{mention_id}}` 建 container → `GET /{container_id}?fields=status,error_message`，每 5 秒查一次最多 60 秒，`status=FINISHED` 才 `POST /{user_id}/threads_publish`（官方建議每分鐘一次最多 5 分鐘，文字貼文通常數秒即 FINISHED，故縮短）→ 回 media `id` 記 `reply_id`；`ERROR`／`EXPIRED` → 記 `last_error`、該 mention 標 `failed_publish`、下輪重試一次；第二次仍失敗 → 標記已處理並 log（避免每輪重跑 AI）。「container 建好但 publish 失敗」的重複發文風險以「建 container 後即先寫 state `pending_publish:{mention_id, container_id}`、下輪先嘗試 publish 同一 container」處理。
- **候選路徑（D-11，待 Day 2.5 實測後才可切換）**：`auto_publish_text:"true"` 單步發佈（Reference > Publishing；threads_verify_10 additional_findings 第 1 條只確認「文字貼文會自動發佈」，**未描述回傳的 `id` 是 container 還是 media id、reply 情境是否適用**）。Day 2.5 拿到 token 後，用機器人帳號對「機器人自己的一則貼文」以 `auto_publish_text=true` 回覆一次（不涉他人），記錄回傳 JSON 並 `GET /{id}?fields=id,permalink,text` 確認可讀且 permalink 存在（OP-5 加此項）；成立才在 D-11 決定是否切為主路徑。
- token 一律以 `access_token` 表單／查詢參數傳送（官方範例；`Authorization: Bearer` 支援未文件化，不採用）。

### 7.7 回覆模板（精確文案）

共識 §3：第 1 行燈號 + 判定 → 一句摘要（≤120 字）→ 1 個查核來源 → 結果頁連結 → 免責。連結 2 個（上限 5；2025-12-22 起超過回 `THREADS_API__LINK_LIMIT_EXCEEDED`）。品牌署名不放進回覆（由帳號名承擔以省字數；D-7 可改）。

```
{燈} {判定標籤}
{summary ≤120 字（超長於第 118 字切並補「…」），句末不補標點}
查核來源：{sources[0].url}          ← 只可放 Tier 1／2（FR-16）；verification_status=="unverified" 時本行改為「尚無查核機構證實」（唯一觸發條件；rule／verified 狀態下 sources 保證非空，5.3）
完整判讀：{PUBLIC_BASE_URL}/r/{id}
AI 自動判讀，請自行查證。
```
第一行**只有燈 + 判定標籤**（回到共識 §3 格式；v1.0 的「｜{category_label}」取消——`_validate_result` 不驗 `category` 是否在清單內，中文對照有誤標風險且多佔字數；`category_label` 只在結果頁顯示。若要保留見 D-12）。七種實例第一行：`🔴 詐騙警告`、`🔴 假訊息`、`🔴 風險訊息`、`🟡 尚待確認`（UNKNOWN／低信心 SAFE）、`🟡 尚無查核機構證實`（SAFE 但無 Tier 1／2 來源，FR-16）、`🟡 無法查證`（UNVERIFIABLE）、`🟢 查無異常`。**「查核來源」行只允許 `tier ∈ {1,2}` 的 URL**（`format_verdict_reply` 讀 `result.sources`，該清單已由 FR-16 過濾；防禦性再檢查一次 `tier`），`verification_status="unverified"` 時該行固定為「尚無查核機構證實」（9 字，不含連結，計入長度但不計連結數）。

長度規則：官方只確認「Text posts are limited to 500 characters」與「Emojis are counted as the number of UTF-8 bytes」（threads_verify_10 Claim 10），**未說明 CJK 如何計數**（CJK 在 UTF-8 也是 3 bytes）。本文件採「中文算 1」為**推論**：`threads_len(text)` = 對每個字元，若屬 Unicode 類別 `So`／`Sk` 或在 emoji 範圍（含變體選擇子 U+FE0F、ZWJ U+200D）則計 `len(ch.encode("utf-8"))`，否則計 1（v1.0 的 `4 if ord > 0xFFFF` 漏算 BMP emoji 如 ⚠ U+26A0 與 ZWJ 序列）。組回覆前先把 `summary` 內非 🔴🟡🟢 的 emoji 移除（模型偶爾輸出 ⚠️）。**實測前模板目標長度 ≤400**、硬上限 500；Day 2.5 `--live` 以「480 字純中文 + 3 emoji」對機器人自己的貼文試發一則驗證計數規則，通過後目標放寬至 ≤480（結果記入 FN-5「實測長度規則」欄）。截斷順序：先截 `summary` 至 60 字加「…」→ 再省略「查核來源」行（含「尚無查核機構證實」替代行）→ **永不**截掉結果頁連結與免責行（修正 threads_service.py:59-65 硬切 `text[:500]` 可能砍掉來源）；測試守住極端案例（4 個 emoji + 200 字 summary、含 ⚠️ 的 summary）。

固定文案（不含連結，≤120 字）：
- `reply_cannot_read`：「🟡 我讀不到這則原貼文（可能是私人帳號、或尚未加入測試名單）。請把要查證的文字複製後貼到 {PUBLIC_BASE_URL} 查證。」
- `reply_media_only`：「🟡 這則貼文只有圖片或影片，我目前只能查文字。請到 {PUBLIC_BASE_URL} 上傳圖片或貼上文字。」
- `reply_too_short`：「🟡 這則貼文的文字太短，無法判讀。請貼上完整訊息內容再 @我。」

分享文案（FR-05，Web Intent `text`，`url` 另帶）：
- `share_text_red_scam`：「🔴 AI 判定這則訊息是詐騙：{summary≤80}。查核來源：{source_domain}」
- `share_text_red_misinfo`：「🔴 AI 判定這則訊息是假訊息：{summary≤80}。查核來源：{source_domain}」
- `share_text_yellow`：「🟡 這則訊息 AI 尚無法確認：{summary≤80}。轉傳前請先查證」
- `share_text_green`：「🟢 AI 查證這則訊息沒有發現異常：{summary≤80}」
- `share_text_yellow_unverified`：「🟡 這則訊息尚無查核機構證實：{summary≤80}。轉傳前請先查證」
- 規則：`{source_domain}` 只取 Tier 1／2 來源的網域；`verification_status="unverified"` 時紅燈文案去掉「。查核來源：{source_domain}」尾段（FR-16）。

### 7.8 紅黃綠映射（單一權威，Web 與 Threads 共用）

實作於 `app/utils/verdict.py:frame_of(result) -> (frame_type, frame_label, light)`（取代 `pandas_task_processor._ai_result_to_frame` :24-34）；`_build_result`、`format_verdict_reply`、前端皆只讀 `frame_type`／`frame_label`，`format_verdict_reply` 不再自行查 `risk_type`（修正 threads_service.py:36-37 與 Web 不一致，共識 §10）。

| 條件（依序判斷） | `frame_type` | `frame_label` | 燈 | Threads 第一行 |
|------------------|-------------|--------------|----|---------------|
| `ai_unavailable` | `grey` | AI 暫時無法使用 | — | （不回覆） |
| `risk_type == UNVERIFIABLE` | `yellow` | 無法查證 | 🟡 | 🟡 無法查證 |
| `is_risk && risk_type == SCAM` | `red` | 詐騙警告 | 🔴 | 🔴 詐騙警告 |
| `is_risk && risk_type == MISINFO` | `red` | 假訊息 | 🔴 | 🔴 假訊息 |
| `is_risk`（其他） | `red` | 風險訊息 | 🔴 | 🔴 風險訊息 |
| `risk_type == SAFE && verification_status == "unverified"`（無 Tier 1／2 來源且非規則命中，FR-16） | `yellow` | 尚無查核機構證實 | 🟡 | 🟡 尚無查核機構證實 |
| `risk_type == SAFE && confidence ≥ 0.7`（且已證實） | `green` | 查無異常 | 🟢 | 🟢 查無異常 |
| 其餘（低信心 SAFE、UNKNOWN） | `yellow` | 尚待確認 | 🟡 | 🟡 尚待確認 |

本輪維持與評測一致的 `is_risk → red`，不加「低信心紅燈降黃」閘門（第 13 節 D-6，門檻集中在 `verdict.py` 一處可調）。**綠燈必須同時滿足「SAFE、信心 ≥0.7、已證實」三條件**（共識 §9 第 2 點：沒有 Tier 1／2 來源不得顯示綠燈高信心）；紅燈不受 `verified` 影響（結果頁另以橫幅提示）。`frame_of(result)` 簽名讀 `result.verification_status`（缺鍵視為 `unverified`，保守）。`tests/test_ai_service_contract.py` 的框色測試改為驗證此表 **8 列**。

### 7.9 模擬模式（`THREADS_MODE=sim`）
- Python 介面：`threads_service.py` 抽 `ThreadsClient` Protocol：`available`、`get_profile()`、`get_mentions(since, after_cursor=None)`、`get_post(media_id)`、`reply_to(media_id, text)`、`publish_text(text)`、`get_publishing_limit()`、`refresh_token()`；`ThreadsService`（live）與 `FakeThreadsService`（`app/services/threads_sim.py`）皆實作；`run_threads_poll` 只依賴 Protocol。
- `FakeThreadsService`：`get_profile()` 回檔案內 `bot`；`get_mentions(since)` 讀 `mentions.json` 並過濾 `timestamp > since`；`get_post(id)` 查 `posts`；`reply_to` 追加一行到 `data/threads_sim/replies.jsonl` 並回 `"sim_reply_{n}"`；`get_publishing_limit()` 回檔案內 `publishing_limit`。mention 物件可帶 `"_sim_error": {"on":"get_post","http":403}` 注入錯誤（以 **HTTP 狀態碼**觸發，不依賴未驗證的 `error.code`），讓測試覆蓋 7.10 分流表。fixture 的 `media_type` 值（`TEXT_POST`）為推測，Day 2.5 `--live` log 真實 mention JSON 後以實際值更正（FR-09 驗收 5）。
- `data/threads_sim/mentions.json`（鏡射 Graph API 形狀）：
  ```json
  {
    "bot": {"id": "bot001", "username": "factcheck_tw_bot"},
    "posts": {
      "p100": {"id": "p100", "username": "tester_a", "media_type": "TEXT_POST",
               "text": "健保卡即日起停用！請點 https://nhi-verify.xyz 重新驗證，逾期停卡",
               "permalink": "https://www.threads.com/@tester_a/post/p100"}
    },
    "mentions": [
      {"id": "m1", "username": "tester_b", "text": "@factcheck_tw_bot 這真的嗎",
       "media_type": "TEXT_POST", "replied_to": {"id": "p100"}, "timestamp": "2026-09-14T08:00:00+0000",
       "permalink": "https://www.threads.com/@tester_b/post/m1"}
    ],
    "publishing_limit": {"reply_quota_usage": 3, "reply_config": {"quota_total": 1000}}
  }
  ```
- `data/threads_sim/replies.jsonl` 每行 `{"ts", "mention_id", "reply_id", "result_id", "text"}`；同時寫共用 `data/threads_replies.jsonl`（`mode:"sim"`）。
- 介面：`/bot` 頁 sim 模式顯示「模擬模式」徽章、`mentions.json` 路徑提示、最近回覆列表（只讀；觸發一輪走終端機，FR-11）。
- 切換只改 `.env` `THREADS_MODE`；`live` 需 token，`sim` 不需，`off` 停用排程與 poll。`scripts/test_threads_bot.py --poll` 在 sim 模式跑一輪；`--reset-sim` 清 `replies.jsonl` 與 `replied_ids`。

### 7.10 配額護欄與錯誤碼分流

**判斷以 HTTP 狀態碼為主**；表中 `error.code` 數值（190／10／200／100／4／17／32／613）是 Facebook Graph API 通用碼的**推測**，未在 threads_gap_analysis／threads_verify_10 任何條目中核對，只作次要提示並標「待 live 核對」。所有非 2xx 回應一律以 `repr()` 把 body 原文寫 log；**任何未列入的 4xx 走保守路徑**：該 mention 標 failed + log 全文，不重試、不回覆（避免誤分流造成重複回覆或整輪停擺）。Day 2.5 `--live` 故意（a）讀一則非 Tester 貼文、（b）用壞 token 各打一次，把實際狀態碼與 `error` 物件貼回本表後才定案 FN-4 fixture。

| 情況 | 判斷 | 處理 |
|------|------|------|
| token 失效／過期 | HTTP 401（次要：`error.code == 190`，待核對） | `last_error="token_invalid"`；`backoff_until=+60 min`；`/bot` 紅色警示；不重試 |
| 權限不足／讀不到 | HTTP 403／404（次要：`error.code in (10, 200)`，待核對） | mentions 端點 → 整輪停、`last_error="permission_denied"`；讀原貼文 → 該 mention `reply_cannot_read` |
| 參數錯／未知 4xx | HTTP 400 或其他 4xx（次要：`error.code == 100`） | 該 mention 標 failed、log 全文、不回覆 |
| 限流 | HTTP 429（次要：`error.code in (4, 17, 32, 613)`，待核對） | `backoff_until = now + min(60, poll_interval × 2^n)` 分鐘，n 隨連續次數遞增、成功後歸零 |
| 連結超限 | body 含 `THREADS_API__LINK_LIMIT_EXCEEDED` | 模板保證 ≤2 連結，不應發生；發生則去掉「查核來源」行重送一次 |
| container ERROR／EXPIRED | 7.6 備援路徑 | 重試一次後放棄，記 `last_error` |
| 5xx／逾時 | — | 該筆跳過不標記，下輪重試；連續 3 輪 → `backoff_until=+15 min` |
| 回覆配額 1,000/24h | `reply_quota_usage ≥ total − 10` | 停止本輪回覆 |
| 本地上限 | `THREADS_MAX_REPLIES_PER_POLL=5`、`THREADS_MAX_REPLIES_PER_DAY=50` | 超過即停、只記錄 |
| AI 日額度（P1） | `DAILY_AI_CALL_CAP`（FR-14） | 同 `ai_unavailable`：不回覆、不標記 |

所有 Threads 相關 log 走 `logging`（不用 `print`，避免 cp950 對 emoji 崩潰——CLAUDE.md §7；回覆文字含 🔴🟡🟢，log 時以 `repr()` 或 `errors="replace"`）。

### 7.11 新增設定鍵（`config.py` + `.env.example`）
`THREADS_MODE`（`off|live|sim`，預設 `off`）、`THREADS_APP_ID`、`THREADS_APP_SECRET`、`THREADS_MAX_REPLIES_PER_POLL=5`（demo 週 `.env` 設 2）、`THREADS_MAX_REPLIES_PER_DAY=50`、`PUBLIC_BASE_URL`、`ADMIN_TOKEN`、`BRAND_NAME`、`BOT_HANDLE`（預設 `factcheck_tw_bot`）、`CONTACT_EMAIL`；FR-16：`TIER1_DOMAINS`（程式常數，不進 `.env`）；P1：`DAILY_AI_CALL_CAP=300`、`WEB_SEARCH_ALLOWED_DOMAINS`（FR-19，逗號分隔，空 = 不帶 `filters`）；P2：`ENABLE_DAILY_POST=false`。`.env.example` 的 AI 段只留 `AI_PROVIDER=cgu`、`CGU_API_KEY`／`CGU_BASE_URL`／`CGU_MODEL`、`EMBED_*`、`USE_WEB_SEARCH`、`OPENAI_REASONING_EFFORT`；myai168 的 `MYAI_API_KEY`／`OPENAI_RELAY_URL`／`CLAUDE_RELAY_URL`／`OPENAI_MODEL`／`CLAUDE_MODEL` 移到「已停用（保留 provider 程式供日後切回）」註解區（共識 §4；`.env` 本身已清）。`.env.example` 補列既有但漏掉的 `THREADS_BASE_URL`；移除 `ENABLE_THREADS_BOT`（相容讀取）、`SERPER_API_KEY`、`GOOGLE_API_KEY`／`EMBEDDING_MODEL`、`STT_MODEL`／`CGU_STT_MODEL`／`CRAWL_WITH_SCREENSHOT`／`SEARCH_RESULTS_LIMIT`（FR-15）。

---

## 8. UX 規格

### 8.1 設計原則與 token 方向（共識 §5）
- **淺色預設、黑白為底、單一強調色**；紅黃綠**只**用於判定燈號、chip 與結果卡邊條，導覽、按鈕、裝飾一律不得用這三色。
- 手機優先（U1 來自 Threads 內建瀏覽器）：單欄、內容最大寬 640 px、觸控目標 ≥44 px、底部安全區留白；桌機只是把單欄放寬並把底部分頁列移到頂部。
- 不加 UI 套件；React 19 + Vite + Tailwind v4；`react-router-dom` 視為路由基礎設施（`/r/{id}` 必須有路由），是唯一新增依賴——共識 §5 只說「不加 UI 套件」，此為解釋，列入 D-13 請負責人一鍵確認。現況 `package.json:29,32` 釘 `vite ^8.0.0-beta.13`（含 `overrides`）且 CI 從未 build 過：Day 1 本機 `npm run build` 一次，失敗即降回 Vite 7 穩定版並移除 `overrides`（D-13）。
- 深淺色切換保留：`localStorage` key `fcc_theme`，首訪依 `prefers-color-scheme`（不再強制深色）；dark 於 `:root[data-theme="dark"]` 覆蓋。
- 字型：系統中文字體堆疊 `"Noto Sans TC", "PingFang TC", "Microsoft JhengHei", system-ui, sans-serif`，不載入外部字型（離線與速度）。
- Token（`index.css`，全部改名以斷開舊青綠系；數值為起點，mockup 定案）：
  - `--c-bg` #FFFFFF／dark #0F1115；`--c-surface` #FAFAFA／#171A21；`--c-ink` #111111／#F3F4F6；`--c-ink-2` #6B7280／#9CA3AF；`--c-ink-3`（更淡）；`--c-line` #E5E7EB／#2A2F3A
  - `--c-accent` 單一色，建議 #2F4BFF（深靛藍，與紅黃綠皆可區分）；`--c-accent-ink` #FFFFFF；`--c-accent-soft`（焦點環／選中分頁底）
  - `--c-verdict-red` #D92D20、`--c-verdict-yellow` #B54708（文字）、`--c-verdict-green` #067647、`--c-verdict-grey` #6B7280；各有 `-soft` 底色（黃 #FEF0C7）；深色底改用較亮文字色（red #F97066、yellow #FDB022、green #32D583），底色保持深色低飽和
  - `--c-neutral-chip`（PENDING／UNVERIFIABLE／快取 chip）；`--radius-card` 12px、`--radius-chip` 999px；`--shadow-card`（淺色極淡、深色無）
- 動效：只有結果載入 shimmer、結果卡 fade-in（≤200 ms）、分享按鈕文字切換；`prefers-reduced-motion` 全部關閉。
- 圖示：幾何記號／文字（✕ ! ✓ ?）；燈號 emoji 🔴🟡🟢 **只**在 Threads 回覆與分享文案使用（共識 §3 指定）；介面內燈號用實心圓點 `●` + 文字，不靠顏色單獨傳達。

### 8.2 資訊架構與導覽
```
/            首頁（輸入 + 最近查證 5 筆）        ┐
/r/:id       結果頁（獨立可分享）                │ 主要（底部分頁列）
/trending    熱門牆                              │
/knowledge   知識庫搜尋                          ┘
/bot         機器人狀態（U5；最小只讀版 P0）
/oauth/callback                                   SPA 靜態頁（token 取得用）
/privacy.html  /data-deletion.html  /deauthorize.html   純 HTML（public/，Meta 後台填這三個）
/history     我的紀錄（localStorage 全頁，P2，本次不做）
```
- 手機（<768 px）：底部固定分頁列 **3 格**「查證／熱門／知識庫」（v1.0 的「紀錄」格隨 `/history` 降 P2 移除；最近 5 筆在首頁），各 44 px 高、`env(safe-area-inset-bottom)` 內；當前分頁以強調色文字 + 上緣 2 px 線表示。`/bot`、隱私頁從頁尾進入。
- 桌機：頂欄品牌名（連回 `/`）+ 同 3 個分頁 + 「機器人」+ 右側主題切換（文字按鈕「深色／淺色」，非 emoji）；內容區 `max-width: 640px` 置中。
- 所有頁尾：「隱私政策 · 資料刪除 · 本站判讀由 AI 產生，僅供參考」。
- Vercel `vercel.json`：`rewrites: [{source:"/api/(.*)", destination:"{TUNNEL_URL}/api/$1"}, {source:"/((?!.*\\.html$).*)", destination:"/index.html"}]`——API 由 Vercel 同源代理到後端 tunnel（D-5 方案 b：免 CORS、前端只打相對路徑 `/api`、tunnel 網址變時只改這一行重新部署）；`*.html` 靜態頁不 rewrite。`VITE_API_BASE_URL` 留空＝同源（本機 dev 仍走 vite proxy → 8000）。

### 8.3 畫面規格（元件清單 + 所有狀態）

#### S1 首頁 `/`
元件：
1. 標題區：`home_tagline` + `home_sub`。
2. 輸入卡：模式切換 tab（文字／網址／圖片，`role="tablist"`）；`textarea`（自動長高，最小 4 行，右下字數 `{n}/20000`）；網址模式 `<input type="url" inputmode="url">`；圖片模式為虛線上傳區（點擊或拖曳，`<input type=file accept="image/png,image/jpeg,image/webp">` 以 `sr-only` 而非 `display:none`，可鍵盤觸發）+ 預覽縮圖 + 移除鈕；主按鈕「開始查證」（全寬、`--c-accent`）；副文字 `analyze_note`。
3. Threads 使用說明卡：`bot_howto` + 開發模式一句。
4. 最近查證列表：localStorage 最近 5 筆（燈號點 + preview + 相對時間 + 「查看」→ `/r/{id}`）+ 「清除」（二次確認）；「全部紀錄」→ `/history` 為 P2、本次不放。

狀態：
- **空**：無歷史 → 顯示 3 個範例 chip（`example_1..3`，點擊填入輸入框、不自動送出）+ `history_empty`。
- **輸入驗證失敗**：inline 紅字（非 alert）：`err_empty`、`err_too_long`、`err_invalid_url`、`err_image_type`、`err_image_size`；主按鈕維持可按。
- **送出中**：主按鈕 disabled + spinner「查證中…」；`aria-live="polite"` 宣告；成功建立任務後 ≤500 ms 導向 `/r/{id}`。
- **速率限制／額度用完**（429）：inline `err_rate`（帶秒數）或卡片 `quota_exceeded_*`。
- **後端不可用**：頂部橫幅 `backend_down`。
- **快取命中／AI 不可用／UNVERIFIABLE／錯誤／分享後**：皆在 S2 呈現（首頁不再內嵌結果卡）。

#### S2 結果頁 `/r/{id}`
元件（由上而下，手機單欄）：
1. 返回鍵；燈號區塊（全寬）：實心圓點 + `frame_label`（24 px 粗體、h1）+ `category_label`（次級）；右側信心 chip「信心 高／中／低」（點擊展開 `confidence_note`）；快取 chip（`chip_cache_*`，點擊展開 `cache_hint`）或 `chip_live`。
2. 「你查的內容」摘錄卡：`input_preview`（≤200 字、可展開）；`platform_post` 有值時顯示 `from_threads` + 外連原貼文。
3. 判讀摘要 `summary`（粗體一句）+ 詳細說明 `explanation`（可折疊）。
4. 查核來源：清單，**只列 Tier 1／2**（FR-16），每項標題 + 網域 + `tier_label` chip（`tier_1_chip`「查核機構」／`tier_2_chip`「媒體查核報導」，中性色）+ 外連圖示（`rel="noopener"`）；`verification_status="unverified"` 時（此時 `sources` 必為空，5.3；`rule`／`verified` 狀態保證非空）顯示 `sources_empty`（逐字「尚無查核機構證實這則訊息，請自行查證。」）並於本區上方另有 `no_verified_source_title/body` 橫幅（黃色 `-soft` 底、「!」記號、位置在燈號區之下、摘要之上，所有燈色皆顯示）。Tier 3 `related_discussions` **不顯示**（P2 才加折疊區）。
5. 知識庫中的相似查證 `similar_news`（向量近鄰最多 3 筆，FR-02；每筆 `raw_content` 前 60 字 + 燈號點 + 相似度 + 有 `last_result_id` 時內連 `/r/{id}`；可折疊；快取命中時隱藏）。**v1.2：降 P1，本次 `similar_news=[]` 時整區隱藏**（元件保留在設計，不實作資料來源）。
6. 動作列（手機 sticky 於視窗底部、分頁列之上；桌機回到燈號區下方）：「分享到 Threads」（主）、「複製連結」（次）、「再查一則」（→ `/`）。
7. 頁尾細字：`analyzed_at`、`label_source` 說明、`disclaimer_short`。

狀態：
1. **載入**（`pending/processing`）：骨架 3 段 + 三步指示「檢查快取 → 讀取內容 → AI 判讀」（時間動畫 2 秒/步，**只前進、不循環**：走到「AI 判讀」後停在那裡直到結果出來；2026-09-19 負責人實機看到舊版走到第三步又跳回第一步後要求修改）+ `result_loading`；輪詢每 2 秒、最多 90 秒；`aria-busy`。
2. **超時**（>90 秒仍未完成）：`error_timeout` + 「重新整理」；停止自動輪詢；`task_id` 仍在 URL，重開即續（修正 App.jsx:426 永遠停在骨架的 bug）。
3. **成功（未快取）**：燈號區依 7.8 上色；chip `chip_live`。
4. **快取命中**：chip `chip_cache_url|hash|vector` + `cache_hint`；`similar_news` 區隱藏。
5. **AI 不可用 fallback**（`ai_unavailable`）：灰框、圖示「!」、`ai_unavailable_title/body`、按鈕「重新查證」（重送同一輸入、產生新 id）；分享／複製隱藏。
6. **失敗**（`status=failed`）：`error_title` + `error_server`（帶 `code`）+ 「重新查證」。
7. **UNVERIFIABLE**：黃框「無法查證」+ `unverifiable_body`（`source_url` 為 threads 網域時加 `unverifiable_threads_hint`）；仍有分享（`share_text_yellow`）。
8. **分享後**：分享鈕文字 3 秒內「已開啟 Threads」+ toast `toast_share`；複製鈕「已複製」。
9. **404**：`result_not_found_title/body` + 「回首頁」。
10. **未經證實**（`verification_status="unverified"`，FR-16）：與狀態 3／4 疊加——`no_verified_source_*` 橫幅 + 來源區 `sources_empty`；SAFE 時燈號區為黃「尚無查核機構證實」（7.8），紅燈時維持紅但橫幅照顯示；分享文案用 `share_text_yellow_unverified`（黃）或去尾段的紅文案。**例外（5.3）**：`risk_type=UNVERIFIABLE`（狀態 7）與 `ai_unavailable`（狀態 5）雖然 `verification_status` 亦為 `unverified`，**不顯示** `no_verified_source_*` 橫幅、來源區整區隱藏（狀態 7 只顯示 `unverifiable_body`，狀態 5 只顯示 `ai_unavailable_*`），避免「讀不到內容」與「找不到查核來源」兩種語意同時出現。

#### S3 熱門牆 `/trending`
元件：標題 `trending_title` + `trending_sub`（讀 `/health.scheduler.{enabled,interval_hours}` 顯示 `scheduler_on/off`，5.1）+ `trending_updated`；篩選 chip（全部／詐騙／假訊息／安全／未查證）；卡片列表（燈號點 + 標題 ≤2 行 + 機構 + 日期 + `label_source` 小字）；卡片點擊：有 `result_id` → `/r/{id}`，否則外連 `source_url`。
狀態：**載入**（6 張骨架）／**空** `trending_empty`／**篩選無結果** `filter_empty`／**錯誤** `backend_down` + 重試；PENDING／UNVERIFIABLE **或 `verified=false`** 顯示灰色 `chip_pending`、不上紅黃綠（FR-06 驗收 6）；卡片來源機構只可能是 MyGoPen／TFC／Cofacts／解析後的真實媒體網域，不得出現 `news.google.com`。

#### S4 知識庫 `/knowledge`
元件：搜尋列（`type=search`，送出鈕）；統計列 `knowledge_stats` + 副文字 `knowledge_verified_note`；篩選 chip（詐騙／假訊息／安全／無法查證）；結果卡（燈號點 + `raw_content` ≤3 行 + `summary` ≤2 行 + `hit_count` + `label_source` chip + 第一個 Tier 1／2 來源網域）；「載入更多」（offset 分頁，每次 30）。資料只含 `verified=true` 列（FR-17）。
狀態：**載入**／**空（無資料）** `knowledge_empty`／**空（搜尋無結果）** `knowledge_no_match`／**載入更多中**／**已到底** `knowledge_end`／**錯誤**。

#### S5 我的紀錄 `/history`（P2，本次不做；spec 保留）
元件：`history_sub`；列表（燈號點 + preview + 相對時間 + 「查看」）；「清除全部」（二次確認 dialog、focus trap）。
狀態：**空** `history_empty`／**localStorage 不可用** `history_unavailable`／**列表**。

#### S6 機器人狀態 `/bot`（最小只讀版 P0）
元件（P0）：模式徽章（live「開發模式（僅 Threads 測試者）」／sim「模擬模式」／off「已停用」）；狀態卡（`threads_last_poll`、`last_error`）；`dev_mode_notice` 說明框；最近回覆列表（燈號點 + 原貼文摘要 + 回覆全文可展開 + 「原貼文」外連 + 「結果頁」內連）；每 2 秒重讀 `status`。P1（報告後）：`threads_token_days`／`threads_token_warn`、`threads_daily`、「執行一輪」按鈕、知識庫未證實筆數 `knowledge_unverified`「知識庫未證實 {unverified_count} 筆」（讀 `GET /api/knowledge/stats.unverified_count`，5.1）。
狀態（P0）：**未啟用** `threads_off`／**模擬模式**（徽章 + `mentions.json` 路徑提示）／**運作中**／**last_error**（紅色）／**載入**／**錯誤**。P1：**token 即將到期**／**執行中**。

#### S7 靜態頁 `/privacy.html`、`/data-deletion.html`、`/deauthorize.html`（純 HTML）與 `/oauth/callback`（SPA）
純文字排版（h1 + 段落 + 清單），最大寬 640 px；三個純 HTML 頁內嵌同一組 token 的最小 CSS（不載 Tailwind），文案取 8.7；`/oauth/callback` 讀 `?code=` 顯示於 `<code>` + 複製鈕 + `oauth_cb_body`。

### 8.4 狀態總表（供介面測試 3.3 逐格勾）

| 畫面 | 空 | 載入 | 成功 | 快取命中 | AI 不可用 | 錯誤 | UNVERIFIABLE | 未經證實（FR-16） | 分享後 |
|------|----|------|------|----------|-----------|------|--------------|------------------|--------|
| S1 首頁 | ✓範例 chip | ✓送出中 | （導向 S2） | — | — | ✓inline／橫幅／429 | — | — | — |
| S2 結果頁 | 404 版 | ✓骨架＋超時 | ✓ | ✓chip | ✓灰卡 | ✓重試 | ✓黃框 | ✓橫幅＋黃（SAFE）／紅＋橫幅 | ✓ |
| S3 熱門牆 | ✓ | ✓ | ✓ | — | — | ✓ | 「未查證」chip | 「未查證」chip（`verified=false`） | — |
| S4 知識庫 | ✓兩種 | ✓＋載入更多 | ✓ | — | — | ✓ | 篩選項 | （不出現；`verified=false` 列已濾除） | — |
| S5 紀錄（P2，不列入本次介面測試） | ✓ | — | ✓ | — | — | 不可用版 | — | — | — |
| S6 機器人（P0 只讀版） | 未啟用版 | ✓ | ✓（live／sim） | — | — | ✓last_error | — | — | — |

P0 畫面 = S1、S2、S3、S4、S6（只讀版）；UI-1 截圖檢核表以此表為母版（10.3）。

### 8.5 手機優先版面說明（無像素圖，以順序與比例描述）
- 單欄、內距一個手指寬；卡片之間留一格空白；所有互動元素高度 ≥44 px。
- 首頁：頂欄 → 標題 → 輸入卡（tab 在卡內頂部，textarea 4–6 行，送出鈕全寬緊貼其下、首屏內）→ Threads 說明卡 → 最近查證。
- 結果頁：頂欄「← 返回」→ 燈號區塊貼頂（佔首屏上三分之一）→ 摘要 → 說明（折疊）→ 來源 → 相關查核 → 頁尾；動作列 sticky 於底部，內容底部預留 padding 不被遮。
- 分頁列固定底部（安全區內）。橫向溢出：長網址 `word-break: break-all`；表格與程式碼區塊 `overflow-x:auto`；頁面本體永不橫向捲動。
- 桌機（≥768 px）：頂欄取代底部分頁列；內容欄仍 640 px；動作列改為卡片內一般按鈕、不 sticky。

### 8.6 可及性最低要求
- `<html lang="zh-Hant">`；每頁唯一 `<h1>`；分頁列 `nav` + `aria-current="page"`。
- 文字對比 ≥4.5:1（黃色文字用 #B54708 深色，不用亮黃）；燈號一律「顏色 + 文字 + 圓點」不靠色。
- 鍵盤可達：模式 tab（`role="tab"`／`aria-selected`、方向鍵切換）、上傳區用可聚焦 `<label>` + 視覺隱藏 input（Enter 可開檔案選擇）、對話框 focus trap、`:focus-visible` 強調色焦點環。
- 動態內容 `aria-live="polite"`（查證開始／完成／錯誤）；載入骨架 `aria-busy`。
- 觸控裝置不依賴 hover／`title`：信心與快取說明以點擊展開。
- 全部按鈕有可讀文字（主題切換 `aria-label="切換深淺色"`）；字級最小 13 px（chip）、正文 15–16 px（現行 10–11 px 全部移除）；`prefers-reduced-motion` 尊重。

### 8.7 繁中文案表（所有使用者可見文字；逐字）

| key | 文案 |
|-----|------|
| `home_tagline` | 貼上訊息，10 秒知道真假 |
| `home_sub` | AI 判定詐騙／假訊息、尚待確認或查無異常，並附上查核來源。 |
| `tab_text` / `tab_url` / `tab_image` | 文字／網址／圖片 |
| `input_placeholder_text` | 貼上 LINE、Threads 或任何地方看到的訊息… |
| `input_placeholder_url` | https://… 貼上新聞或貼文網址 |
| `upload_hint` | 點擊或拖曳圖片到這裡（PNG／JPG／WEBP，10 MB 以內） |
| `btn_analyze` / `btn_analyzing` | 開始查證／查證中… |
| `analyze_note` | 查證約需 5–20 秒；查過的內容會直接命中快取。 |
| `example_1` | 健保卡即日起停用，請點連結重新驗證 |
| `example_2` | 網傳吃香蕉配優格會中毒 |
| `example_3` | 165 反詐騙專線提醒：遇到「保證獲利」請掛斷 |
| `err_empty` | 請先貼上要查證的內容。 |
| `err_too_long` | 內容超過 20,000 字，請刪減後再試。 |
| `err_invalid_url` | 這不是有效的網址，請以 http:// 或 https:// 開頭。 |
| `err_blocked_url` | 這個網址無法查證（內部或保留位址）。 |
| `err_image_type` | 只支援 PNG、JPG、WEBP 圖片。 |
| `err_image_size` | 圖片超過 10 MB，請壓縮後再上傳。 |
| `err_rate` | 查證太頻繁，請 {n} 秒後再試。 |
| `backend_down` | 暫時連不上伺服器，請確認網路或稍後再試。 |
| `result_loading` | AI 正在查證，通常 5–20 秒 |
| `result_step_1` / `_2` / `_3` | 檢查快取／讀取內容／AI 判讀 |
| `error_timeout` | 處理時間比預期久，你可以稍後再打開這個連結。 |
| `chip_live` | AI 即時判定 |
| `chip_cache_url` / `_hash` / `_vector` | 快取命中・相同網址／快取命中・相同內容／快取命中・語意相似 |
| `cache_hint` | 這筆內容先前已查證過，系統直接沿用結果，沒有再次呼叫 AI。 |
| `frame_red_scam` / `frame_red_misinfo` / `frame_red_other` | 詐騙警告／假訊息／風險訊息 |
| `frame_yellow` / `frame_yellow_unverifiable` | 尚待確認／無法查證 |
| `frame_green` | 查無異常 |
| `frame_grey` | AI 暫時無法使用 |
| `confidence_chip` | 信心 {高\|中\|低} |
| `confidence_note` | 模型自評信心，未經機率校準（實際效能請參考評測報告） |
| `section_input` / `section_summary` / `section_explanation` / `section_sources` / `section_similar` | 你查的內容／判讀摘要／詳細說明／查核來源／知識庫中的相似查證 |
| `similar_item` | 相似度 {pct}%・{frame_label} |
| `sources_empty` | 尚無查核機構證實這則訊息，請自行查證。 |
| `tier_1_chip` / `tier_2_chip` | 查核機構／媒體查核報導 |
| `no_verified_source_title` | 尚無查核機構證實 |
| `no_verified_source_body` | 目前找不到已對這則訊息做出判定的查核機構或媒體查核報導，以上為 AI 的初步判讀。轉傳前請先到台灣事實查核中心、MyGoPen 或 Cofacts 查證。 |
| `frame_yellow_no_source` | 尚無查核機構證實（7.8 新列；與 `frame_yellow_unverifiable`「無法查證」不同：後者是讀不到內容，前者是讀得到但找不到已判定的查核來源） |
| `ai_unavailable_title` | AI 服務暫時無法使用 |
| `ai_unavailable_body` | 可能是額度用盡或連線問題，這次沒有產生判定。你可以稍後再試，或先到知識庫搜尋是否已有人查過。 |
| `quota_exceeded_title` | 今日查證額度已用完 |
| `quota_exceeded_body` | 為控制成本，每天的 AI 查證次數有上限。已查過的內容仍可直接命中快取；明天再試或到知識庫搜尋。 |
| `unverifiable_body` | 系統抓不到這個網址的內容，或內容太少無法判讀。請改貼文字內容再試一次。 |
| `unverifiable_threads_hint` | Threads 貼文網址目前無法直接讀取，請複製貼文文字後貼上查證。 |
| `error_title` | 出了點問題 |
| `error_network` | 連不上伺服器，請檢查網路後重試。 |
| `error_server` | 伺服器發生錯誤（{code}），請稍後再試。 |
| `btn_retry` / `btn_reanalyze` | 重試／重新查證 |
| `btn_share_threads` / `btn_share_opened` | 分享到 Threads／已開啟 Threads |
| `btn_copy_link` / `btn_copied` | 複製連結／已複製 |
| `btn_check_another` | 再查一則 |
| `toast_share` | 已開啟 Threads，發佈前可自行修改文字 |
| `result_not_found_title` / `_body` | 找不到這筆查證／連結可能已過期或輸入錯誤。你可以回首頁重新查證。 |
| `btn_home` | 回首頁 |
| `from_threads` | 來自 Threads @{username} |
| `label_source_ai` / `_rule` / `_gold` / `_admin` | AI 判定／查核機構標記／評測標註／人工覆寫 |
| `analyzed_at` | 查證時間 {datetime} |
| `disclaimer_short` | 判讀由 AI 自動產生，僅供參考，請自行查證。 |
| `trending_title` / `trending_sub` | 今日熱門查核／來源：MyGoPen、台灣事實查核中心、Cofacts。{scheduler_state} |
| `scheduler_on` / `scheduler_off` | 每 {n} 小時自動更新／目前為手動更新 |
| `trending_updated` | 資料更新時間：{time} |
| `trending_empty` / `filter_empty` | 還沒有熱門查核資料。／這個分類目前沒有資料。 |
| `chip_pending` | 未查證 |
| `knowledge_title` / `knowledge_sub` | 查證知識庫／所有查證過的內容都在這裡，重複的訊息不必再問 AI。 |
| `knowledge_search_placeholder` | 搜尋關鍵字… |
| `knowledge_stats` | 共 {total} 筆・詐騙 {scam}・假訊息 {misinfo}・安全 {safe}・無法查證 {unv}（只計 `verified=true`，FR-17） |
| `knowledge_verified_note` | 知識庫只收錄有查核機構或媒體查核報導佐證的判定。 |
| `knowledge_empty` / `knowledge_no_match` | 知識庫是空的。／找不到符合「{q}」的資料，試試其他關鍵字，或直接貼到首頁查證。 |
| `hit_count` | 命中 {n} 次 |
| `btn_load_more` / `knowledge_end` | 載入更多／已顯示全部 {total} 筆 |
| `history_title` / `history_sub` | 我的紀錄／紀錄只保存在這個瀏覽器，不需登入，也不會上傳。 |
| `history_empty` | 還沒有查證紀錄。到首頁查一則試試。 |
| `history_unavailable` | 這個瀏覽器無法保存紀錄（可能是無痕模式）。 |
| `btn_clear_history` / `confirm_clear` | 清除全部／確定要清除這台裝置上的所有紀錄嗎？此動作無法復原。 |
| `bot_howto` | 在 Threads 回覆可疑貼文並 @{BOT_HANDLE}，機器人會在 {n} 分鐘內回覆判定與來源。 |
| `threads_title` | Threads 查核機器人 |
| `threads_mode_live` / `_sim` / `_off` / `_invalid` | 開發模式（僅 Threads 測試者）／模擬模式／已停用／token 失效 |
| `threads_off` | 機器人尚未啟用。設定 THREADS_MODE 與 token 後重新啟動後端。 |
| `threads_last_poll` | 上次輪詢 {time}：檢查 {checked}、回覆 {replied}、略過 {skipped}、錯誤 {errors} |
| `threads_token_days` / `threads_token_warn` | token 剩餘 {n} 天／Threads 授權將於 {n} 天後到期，請執行續期。 |
| `threads_daily` | 今日回覆 {n}／{cap}；Threads 配額 {usage}／{limit} |
| `dev_mode_notice` | 目前為開發模式：只有被加入為測試人員的 Threads 帳號 @{BOT_HANDLE} 才會收到回覆。公開服務需通過 Meta App Review 與企業驗證，為本專題論文所述之上線條件。 |
| `btn_run_poll` | 執行一輪 |
| `threads_replies_title` / `threads_replies_empty` | 最近回覆／還沒有回覆紀錄。 |
| `btn_view_post` / `btn_view_result` | 原貼文／結果頁 |
| `theme_dark` / `theme_light` | 深色／淺色 |
| `nav_home` / `nav_trending` / `nav_knowledge` / `nav_bot` | 查證／熱門／知識庫／機器人（`nav_history`「紀錄」隨 `/history` 降 P2 保留 key、本次不顯示） |
| `deauthorize_title` / `deauthorize_body` | 取消授權／本服務不保存授權狀態，取消授權後不需額外處理。 |
| `footer` | 隱私政策 · 資料刪除 · 本站判讀由 AI 產生，僅供參考 |
| `privacy_title` | 隱私政策 |
| `privacy_collect` | 我們蒐集：你貼上的文字、網址或圖片；在 Threads 上 @機器人 時被回覆的公開貼文文字與貼文連結；AI 判定結果。這些內容會儲存在查證知識庫，供後續相同或相似內容快速比對。 |
| `privacy_not` | 我們不蒐集：帳號、密碼、Cookie 追蹤；「我的紀錄」只存在你的瀏覽器。 |
| `privacy_ai` | 判讀由 AI 自動產生，可能有誤，不構成任何法律或專業建議。使用本站即表示你了解並同意上述條款。 |
| `deletion_title` | 資料刪除說明 |
| `deletion_body` | 若你希望刪除某筆查證或被引用的 Threads 貼文文字，請來信 {CONTACT_EMAIL}，附上結果頁連結（/r/…）或 Threads 貼文連結，我們會在 7 日內刪除並回覆。 |
| `oauth_cb_title` / `oauth_cb_body` | 授權完成／請複製下方代碼，回到終端機貼上以完成 token 取得。 |
| `page_title_suffix` | ｜{BRAND} |

Threads 回覆與分享專用文案見 7.7。

---

## 9. 非功能需求

| 類別 | 需求 | 量測 |
|------|------|------|
| 效能 | 文字 L1 命中 p50 <1.5 s；L2 命中 p50 <4 s（含一次 embedding）；快取命中（任一層）p95 ≤6 s；未命中 AI（web_search 關）p50 ≤15 s、p90 <20 s；（開）p90 <35 s；網址（含爬取）p95 ≤60 s；結果頁 API p50 <300 ms；前端首屏 LCP <2.5 s。**FR-16 Cofacts GraphQL 查詢時間（並行、總逾時 5 s、程序內 LRU）另計**，log 分開記 `tier_ms`，不計入上列 AI 數字 | 依共識 §7 由 `evaluate.py` 承擔（不新增 `bench.py`）：`evaluate.py --timing` 每筆輸出 `elapsed_ms`；快取層時間以後端每筆結構化 log 的 `elapsed_ms + cache_layer` 人工彙整（可觀測列）；結果頁 API 用 `curl` 迴圈 50 次；首屏用 Lighthouse 行動版預設節流（Slow 4G）LCP |
| 成本 | 每次未命中查證 ≤ USD 0.02（CGU AIR `gpt-5.4-mini`、`OPENAI_REASONING_EFFORT=low`，web_search 由 `USE_WEB_SEARCH` 控制；參考：2026-07 三輪批次查證共 USD 0.127，CLAUDE.md §8）；demo 週護欄 = CGU `GET /me/usage` 每日查一次 + `USE_WEB_SEARCH`（FR-14 demo 週段；程式護欄為 P1）；demo 週總花費 ≤ USD 5（共識 §4：CGU OpenAI 成本額度 USD 10，**不買 OpenAI 直連額度**）；`gpt-5.4` 只作績效測試比較組（可選、≤ USD 2） | Day 0 `test_ai_provider.py --provider cgu` 前後 `/me/usage` 差為第一筆數據；每次評測前後 `/me/usage` 記入 `docs/test/cgu_usage.txt`；P1 後加 `data/ai_usage.jsonl` |
| 隱私 | 不存 IP；只存文字與判定；Threads 只存公開貼文的 `post_id`／`username`／`permalink`；fallback 不回傳上游錯誤原文；`/api/knowledge` 只回 `raw_content` 前 500 字；log 不含 token | code review + `grep` token 不出現在 log |
| 安全：SSRF | `crawler.crawl_url` 與 `url_validator._is_url_alive` 統一走 `app/utils/safe_url.py`：僅 http/https；DNS 解析後所有 A/AAAA 皆非 loopback/private/link-local/multicast/reserved；port 僅 80/443；重導向 ≤3 次且每跳重檢；連線逾時 10 s、總逾時 `CRAWLER_TIMEOUT`（預設 30 s，與 FR-02 驗收 3 同一組）；回應 ≤2 MB | `tests/test_safe_url.py`（新增） |
| 安全：授權 | 5.6；`ADMIN_TOKEN` ≥32 字亂數（`start.bat` 首次自動產生）；缺 → 401、空設定 → 403 | `tests/test_api.py` 加案例 |
| 安全：速率 | **2026-09-19 已實作**（後端上雲公開前）：`app/utils/rate_limit.py` 每 IP 滑動視窗，`RATE_LIMIT_PER_MINUTE=30`、`RATE_LIMIT_PER_HOUR=200`（0 = 關閉；預設寬鬆，因為同一間教室對外是同一個 IP），套用在 `POST /api/analyze/*` 與 `POST /api/feedback/*`（各自計數），超過回 429 `rate_limited` + `Retry-After` 秒數；被擋下的請求不計入視窗。用戶端 IP 取 `X-Forwarded-For` 最左邊（IPv6 以 /64 為單位）。行程內記憶體、重啟歸零（守預算的是 FR-14 每日上限）。另有請求大小上限 `app/utils/body_limit.py`：一般 1 MB、圖片 10 MB，超過回 413 `payload_too_large` | `tests/test_rate_limit.py`、`tests/test_launch_guards.py` |
| 安全：輸入 | 圖片 magic bytes 與 10 MB（2026-09-19 已實作：415 `unsupported_media`／413 `payload_too_large`，存檔副檔名取自檔頭而非使用者檔名）；URL 驗證 | FN-2、`tests/test_launch_guards.py` |
| 安全：CORS | 正式環境 API 經 Vercel rewrites 同源代理（8.2），瀏覽器不跨域；`CORS_ORIGINS` 只需 `localhost:5173` + Vercel 網址（保險）；`allow_credentials=False`（無 cookie）；`cors_origins_list` 過濾空字串 | 手動 |
| 可靠性 | 機器人單實例：`asyncio.Lock` + 檔案鎖 + uvicorn 單 worker；state 原子寫入、每則後寫；backoff；重複回覆率 0；啟動 reaper（P1）；Cloudflare Tunnel 斷線時前端顯示 `backend_down` 而非空白；**tunnel 單請求 ≤100 s**（Cloudflare 邊緣逾時回 524）——所有經 tunnel 的端點必須在 100 s 內回應，長工作一律非同步（`/api/threads/poll` 202、查證走 `/r/{id}` 輪詢） | FN-4、手動拔網 |
| 可靠性 | AI provider 備援鏈程式保留（共識 §4）；未設 key 的 provider 不進鏈（ai_service.py:118-122）——**現況 `.env` 只設 CGU，鏈為 `['cgu']`**（myai168／Gemini 6 個 key 已刪，不再有「打了也會失敗的備援」）；每 provider timeout 150 s 降為 **60 s** | `.env`、單元測試 |
| 資料品質 | 對外顯示的查核來源 100% 為 Tier 1／2；知識庫頁 0 筆 `verified=false`；熱門牆 0 筆 Google News 轉址；SAFE 且未證實者 0 筆綠燈（FR-16～18） | OP-9 清洗前後 `check_db.py` 比對；FN-12～14；UI-1 抽查 S2／S3／S4 截圖 |
| 可觀測 | `logging` 取代 `print`（cp950 安全）；每次查證一行結構化 log（`result_id, origin, cache_layer, provider, ms, usd`） | log 抽查 |
| 可維護 | CI：`pytest` + `npm ci && npm run build`（Day 1 上）；`ci.yml` 移除測試數字註解 | GitHub Actions |
| 相容 | Python 3.11–3.13；Node 20；iOS Safari 16+／Android Chrome 110+（Threads 內建瀏覽器） | 手機實測兩台 |
| 部署 | 前端 Vercel；後端負責人電腦 + Cloudflare **quick tunnel**（`cloudflared tunnel --url http://localhost:8000`，免費、免網域、免帳號；網址為隨機 `*.trycloudflare.com`，**重啟會變**）。具名 tunnel 需在 Cloudflare 託管一個自有網域才能綁固定主機名（v1.0「具名 tunnel 免費且網址固定」與 D-5「不買網域」互斥，已更正）。網址變動的影響被 8.2 的 Vercel rewrites 隔離：`PUBLIC_BASE_URL`（分享連結、Threads 回覆連結、Meta redirect URI、隱私頁）永遠是 Vercel 網址；tunnel 重啟後只改 `vercel.json` 一行重新部署（<2 分鐘）。`start.bat` 加啟動 tunnel 選項並印出網址。替代方案見 D-5 | 手動 |

---

## 10. 測試通過準則（對應 TP-FNV-2026-01 §3.1–3.5、§4.2、§4.3）

每條皆可量測；**每張表加「優先級」欄**，P0／P1 以測試條目為單位（不再只標在 FR 上）。「通過」= 全部 P0 條目達標、P1 條目 ≥80%；任一 P0 條目不達標 → 測試中止（計畫書 4.3）；**再繼續的條件**：該 P0 條目修復並重跑通過，且回歸 `pytest tests` 全綠、`npm run build` 成功。

### 10.1 操作測試（3.1，操作者 U5）
| ID | 優先級 | 步驟 | 通過準則 |
|----|--------|------|----------|
| OP-1 | P0 | 全新 clone → `start.bat` | 後端 `/health` 200 且 `ai_available=true`；前端 5173 開啟首頁；<5 分鐘（含 pip/npm）；`.env` 已自動產生 ≥32 字 `ADMIN_TOKEN`，`curl -X POST -H "X-Admin-Token: …" /api/threads/poll` 回 202 或 200 `threads_disabled`；**`GET /api/knowledge/stats.total ≥ 150`**（證明提交的種子是 FR-18 清洗後版本，`verified` 已回填；在 OP-9 之後執行） |
| OP-2 | P0 | `scripts/test_ai_provider.py --provider cgu`（關／`--web-search` 開／`--web-search --allowed-domains` 各跑一次；前後各查一次 `GET {CGU_BASE_URL}/me/usage`） | **P0 條件（只有這一項擋交付）**：關閉 web_search 的一次印出合法 `risk_type`、非 fallback、印出 `usage`，embedding 維度 1536。**記錄項（回 400／不支援不算不達標）**：`--web-search` 與 `--allowed-domains` 兩次結果寫入 `docs/test/cgu_usage.txt`——`--web-search` 回 400／閘道不支援 → `USE_WEB_SEARCH=false` 進 demo 並在報告註明；`--allowed-domains` 回 200 且 `url_citation` 全在清單內（另記 `gov.tw` 裸網域是否涵蓋子網域）→ 閘道支援，FR-19 維持 P1、D-16 決定是否 Day 6 順手做；否則不做。三次 `/me/usage` 前後差合計 ≤ USD 0.06 |
| OP-3 | P0 | `THREADS_MODE=sim` + `scripts/test_threads_bot.py --poll`（或 `curl` 打 `/api/threads/poll` 後輪詢 `status`） | 一輪完成、`replies.jsonl` 新增 ≥1 行、`/bot` 頁 ≤4 秒顯示該回覆、`status.mode == "sim"` |
| OP-4 | P1 | `scripts/threads_auth.py` 走完授權 | `data/threads_token.json` 產生，含 `authorized_at`，`token_days_left` 介於 55–60 |
| OP-5 | P1 | `scripts/test_threads_bot.py --live` | profile 與 mentions 皆 200；log 一則真實 mention 原始 JSON（記下 `media_type` 實際值）；對機器人自己貼文試發 `auto_publish_text=true` 回覆一則並 `GET /{id}` 可讀（7.6 D-11 依據）；480 字純中文 + 3 emoji 試發一則（7.7 長度規則）；故意讀非 Tester 貼文、用壞 token 各一次並記錄狀態碼與 `error` body（7.10） |
| OP-6 | P1 | `scripts/threads_auth.py --refresh` | `expires_at` 延後 ≥50 天（或拒絕：token <24 h） |
| OP-7 | P0 | 以 v1.0 前的舊 `tasks.parquet`／`knowledge_base.parquet`／`factcheck.db` 啟動後端 | 載入成功、新欄位為預設值、筆數不變（`check_db.py` 前後比對） |
| OP-8 | P0 | Vercel 部署 + quick tunnel + `vercel.json` rewrites | 手機 4G 開 `{PUBLIC_BASE_URL}/r/{任一 id}` 可看到結果；`{PUBLIC_BASE_URL}/api/health` 200（同源代理） |
| OP-9 | P0 | `scripts/clean_sources_2026_09.py --dry-run` → 負責人審閱 `data/clean_sources_report.txt`（D-17）→ `--apply` → 再 `--apply` 一次 | dry-run 不改任何檔（`git status`／檔案 mtime 不變）；報告列出各規則影響筆數與逐筆 before→after；apply 後 `check_db.py`：知識庫 236 筆不變、`verified=true` ≥150、熱門牆 `news.google.com` 0 筆、`.bak-{date}` 備份存在；第二次 apply 影響筆數 0（冪等）；`pytest tests` 仍綠 |

### 10.2 功能測試（3.2 = `pytest tests`，CI 自動）
| ID | 優先級 | 對應 FR | 準則 |
|----|--------|---------|------|
| FN-1 | P0 | FR-01、FR-19 | 既有測試依 5.5／7.7／7.8 新契約更新後全過（**允許改寫** `tests/test_ai_service_contract.py` 的框色案例（改驗 7.8 表 **8 列**）與 Threads 回覆案例（改驗 7.7 新模板，含「尚無查核機構證實」替代行）；其餘 `test_cache_and_store`／`test_marking_rules`／`test_api`／`test_url_validator`／`test_processor_flow` 五檔**不得修改斷言**——`test_cache_and_store` 的 fixture 直接呼叫 `save_record`、無 `verified` 參數，其來源 `165.npa.gov.tw` 為 `gov.tw` Tier 1，由 `save_record` 內部離線計算得 `verified=true`（FR-17「計算位置」），`test_vector_search_exact_hit` 在 `find_similar_by_vector` 加 `verified` 過濾後仍原樣通過）+ 新增：文字輸入不呼叫 crawler（mock 斷言 `process_input` 未被呼叫）；系統 prompt 含 FR-19 逐字規則（字串比對「找不到這類來源就回 `sources: []`」） |
| FN-2a | P0 | FR-02 | `test_safe_url.py`：10 個私網／協定樣本全部拒絕（422 `blocked_url`）且未發出請求、3 個公網放行；連線逾時 10 s 與總逾時 `CRAWLER_TIMEOUT` 以 mock 各自驗證生效；爬取失敗回 UNVERIFIABLE 而非例外；非網址 422；輸入網址同網域的 `sources` 項被剔除。（`similar_news` 向量近鄰斷言隨功能降 P1 移至 FN-2c） |
| FN-2c | P1 | FR-02 `similar_news` | `similar_news` 由向量近鄰填入（固定向量 fixture）、只取 `verified=true` 列、排除自己、≥0.6 |
| FN-2b | P1 | FR-03 | 非圖片 415、>10 MB 413、bytes hash 命中 |
| FN-3 | P0 | FR-04、5.1 | `test_result_api.py`：`/api/result/{id}` 對 pending／completed／failed／404／ai_unavailable 五態 schema 正確；sync／async／threads_sim 三種來源皆 200；`/health` 含 `scheduler.{enabled,interval_hours}` |
| FN-4 | P0 | FR-09／FR-10 | `test_threads_bot_sim.py`：文字 mention 產生 `threads_len ≤ 400` 回覆且含 `/r/`；圖片 mention（`media_type=IMAGE`、無文字）→ `reply_media_only`；`get_post` HTTP 403 → `reply_cannot_read`；HTTP 429 → `backoff_until` 設定；未知 4xx → 標 failed 不回覆；二次 poll 不重複；fallback 不回覆不標記；自我貼文跳過（`username == bot` 與 `reply_id` 在本機清單兩種）；每則後 state 已寫入（crash 模擬）；container `FINISHED` 才 publish、`ERROR` 重試一次 |
| FN-5 | P0 | 7.7 | **七種**第一行模板（含 `🟡 尚無查核機構證實`）`threads_len ≤ 400`（實測後放寬 480）；4 個 emoji + 200 字 summary、含 ⚠️ 的 summary 兩個極端案例仍 ≤500 且保留結果頁連結；「🟡 尚無查核機構證實 + 替代行『尚無查核機構證實』（無連結）」一組長度案例：連結數 = 1（只剩結果頁）、替代行計入長度不計連結；連結數 ≤2；`threads_len` 對 BMP emoji／U+FE0F／U+200D 以 bytes 計；**實測長度規則紀錄欄**（Day 2.5 OP-5 結果） |
| FN-6 | P0 | 7.8 | `frame_of()` 對表格 **8 列** + 11 組 (is_risk, risk_type, confidence, ai_unavailable, verification_status) 輸入的表格測試；含「SAFE、0.95、unverified → yellow 尚無查核機構證實」與「SAFE、0.95、verified → green」、「缺 `verification_status` 鍵 → 視為 unverified」三組 |
| FN-7 | P0 | 5.5 | `is_fallback()` 統一判斷（含 `evaluate.py`／`test_ai_provider.py` 改呼叫）；`ai_unavailable` 與 summary 前綴同時成立 |
| FN-8 | P0 | FR-07 | `q="("` 200；`offset` 分頁不重複不遺漏；stats 四格加總 = total；fixture 中 `verified=false` 列不出現在列表、不計入 `total`（FR-17） |
| FN-9 | P0 | 5.6 | 管理端點無 token → 401；`ADMIN_TOKEN` 空 → 403；正確 → 202/200/409 |
| FN-10 | P1 | FR-14 | `DAILY_AI_CALL_CAP=1` 時第二次未命中回 429 且 AI mock 未被呼叫 |
| FN-11 | P0 | 三層快取 | 同文 hash 命中、改寫文 vector 命中（固定向量 fixture）；`verified=false` 列即使相似度 0.99 也不命中 vector 層（hash 層仍命中）；圖片 bytes hash 命中移至 FN-2b |
| FN-12 | P0 | FR-16 | `test_source_tier.py`：≥15 組 URL／標題 → tier 表格測試（`gov.tw.evil.com` → 3、`news.google.com/rss/…` → 3、Cofacts 有回覆 mock → 1／無回覆 → 3、MyGoPen 任意標題 → 1、ETtoday 查核標題 → 2、ETtoday 一般標題 → 3、Cofacts GraphQL 逾時 → 3、`offline=True` 時 Cofacts → 3 且未發請求）；GraphQL mock 對準 `https://api.cofacts.tw/graphql`（與 search_service.py:216 同端點）；`tier_of` 對 Tier 2 呼叫的是 `news_fetcher._title_indicates_debunk`（mock 斷言，防複製規則） |
| FN-13 | P0 | FR-17 | `test_kb_write_gate.py`：FR-17 驗收 1 的四組（Tier 1 存活 → true；只有 Tier 3 → false 且 vector 不命中；`sources=[]` + rule → true；Tier 1 但 validator 判死 → false）；`/api/result` 回 `verification_status` 三值正確；`sources[]` 無 tier 3 |
| FN-14 | P0 | FR-18 | `test_clean_sources.py`：fixture Parquet／SQLite 上 `--dry-run` 檔案 mtime 不變；`--apply` 兩次結果相同；Google News 解析 mock 成功（覆寫 + 去重）與失敗（刪列）兩種；`label_source="rule"` 列永不降級 |
| 目標 | — | — | P0 測試數 ≥60、CI 綠燈、執行 <60 s、零付費呼叫（Cofacts GraphQL 一律 mock）；FR-01／02／04～07／09／10／11／16／17／18 每條至少一個測試 |

### 10.3 介面測試（3.3 = visual review，共識 §7）
| ID | 優先級 | 準則 |
|----|--------|------|
| UI-1 | P0 | 以 8.4 狀態總表為母版產出「截圖檢核表」（每格一列：畫面／狀態／寬度／主題／檔名／勾核者／結果）。P0 畫面 S1、S2、S3、S4、S6 的打勾格 × 2 寬（375／1280 px）× 2 主題 = 必交（約 100 張；S5 為 P2 不列）。「一致」定義：該格顯示 8.7 對應 key 的文案且無 8.6 列出的違規（字級 <13 px、hover-only 說明）；S1／S2 另與 Day 1 mockup 對照，S3／S4／S6 只對 8.3 元件清單。由非實作組員勾核 |
| UI-2 | P0 | 手機 360×780 無橫向捲動；結果頁動作列 sticky 可見；底部分頁列在安全區內 |
| UI-3 | P1 | 顏色紀律：`grep -l 'c-verdict' src/**/*.jsx` 命中的元件檔 ≤3（ResultCard、Chip、燈號點）；導覽／按鈕不出現紅黃綠（截圖抽查） |
| UI-4 | P0 | 淺色為預設；系統深色時自動深色；切換後重整保持 |
| UI-5 | P1 | Lighthouse（手機）Accessibility ≥90、Performance ≥80；axe 零 critical；鍵盤 Tab 可走完首頁並完成一次查證 |
| UI-6 | P0 | 文案表 8.7 全部 key 在介面出現且逐字一致；`grep -P '[a-zA-Z]{4,}' src/i18n.js` 只允許品牌與 URL；簡體以 OpenCC `t2s` 轉換前後 diff 為空 |
| UI-8 | P0 | 來源紀律（FR-16）：S2 截圖抽查 10 筆結果頁，「查核來源」區每項皆帶 `tier_1_chip`／`tier_2_chip`，無 Tier 3 網域（用 OP-9 後的資料）；S3 截圖無 `news.google.com`；至少一張 S2「尚無查核機構證實」狀態截圖（SAFE 黃 + 橫幅）入檢核表 |
| UI-7 | P1 | Threads 手機 App 內建瀏覽器開 `/r/{id}`：燈號首屏可見；分享鈕開出的 URL 符合 FR-05 驗收 1（App 內是否深連結 composer 只記錄） |

### 10.4 績效測試（3.4 = `evaluate.py --timing` + 後端 log + 手動計時；依共識 §7 不新增腳本）
| ID | 優先級 | 準則 |
|----|--------|------|
| PF-1 | P0 | `evaluate.py --timing`（web_search 關）：未命中 p50 ≤15 s／p90 <20 s（150 筆 `elapsed_ms`）；L1／L2 命中：對 10 筆已入庫文字各重送一次、從後端結構化 log 取 `elapsed_ms + cache_layer`，L1 p50 <1.5 s、L2 p50 <4 s |
| PF-2 | P0 | 三層快取命中率：對 20 筆「改寫版謠言」（組員 C 準備，獨立於 eval_set）以 `POST /api/analyze/sync` 送出，log 中 `cache_layer=vector` ≥70% |
| PF-3a | P0 | Threads 本專案可控延遲：從 `run_threads_poll` 取得 mention 到 `reply_to` 回 200 ≤60 s（log `elapsed_ms`；sim 與 live 各量 3 次） |
| PF-3b | P1 | Threads 端到端牆鐘時間（含 Meta 索引延遲，不可控）：使用者送出 @ 到回覆出現，記錄 5 次實測，目標 ≤ poll 間隔 + 60 s（demo 設 1 分鐘 → ≤2 分鐘）；未達標只記錄不擋 |
| PF-4 | P1 | 模擬模式 10 則 mention 一輪 <3 分鐘（AI 開）；mock AI 時 <10 s |
| PF-5 | P1 | 成本：150 筆評測總花費 ≤ USD 1.5；每次未命中平均 ≤ USD 0.02（CGU `GET /me/usage` 評測前後差 + OP-2 `usage` 輸出，記入 `docs/test/cgu_usage.txt`） |
| PF-6 | P1（可選） | 模型比較組：同 150 筆以 `CGU_MODEL=gpt-5.4` 重跑一次（`USE_WEB_SEARCH=false`；預算 ≤ USD 2，先以 `/me/usage` 確認餘額 ≥ USD 4 才跑），與 `gpt-5.4-mini` 並列 accuracy／FN／p50 延遲／每筆成本；報告 §6 一張表；不作通過條件 |

### 10.5 品質測試（3.5 = `evaluate.py`）
| ID | 優先級 | 準則 |
|----|--------|------|
| QA-1a | P0（閘門） | `evaluate.py --seed-db`（web_search 關）以 **CGU `gpt-5.4-mini`**（provider 鏈 `['cgu']`）重跑 150 筆：**FN=0（絕對條件）**；跑前後各查 `/me/usage`（PF-5） |
| QA-1b | P1（量測） | 同一次執行的 accuracy 與 FP 記錄實際值，目標 ≥93%／≤8；未達標不擋交付，但報告 §6 標示「未達標」並附錯誤分析。報告依 D-8 並列舊數字（0.96，gpt-5-mini via myai168，2026-07）與新數字（gpt-5.4-mini via CGU AIR，2026-09），各標 provider／model／date；PF-6 比較組（gpt-5.4）有跑才加第三欄 |
| QA-2 | P1 | `evaluate.py` 報告加 `provider/model/date/use_web_search/elapsed_ms` 欄；`--report-only` 重算一致；`eval_errors.csv` 逐筆有 `error_type` |
| QA-3 | P0 | CI 每次 push 綠燈（`pytest` + `npm run build`）；`ci.yml` 不再寫死測試數 |
| QA-4 | P1 | CLAUDE.md、README、`.env.example` 與本 spec 的端點／設定名一致（文件審查勾核表，含：Threads 權限清單修正、§2 表格「影片語音轉文字」列刪除、移除 `ENABLE_THREADS_BOT`／STT 設定鍵、`legacy/` 標示、**§2 AI 引擎改寫為「CGU AIR 為唯一 provider、myai168 已停用、額度查 `/me/usage`」、§9 加來源分級三條規則、`BOT_HANDLE=factcheck_tw_bot`、**§4／§7「runtime 變動不用 commit」補例外：FR-18 清洗後的 `knowledge_base.parquet` 提交一次作新種子**） |
| QA-5 | P0 | 清洗 dry-run diff 審查（FR-18）：`data/clean_sources_report.txt` 中 0 筆 `label_source="rule"` 被降級；隨機抽 10 筆降級列由負責人逐筆判斷，同意 ≥9（不同意者記回 `TIER1_DOMAINS`／規則修正後重跑 dry-run）；Cofacts 33 筆逐筆有「有回覆／無回覆」結論；Google News 31 筆逐筆有「解析成功→新網址／失敗→刪除」結論；審查紀錄存 `docs/test/clean_sources_review.md` |

### 4.2 通過準則彙總（可直接抄進計畫書）
- **P0**：OP-1／2／3／7／8／9；FN-1／2a／3／4／5／6／7／8／9／11／12／13／14；UI-1／2／4／6／8；PF-1／2／3a；QA-1a／3／5。
- **P1**：OP-4／5／6；FN-2b／2c／10；UI-3／5／7；PF-3b／4／5／6（可選）；QA-1b／2／4。
- demo 前一日（Day 6）：全部 P0 達標；P1 可在報告前補。
- 4.3 中止：任一 P0 不達標即中止；再繼續 = 修復 + 該項重跑通過 + `pytest tests` 全綠 + `npm run build` 成功。

### 10.6 計畫書對照表（§2.3 參考文件／§4.1 測試環境／§4.4 交付項目）

**2.3 參考文件**：`docs/rebuild/00_consensus.md`（2026-09-14，含 2026-09-15 §4／§9 補充）、`docs/rebuild/01_spec.md`（本文件 v1.3）、`CLAUDE.md`、`code/backend/data/eval_report.csv`／`eval_binary.csv`／`eval_errors.csv`、`assets/confusion_matrix.png`、`data/clean_sources_report.txt`（FR-18）、Threads 官方文件（Threads API Overview、Reference > Publishing／Replies／Mentions、Get Started > Permissions／App Roles、Web Intents；以 threads_gap_analysis／threads_verify_10 記錄之 URL 為準）、CGU AIR Gateway 教學頁（`https://air.cgu.edu.tw/workspace4/LLMAPI/api_call.html`；OpenAI-compatible Responses API，`/v1/me/usage` 用量查詢）、OpenAI Responses API 文件（僅作格式參考；`web_search` `filters.allowed_domains` 於閘道的支援性見 OP-2）。

**4.1 測試環境需求**：
| 項目 | 需求 |
|------|------|
| 後端 | Python 3.11–3.13、`code/backend/venv`、Windows 11（負責人電腦）；uvicorn 單 worker |
| 前端 | Node 20、`npm run build` 通過；Vercel 免費專案（`vercel.json` rewrites） |
| 網路 | Cloudflare quick tunnel（`cloudflared`）；tunnel 單請求 ≤100 s |
| 行動裝置 | iOS Safari 16+ 一台、Android Chrome 110+ 一台（皆裝 Threads App） |
| AI | CGU AIR 新學期金鑰（已到手、實測通過 2026-09-15）：`AI_PROVIDER=cgu`、`CGU_MODEL=gpt-5.4-mini`、`EMBED_MODEL=text-embedding-3-small`；OpenAI 成本額度 USD 10 + 本地模型 1,000 萬 tokens；用量以 `GET {CGU_BASE_URL}/me/usage` 查；**無 OpenAI 直連、無 myai168** |
| Threads | Meta 開發者帳號、App（Threads use case、四權限）、機器人公開帳號、4 個 Threads Tester（皆公開）、60 天長效 token、`THREADS_APP_ID`／`SECRET`；無憑證時 `THREADS_MODE=sim` |
| 資料 | `knowledge_base.parquet` 236 筆種子（**經 FR-18 清洗後**：筆數不變、`verified` 已回填、**已提交至 git**，全新 clone 即含；OP-1 以 `stats.total ≥150` 驗）、`factcheck.db` 熱門（清洗後無 Google News 轉址列）、`eval_set.csv` 150 筆、組員 C 的 20 筆改寫謠言、`data/threads_sim/mentions.json` |
| 工具 | `pytest`、GitHub Actions、Lighthouse（Chrome DevTools）、axe DevTools、OpenCC、`curl`、螢幕錄影（手機內建 + OBS／Xbox Game Bar） |

**4.4 測試交付項目**（檔名與存放路徑）：
| 交付物 | 路徑 |
|--------|------|
| 單元測試報告 | GitHub Actions run 連結 + `pytest -q` 終端機截圖 → `docs/test/ci_run.png` |
| 評測報告 | `code/backend/data/eval_report.csv`、`eval_binary.csv`、`eval_errors.csv`（含 provider/model/date/elapsed_ms 欄）、`assets/confusion_matrix.png` |
| 績效紀錄 | `docs/test/perf_log.csv`（從後端結構化 log 彙整：result_id、origin、cache_layer、elapsed_ms）、PF-3a／3b 手動計時表 `docs/test/threads_latency.csv` |
| 截圖檢核表 | `docs/test/ui_checklist.csv` + `docs/test/screens/{S1..S6}_{state}_{375|1280}_{light|dark}.png` |
| Threads 證據 | `code/backend/data/threads_replies.jsonl` 節錄、OP-5 原始 JSON／錯誤 body 紀錄 `docs/test/threads_live_log.md` |
| 成本證據 | CGU `GET /me/usage` 逐次輸出 `docs/test/cgu_usage.txt`（日期／動作／前／後／差）；CGU 用量頁截圖 `docs/test/cgu_usage.png`（若閘道有網頁版） |
| 資料清洗證據 | `data/clean_sources_report.txt` 節錄 + `docs/test/clean_sources_review.md`（QA-5）+ `check_db.py` 前後輸出 |
| 文件一致性勾核表 | `docs/test/doc_review.md`（QA-4） |
| 影片 | `demo_v0.3.0.mp4`（≤3:00，雲端連結，不進 git） |

---

## 11. 一週時程與 demo 影片分鏡

今天 2026-09-15（二）= **Day 0**（審閱本文件、必答 D-1／D-3／D-5／D-9、開帳號）。Day 1 = 9/16（三）… Day 6 = 9/21（一）；報告與影片假設 9/22（二）交（D-1 待確認——**若實際是 9/21 或更早，Day 5 晚上錄的 sim 版素材就是成品**）。單人實作（AI 助理），組員承接非程式線。實作順序依共識 §7：① AI 恢復 → ② 新前端 → ③ 分享按鈕 → ④ @機器人回覆（含模擬模式）→ ⑤ 每日貼文（選，本次不做）。

**v1.1 範圍刪減（審查：v1.0 Day 2／3／5 各塞 2–3 個工作日）**：P1／P2 全部移出（FR-03 圖片、`/history`、FR-14 額度護欄、速率限制、`POST /api/threads/refresh-token` + APScheduler 續期、reaper、`migrate_2026_09.py`、`bench.py`、`/bot` 進階欄位與「執行一輪」按鈕）；`/bot` 縮成只讀狀態卡；Day 2 拆兩天；機器人拆 Day 5（sim）與 Day 6 上午（live）；評測 Day 6 下午背景跑；錄素材提前到 Day 5 晚上。

**v1.2 範圍調整（共識 §4、§9）**：① AI 恢復已於 Day 0 之前完成（CGU 新金鑰實測通過），Day 0 的 `.env` 切換與 C2 OpenAI 儲值**取消**，省下的 Day 0／Day 1 時間讓給 ② 來源分級；② 新增 FR-16／17／18（P0）塞進 Day 2（`source_tier.py` + 寫入門檻 + 欄位）與 Day 2.5（清洗腳本 dry-run → 審閱 → apply），FR-19 prompt 規則併入 Day 1 OP-2；③ 為了不超過 v1.1 的可行性修正，`similar_news` 向量近鄰降 P1 移出（Day 2 少一項）；④ D-3 只剩品牌名／顯示名稱，handle 已定，C7 只剩 bio 與公開確認。⑤ **Day 2.5 工時重排（v1.3）**：v1.2 把 FR-18 併入 Day 2.5 後，該半天同時塞了後端契約 B 四項 + 清洗腳本四段串行 + 四個新測試檔，超出 v1.1「每日不超載」標準——`safe_url.py` + SSRF、`ADMIN_TOKEN` + `start.bat`、knowledge `offset`／`regex=False`、trending 去 Google News／refresh token 與 FN-2a／8／9 **前移到 Day 2 尾段**（`similar_news` 移出騰出的空間），Day 2.5 上午只留 FR-18 全流程（腳本 → dry-run → 審閱 → apply → 二次 apply → 提交清洗後 parquet）+ `fact_check_records` ALTER 回填 + FN-14；OP-5 live 實測改由**組員 A 主跑**，負責人只在 dry-run／apply 等待期間看結果。

### Day 0／Day 1 帳號與憑證清單（對應計畫書 §4.1；每項要有完成證據）

| # | 項目 | 負責人 | 截止 | 完成證據 |
|---|------|--------|------|---------|
| C1 | 回覆 D-1／D-3／D-5／D-9（品牌名與機器人顯示名稱、網址方案、信箱、報告日期；handle 已定 `@factcheck_tw_bot`） | 負責人 | Day 0 | 本文件 §13 填入 |
| C2 | ~~OpenAI 帳號 + 儲值~~ **取消**（共識 §4 不買 OpenAI 直連）→ 改為：CGU AIR 新學期金鑰**已完成**（2026-09-15 02:00 填入 `.env`、`gpt-5.4-mini` 與 embedding 實測通過、myai168／Gemini 6 個 key 已刪）；Day 0 只需跑一次 `test_ai_provider.py --provider cgu` 並記錄 `/me/usage` 基準值 | 負責人 | Day 0（已完成大半） | `docs/test/cgu_usage.txt` 第一列 |
| C3 | Vercel 帳號 + 專案連 GitHub repo + 部署現有 `code/frontend`（拿到固定 `*.vercel.app` 網址 = `PUBLIC_BASE_URL`） | 組員 B | Day 0 | 網址可開 |
| C4 | 三個純 HTML 靜態頁（privacy／data-deletion／deauthorize）先以 8.7 文案放上 Vercel（Meta App 設定必填） | 組員 B | Day 1 上午 | 三個 URL 可開 |
| C5 | Cloudflare `cloudflared` 安裝、quick tunnel 跑通、`vercel.json` rewrites 指到 tunnel | 負責人 | Day 1 | `{PUBLIC_BASE_URL}/api/health` 200 |
| C6 | Meta 開發者帳號、App（Threads use case、四權限）、填 Privacy／Data Deletion／Deauthorization 三 URL + Valid OAuth Redirect URI `{PUBLIC_BASE_URL}/oauth/callback` | 組員 A | Day 1 | 後台儲存成功截圖；若靜態頁被拒 → FR-13 備案 |
| C7 | 機器人公開 Threads 帳號 **`@factcheck_tw_bot`（負責人已建立）**：剩餘工作 = 設顯示名稱（D-3）、填 bio（7.2）、確認為公開帳號 | 負責人／組員 A | Day 1 | 帳號頁連結 `https://www.threads.com/@factcheck_tw_bot` 可匿名開啟（= 公開） |
| C8 | `THREADS_APP_ID`／`THREADS_APP_SECRET`（Threads use case 頁，非 Meta App ID）交負責人填 `.env` | 組員 A | Day 1 | `.env` 已填（不截圖） |
| C9 | 4 個 Threads Tester 邀請（機器人、組員 A、組員 B、教授可選）+ 受邀者在 Threads App「網站權限」接受 + 帳號全部設公開 | 組員 A | Day 2 | 後台 roles 頁截圖；四人回報已接受 |
| C10 | `ADMIN_TOKEN`（`start.bat` 自動產生或 `python -c "import secrets;print(secrets.token_urlsafe(32))"`） | 負責人 | Day 1 | `curl` poll 回 202 |
| C11 | ~~CGU 新金鑰申請（備援）~~ **已完成**（共識 §4；CGU 現為唯一 provider）→ 改為：負責人審閱 FR-18 清洗 dry-run 報告並回覆 D-15（Tier 1 白名單）／D-17（是否 apply） | 負責人 | Day 2.5 上午 | `docs/test/clean_sources_review.md` |
| C12 | demo 用可疑貼文 2 則文案（信心 ≥0.8 的典型詐騙）+ 發文帳號（組員 A） | 組員 A／B | Day 4 | 貼文連結 |
| C13 | 錄影裝置與工具（iOS + Android 各一、桌機螢幕錄影） | 組員 B | Day 4 | 試錄 10 秒 |
| C14 | 組員 C：20 筆改寫版謠言（PF-2）；組員 D：測試計畫書 §1–2、§5 骨架 | C／D | Day 3 | 檔案在 `docs/test/` |

### 一週時程

| Day | 程式線（負責人 + AI 助理） | 非程式平行線（組員） | 當日驗收 |
|-----|---------------------------|---------------------|---------|
| **0（9/15 二）** | 審閱本文件；C1。**`.env` 已就緒**（共識 §4，02:00 完成）：`AI_PROVIDER=cgu`、`CGU_API_KEY=<新學期金鑰>`、`CGU_MODEL=gpt-5.4-mini`、`EMBED_API_KEY` 同一把（或留空退用 `CGU_API_KEY`）、myai168／Gemini 6 個 key 已刪 → provider 鏈 `['cgu']`（ai_service.py:118-122 只加入有 key 者，**不需再清空任何 RELAY_URL**）。Day 0 程式線只剩：`test_ai_provider.py --provider cgu` 跑一次 + `GET /me/usage` 記基準值（C2 收尾，10 分鐘）；讀 FR-16～18，把 `TIER1_DOMAINS` 初版與 `_title_indicates_debunk` 現況對一遍（D-15 準備）。 | 組員 B：C3。組員 A：開始 C6 前置（Meta 開發者帳號註冊）；C7 收尾（bio、公開確認）。 | D-1／D-3／D-5／D-9 已答；Vercel 網址到手；`cgu_usage.txt` 第一列 |
| **1（9/16 三）** | **上午**：S1／S2 兩張手機寬 mockup（半天；S2 含「尚無查核機構證實」橫幅與 tier chip）+ grill with mockup → 出 ticket（primitives → screens）。`test_ai_provider.py` 加 `--web-search`／`--allowed-domains` 旗標，關／開／限網域各跑一次並印 `usage` + `/me/usage` 差（OP-2，決定 FR-19 `allowed_domains` 是否可做）；系統 prompt 加 FR-19 逐字規則（15 分鐘）。本機 `npm run build` 15 分鐘（失敗 → Vite 7 穩定版，D-13）。**下午**：FR-15 死碼移除（含 STT／seed_data／設定鍵）、保留標記規則、`.gitignore`（含 `clean_sources_*`／`*.bak-*`）、`ci.yml` 加 build、`tests` 仍綠。C5、C10。 | 組員 A：C6／C8。組員 B：C4（三個靜態頁上 Vercel）。組員 D：計畫書 §1–2、§5。 | OP-2；`pytest` 綠；CI 綠（含 build）；Meta App 三 URL 儲存成功 |
| **2（9/17 四）** | 後端契約 A：`GET /api/result/{id}`、`tasks.parquet` 新欄位（含 `verified`／`source_tier`）+ 5,000 上限 + `_load()` 補預設、`/url` 驗證 + `task_type`、`verdict.py`（`frame_of` 8 列 + `is_fallback` 統一 7 處）、fallback `ai_unavailable` + 通用文案、`category_label`、`/health` 欄位。**FR-16／17**：`app/utils/source_tier.py`（`tier_of` + `TIER1_DOMAINS` + Cofacts 回覆查詢 `to_thread`，約 2 小時）、`pandas_task_processor` 分級 + 寫入門檻 + `related_discussions`、`find_similar_by_vector`／`get_knowledge`／`stats` 加 `verified` 過濾、`knowledge_base.parquet` `_load()` 補 `verified=False`、`PandasStore.save_record` 內部計算 `verified`／`source_tier`（FR-17「計算位置」）。（`similar_news` 向量近鄰移出，P1。）`scripts/threads_auth.py` + `/oauth/callback` 頁（1 小時）、`ThreadsService` 讀 `threads_token.json`。**尾段（自 Day 2.5 前移，v1.3）**：後端契約 B——`safe_url.py` + SSRF、`ADMIN_TOKEN` + `start.bat` 自動產生、knowledge `offset`／`regex=False`、trending 去 Google News／refresh 加 token。新測試 FN-3／6／7／12／13 + FN-2a／8／9。 | 組員 A：C9（Tester 邀請 + 接受 + 公開）。組員 C：C14 改寫謠言。 | FN-1／2a／3／6／7／8／9／12／13 綠；OP-7 |
| **2.5（9/18 五 上午）** | `fact_check_records` ALTER（含 `verified`／`source_tier`）+ `label_source` 回填（清洗腳本規則 4 依賴此欄位，先做，30 分鐘）。**FR-18 全流程**：`scripts/clean_sources_2026_09.py`（約 2 小時，Cofacts 逐筆查詢走快取檔；Google News 解析走 Day 2 已完成的 `safe_url.py`）→ `--dry-run` 產出報告 → 負責人 30 分鐘審閱（QA-5、D-15／D-17）→ `--apply` → 二次 apply 驗冪等（OP-9）→ 通過後提交清洗後的 `knowledge_base.parquet`（FR-18 輸出段）。新測試 FN-14。 | **組員 A 主跑**：`threads_auth.py` 取 token → `threads_token.json`；`--live` 只讀驗證 + OP-5 四項實測（log mention JSON、`auto_publish_text` 自貼試發、長度試發、錯誤 body）→ 結果記 `docs/test/threads_live_log.md`；負責人只在 dry-run／apply 等待期間看結果並更正 FR-09 驗收 5、7.7、7.10、7.9 fixture。組員 D：協助 QA-5 抽查 10 筆降級列。 | FN 全綠（含 FN-14）；OP-4、OP-5、OP-9；QA-5；清洗後 parquet 已提交 |
| **3（9/18 五 下午 + 9/19 六 上午）** | ② 新前端：路由（`react-router-dom`）、token、底部分頁列（3 格）、S1 首頁（含最近 5 筆 localStorage）、S2 結果頁（9 態）、深淺色；`vercel.json` rewrites；部署 Vercel；tunnel 接通（C5）。 | 組員 B：影片腳本與旁白稿初稿。組員 D：計畫書 §3–4 引用本文件第 10 節與 10.6。 | UI-1 首頁 + 結果頁截圖；OP-8 |
| **4（9/19 六 下午）** | ③ 分享按鈕 + 複製（FR-05，含 `share_text_yellow_unverified`）；S2 補「尚無查核機構證實」橫幅 + tier chip（前端只讀欄位，30 分鐘）；S3 熱門牆（`label_source`、`verified=false` → `chip_pending`、`scheduler` 文案）；S4 知識庫（offset、四格統計、`knowledge_verified_note`）；頁尾連靜態頁；`start.bat` 更新（tunnel 選項）。 | 組員 A／B：C12 demo 貼文、C13 錄影工具。組員 D：計畫書 §4.1／4.4 抄 10.6。 | FR-05 驗收；UI-2／4／6 初查 |
| **5（9/20 日）** | ④ 機器人（sim 優先）：`THREADS_MODE`、`ThreadsClient` Protocol + `FakeThreadsService`、7.7 模板 + `threads_len`、`verdict.frame_of` 接入、`threads_replies.jsonl`、`threads_state.json` 每則原子寫、`/api/threads/status|replies`、poll 202 + 腳本輪詢、S6 `/bot` 只讀頁；FN-4／5。**晚上：以 sim 錄一份完整閉環素材（保底成品）。** | 組員 B：旁白錄音；組員 D：報告文字（架構、既有 96% 評測、測試計畫節錄）先寫。 | OP-3；FR-10 驗收 1–4；FR-11 P0 驗收；sim 版素材已錄 |
| **6（9/21 一）** | **上午**：live 護欄——since 游標／分頁／鎖、7.6 兩段式 + FINISHED、7.10 分流（依 OP-5 實測值）、backoff；live 端到端一次（組員 A 發文、組員 B @機器人）；補 live 片段。**下午**：`evaluate.py --timing` 150 筆背景跑（QA-1a／PF-1；跑前後 `/me/usage`，餘額 ≥ USD 4 且有空才加跑 PF-6 `gpt-5.4` 比較組）；修 bug；補 UI 截圖檢核表（含 UI-8 來源紀律）；CLAUDE.md／README／`.env.example` 同步（QA-4，含 §2 AI 引擎改 CGU 唯一、§9 來源分級、`BOT_HANDLE`）；封存 `legacy/`；tag `v0.3.0-demo`；`--reset-sim`。**凍結程式。** | 全員：彩排 2 次（live 與 sim 各一次）；剪片、配旁白、字幕；報告換上新數字定稿。 | 4.2 P0 全達標；FR-09 驗收；PF-3a；影片成品 ≤3:00；報告定稿 |
| **7（9/22 二，若 D-1 確認為交件日）** | 待命修 demo 阻塞 bug；備援 sim + 本機。 | 交件。 | — |

**風險緩衝**：若 Day 2.5 前 Meta App／Tester／token 未就緒，Day 6 上午改為 sim 強化與 bug 修，影片以 Day 5 晚上的 sim 素材 + 字幕「模擬模式：介面與流程與正式相同」呈現；live 一旦就緒只需換 `THREADS_MODE`。

### 3 分鐘 demo 影片分鏡（說一個故事；預設 3:00，D-4 待確認）

| 秒 | 畫面 | 旁白／字幕 | 目的 | 保險 |
|----|------|------------|------|------|
| 0–15 | 手機 Threads 動態牆，一則貼文「健保卡即日起停用，請點連結重新驗證」 | 「這則貼文今天在 Threads 上被瘋傳。它是真的嗎？」 | 問題感；一句定位「三層快取 + AI + Threads」 | — |
| 15–35 | 示範者在貼文下回覆「@factcheck_tw_bot 這真的嗎」送出；切桌機終端機 `scripts/test_threads_bot.py --poll`，log：`poll → mention m1 → cache miss → AI(cgu/gpt-5.4-mini) 9.8s → sources: 1×tier1 → container FINISHED → reply …`；旁邊 `/bot` 只讀頁自動出現新回覆卡 | 「只要 @機器人，它會把原貼文抓下來，先比對知識庫，沒查過才請 AI 判讀。」 | 閉環第 1 段、展示架構 | sim 模式同畫面（終端機 + `/bot` 頁 + `replies.jsonl`） |
| 35–55 | 回到手機：機器人回覆出現「🔴 詐騙警告／假冒健保署…／查核來源：mygopen.com/…／完整判讀：…/r/…」 | 「不到一分鐘，紅燈判定、來源、完整判讀連結都回在貼文底下。」 | 產品核心畫面 | sim：`/bot` 頁回覆卡 + `replies.jsonl` + 字幕「模擬模式」 |
| 55–85 | 點連結 → 手機版結果頁 `/r/{id}`：燈號區、你查的內容（來自 Threads @…）、摘要、查核來源（帶「查核機構」chip） | 「點進來是給一般人看的頁面：為什麼是詐騙、哪個查核機構說的——只列已經做出判定的查核來源。」 | U1 的體驗；共識 §9 來源品質 | 事前確認頁面已快取且 `verified=true`（C12 貼文選有 MyGoPen／TFC 查核報導者） |
| 85–100 | 按「分享到 Threads」→ threads.com 預填「🔴 AI 判定這則訊息是詐騙…」+ 連結 → 發布 | 「看懂之後一鍵分享回 Threads。」 | 閉環收尾（Web Intent 零審核） | 若 App 內卡住，桌機瀏覽器版重錄 |
| 100–125 | 切網站首頁：貼入改寫版「健保卡明天起失效要重新認證」→ 3 秒出結果，chip「快取命中・語意相似」 | 「同一則謠言換個說法再問，向量快取直接命中，不用再花 AI 費用。」 | 三層快取實據（`cache_layer`） | 事前確認 0.75 門檻命中 |
| 125–145 | 熱門牆與知識庫快速捲動（燈號、來源機構、`label_source`、命中次數） | 「查過的都進知識庫；熱門牆自動收 MyGoPen、TFC、Cofacts 的查核。」 | 廣度 | 離線資料已在 |
| 145–160 | `/bot` 只讀狀態頁：開發模式徽章、上次輪詢統計、最近回覆列表 | 「機器人的狀態與每一則回覆都有紀錄。」 | U5、可靠性 | — |
| 160–175 | 投影片一張：評測 150 筆 accuracy（CGU gpt-5.4-mini 新跑值，並列舊 96%）、FN=0；每次查證 <USD 0.02（CGU `/me/usage` 實測）；pytest 60+ 全綠 + CI 徽章；知識庫 236 筆經來源分級清洗 | 「準確率、成本、測試、資料品質都有數據。」 | U3（對應測試計畫 3.2／3.5） | 靜態截圖 |
| 175–180 | 結尾：品牌名 + `@factcheck_tw_bot` + 「開發模式；公開上線需 Meta App Review」 | 「下一步：送審、公開。」 | 誠實交代限制 | — |

---

## 12. 風險與緩解

| # | 風險 | 機率／衝擊 | 緩解 |
|---|------|-----------|------|
| R1 | CGU AIR 為**唯一** provider（鏈 `['cgu']`，無備援）：閘道 `web_search`／`filters.allowed_domains` 支援性未驗證；USD 10 額度被評測 + 彩排 + demo 用盡；閘道 401／限流時整站 AI 不可用；學期中金鑰被重置 | 中／高 | Day 0 已實測 `gpt-5.4-mini` 與 embedding；Day 1 OP-2 關／開／限網域各跑一次並記 `/me/usage`；`OPENAI_REASONING_EFFORT=low`；web_search 回 400 → `USE_WEB_SEARCH=false` 進 demo；評測與批次一律 `USE_WEB_SEARCH=false`；預算分配（評測 ≤1.5、demo 週 ≤5、保留 5）；每日開工前查 `/me/usage`；AI 掛時 fallback 契約 + sim 模式 + 預錄素材保底；**不買 OpenAI 直連**（共識 §4） |
| R2 | Meta App／Tester／token 在 Day 2.5 前拿不到 | 中／高 | FR-10 模擬模式 P0，Day 5 無論如何可 demo 且當晚錄保底素材；Day 0 即開始申請；C3／C4 先有 URL 可填 |
| R3 | mentions `limit`／分頁未文件化、`replied_to` 形狀、`media_type` 回傳枚舉、`auto_publish_text` 回傳語意、錯誤碼、長度計數規則皆未實測 | 中／中 | 7.4 有 paging 就跟；主路徑採共識兩段式；Day 2.5 `--live` OP-5 四項實測後才定案 fixture 與長度目標；缺欄位一律容忍 |
| R4 | quick tunnel 網址重啟會變 | 高／低（已隔離） | `PUBLIC_BASE_URL` 永遠是 Vercel；API 經 `vercel.json` rewrites 代理，網址變只改一行重新部署；demo 期間不重啟；替代方案 D-5 |
| R5 | 換模型（gpt-5-mini → CGU gpt-5.4-mini）後評測 accuracy <93% | 低／中 | QA-1a 只守 FN=0；QA-1b 記實際值，報告並列舊 0.96 與新數字並標 provider/model/date；PF-6 `gpt-5.4` 比較組可選 |
| R6 | 單人一週工作量超載 | 中／高（v1.0 高／高） | v1.1 已把 P1／P2 全部移出時程、Day 2 拆兩天、`/bot` 縮只讀、機器人拆 sim／live 兩段；元件共用（ResultCard、Chip、StateCard）；Day 6 凍結 |
| R7 | Threads 內建瀏覽器對 `localStorage`／`navigator.clipboard`／新視窗限制 | 中／低 | 全部 try/catch 降級；複製失敗顯示可選取文字；分享用 `<a target="_blank">` |
| R8 | 公開回覆誤判（評測 FP=5 皆為官方公告判 SCAM） | 低（僅 Tester）／中 | 免責行固定；demo 貼文選信心 ≥0.8 的典型詐騙；D-6 記錄為上線前必做的信心閘門 |
| R9 | 60 天 token／90 天授權在報告後過期 | 確定／低 | `threads_auth.py --refresh` 手動續；`auth_days_left` 顯示；自動續期 P1 |
| R10 | `tasks.parquet`／`knowledge_base.parquet` 併發寫入互蓋（單寫者假設） | 低／中 | uvicorn 單 worker；poll 互斥鎖；demo 不併發壓測；`evaluate.py` 不與 demo 同時跑 |
| R11 | admin token 擋到自己 demo | 低／中 | `start.bat` 自動產生；OP-1 驗 `curl` poll；demo 前 `curl /health` |
| R12 | Cloudflare Tunnel／負責人電腦在 demo 時斷線；tunnel 100 s 逾時 | 中／中 | 前端 `backend_down` 狀態；長工作全非同步；影片預錄；現場備 sim + 本機 `localhost:5173` 直連 |
| R13 | Vite 8 beta 在 Vercel build 失敗 | 中／中 | Day 1 本機 `npm run build`，失敗即降 Vite 7；CI 加 build |
| R14 | Meta 後台不接受靜態頁作 Data Deletion Callback | 低／中 | FR-13 備案 `POST /api/meta/data-deletion`；Day 1 實填時確認 |
| R15 | FR-18 清洗過度降級：`TIER1_DOMAINS` 漏列正當來源或 Cofacts 回覆查詢失敗（逾時視為無回覆）→ 大量 `verified=false`，知識庫頁縮水、PF-2 向量命中率下降 | 中／中 | 預設 `--dry-run` + QA-5 抽查 ≥9/10 同意才 apply；`--apply` 前自動備份 `.bak-{date}`，可回復；Cofacts 查詢結果快取到 `clean_sources_cache.json`，失敗者可 `--retry-cofacts` 重查（FR-18 規則 1 定義）；降級 >86 筆（`verified=true` <150，OP-9 P0 門檻）即先調 `TIER1_DOMAINS` 重跑 dry-run（D-17，與 OP-9 同一數字）；PF-2 的 20 筆改寫謠言對應原文若被降級，先以 `evaluate.py --seed-db`（`gold`，`verified=true`）補種 |
| R16 | 分級後 demo 貼文的判定「尚無查核機構證實」（AI 找不到 Tier 1／2 來源）→ 影片主線出現黃燈而非紅燈 | 中／中 | C12 demo 貼文**必選有 MyGoPen／TFC 查核報導的謠言**（先在網站跑一次確認 `verified=true`、`sources[0].tier==1`）；`USE_WEB_SEARCH` 開時 prompt 規則 + `allowed_domains`（若可用）提高命中；備案：讓該謠言先由熱門牆 RSS `rule` 命中入庫（hash／vector 命中即帶 Tier 1 來源） |
| R17 | Threads 顯示名稱與品牌名不一致造成影片／文件混亂 | 低／低 | D-3 一次定案品牌名 + 顯示名稱；`BOT_HANDLE=factcheck_tw_bot` 固定，全文只用 handle 指稱機器人 |

---

## 13. 待決事項（只放需負責人決定的）

**Day 0（今天 9/15）必答：D-1、D-3、D-5、D-9**——Day 1 填 Meta App 三個 URL、寫隱私頁、設定 `PUBLIC_BASE_URL` 都依賴 D-5／D-9；D-1 決定整個時程基準；D-3 只剩品牌名與機器人顯示名稱（handle `@factcheck_tw_bot` 已建立、不再選）。**若 Day 0 未答，Day 1 一律以預設值進行。**Day 1 另需答 D-13／D-16／D-18；其餘 D-x 可延後。

| # | 事項 | 影響 | 預設（未回覆時採用） | 期限 |
|---|------|------|--------------------|------|
| D-1 | 進度報告確切日期 | 第 11 節時程基準；若是 9/21 或更早，Day 5 晚上 sim 素材即成品 | 2026-09-22（二） | **Day 0** |
| D-2 | 5 位組員姓名／分工；指導教授是否列為審查者 | 測試計畫書 §5、§6 | 依第 11 節角色 A–D 填 | Day 3 |
| D-3 | 品牌名稱（A/B/C）與機器人**顯示名稱**（例「查核小幫手」）。**handle 已定案 `@factcheck_tw_bot`（帳號已建立，不再選）** | `BRAND_NAME`、Threads 顯示名稱、文案；`BOT_HANDLE` 固定 `factcheck_tw_bot` | A「全民查證公社」；顯示名稱「查核小幫手」 | **Day 0** |
| D-4 | demo 影片長度 | 分鏡 | 3:00 | Day 3 |
| D-5 | `PUBLIC_BASE_URL` 與後端網址方案，三選一：(a) 買最便宜網域（USD ~10）託管 Cloudflare 用具名 tunnel（固定 API 網址、最省工）；**(b) quick tunnel + Vercel `vercel.json` rewrites 代理 `/api`（免費、免網域；tunnel 重啟改一行重新部署）**；(c) 後端上 Fly.io／Render 免費層（不靠負責人電腦，解 R12，但要多一天部署） | 分享連結、Meta redirect URI、隱私頁 URL、§9 部署、8.2 | **(b)**，`https://{brand}.vercel.app`，不買網域 | **Day 0** |
| D-6 | Threads 公開回覆是否加「低信心紅燈降黃」閘門（`confidence < 0.5` → 🟡） | 7.8 映射、評測一致性、Web 端規則 | 本輪不加（P2，記為上線前必做） | Day 5 |
| D-7 | Threads 回覆是否附品牌署名 | 7.7 模板字數 | 不附（靠帳號名）；若要附，末行改「{BRAND}｜AI 自動判讀，請自行查證。」 | Day 5 |
| D-8 | 評測數字用新跑（CGU AIR `gpt-5.4-mini`）還是沿用 0.96；是否加跑 `gpt-5.4` 比較組（PF-6，≤ USD 2） | 報告內容、CGU 額度 | 兩者並列，各標 provider／model／date（QA-1b）；比較組視 Day 6 餘額與時間 | Day 6 |
| D-9 | `CONTACT_EMAIL`（資料刪除聯絡信箱） | FR-13、Meta App 設定 | 負責人 email | **Day 0** |
| D-10 | FR-12 每日貼文是否有餘裕實作 | 範圍 | 僅留 spec（本次不做） | — |
| D-11 | 回覆發佈主路徑：共識的兩段式 + `FINISHED` 檢查（預設）vs `auto_publish_text` 單步（需 Day 2.5 OP-5 自貼試發成立） | 7.6 | 兩段式；OP-5 成立後可切 | Day 2.5 後 |
| D-12 | Threads 回覆第一行是否附 `category_label`（「🔴 詐騙警告｜釣魚詐騙」） | 7.7 字數、`category` 未驗證的誤標風險 | 不附（回到共識格式）；若附，`verdict.py` 對未知 category 回退「AI 查核」並加測試 | Day 5 |
| D-13 | 同意新增 `react-router-dom`（非 UI 套件，路由基礎設施）；Vite 8 beta 是否降回 Vite 7 穩定版 | 8.1、CI／Vercel build | 同意；`npm run build` 失敗即降 Vite 7（**P-01 結果 2026-09-15**：原 `8.0.0-beta.16` build 成功，未降版；因 Vite 8 已出穩定版且 beta 不滿足 plugin-react peer `^8.0.0`，改釘 `vite 8.3.0`＋`@vitejs/plugin-react ^5.2.0`，移除 `overrides`；Node 20.20.2 下 `npm ci && npm run build && npm run lint` 皆通過） | Day 1 |
| D-14 | 是否接受附錄 A 標「未獲同意即採預設」的範圍決策（A4／A6／A10 已依審查縮減） | 範圍 | 接受縮減後版本 | Day 1 |
| D-15 | Tier 1 白名單 `TIER1_DOMAINS` 初版確認：`tfc-taiwan.org.tw`、`mygopen.com`、`cofacts.tw`／`cofacts.g0v.tw`（須有 RUMOR／NOT_RUMOR 回覆）、`*.gov.tw`（精確尾綴）、`who.int`、`cdc.gov`；是否加 165 反詐騙（`165.npa.gov.tw` 已含於 gov.tw）、`fda.gov.tw`（已含）、其他（如 `rumor.taipei`、`fact.check` 類）？ | FR-16 分級、FR-18 清洗結果 | 依上列初版；不加其他 | **Day 2.5 上午**（清洗 dry-run 前） |
| D-16 | FR-19 `allowed_domains`（**維持 P1，不升 P0**）：若 OP-2 實測 CGU 閘道支援，是否於 Day 6 下午有餘裕時順手做（約 30 分鐘）？ | web_search 來源品質 | 支援且 Day 6 有餘裕即做；不支援則不做 | Day 1（OP-2 後） |
| D-17 | FR-18 清洗 `--apply` 放行：審閱 `data/clean_sources_report.txt`（QA-5 抽查 10 筆）後同意套用？降級筆數若 **>86**（即 `verified=true` <150，與 OP-9 P0 門檻同一數字；236 − 150 = 86）是否先調規則再 apply？ | 知識庫 `verified` 分佈、PF-2、demo 資料 | 抽查 ≥9/10 同意即 apply；>86 筆降級先調 `TIER1_DOMAINS` 重跑 dry-run 一次（守住 PF-2 向量命中率） | **Day 2.5 上午** |
| D-18 | `similar_news` 向量近鄰降 P1（v1.2 為 FR-16～18 讓位）：接受本次 S2 不顯示「知識庫中的相似查證」？ | S2 元件 5、FN-2c、A14 | 接受（P1 報告後補） | Day 1 |

---

### 附錄 A：本文件相對共識的「新增決策」清單（供 assumptions 追蹤）

| # | 決策 | v1.1 狀態 | 負責人同意 |
|---|------|----------|-----------|
| A1 | `/r/{id}` 的 `{id}` = `task_id`（uuid4），結果持久化在 `tasks.parquet`（上限 5,000）而非新檔或短 id | 維持 | ☐ |
| A2 | React 全部走非同步端點 + 結果頁自輪詢；`/sync` 保留給 Threads bot／自動化 | 維持 | ☐ |
| A3 | Threads 發佈主路徑 | **改回共識**兩段式 + `FINISHED`；`auto_publish_text` 為 D-11 候選；token 走 query/form 參數 | ☐ |
| A4 | 新增 `/bot` 狀態頁、`/history` 頁、`GET /api/threads/replies`、`data/threads_replies.jsonl` | `/bot` 縮為**只讀最小版 P0**；`/history` 降 P2；replies 端點與 jsonl 維持（`/bot` 與 demo 證據需要） | ☐（D-14） |
| A5 | 新增 `grey` 第四種 `frame_type` 僅用於 AI 不可用；`ai_unavailable` 布林為新客戶端的判斷依據 | 維持 | ☐ |
| A6 | 管理端點以 `X-Admin-Token` 單一共享金鑰保護；速率限制與每日額度 | admin token 維持（`start.bat` 自動產生）；**速率限制降 P2、每日額度 FR-14 降 P1** | ☐（D-14） |
| A7 | 不加低信心紅燈閘門（D-6）；`threads_read_replies` 不申請 | 維持 | ☐ |
| A8 | 新增唯一前端依賴 `react-router-dom`；`/terms` 不獨立成頁 | 維持，列 D-13 確認 | ☐（D-13） |
| A9 | AI provider timeout 150 s → 60 s；`THREADS_MODE` 取代 `ENABLE_THREADS_BOT`；模擬模式命名 `sim` | 維持 | ☐ |
| A10 | 每日 AI 呼叫上限 300、速率 10 次/分/IP；Threads 每輪 5、每日 50 則 | 每日上限 P1、速率 P2；Threads 每輪 **demo 週 2**、每日 50 | ☐（D-14） |
| A11 | `label_source` 值域；`fact_check_records` 加 `platform/post_id/label_source/result_id` | 值域統一為 **`ai\|rule\|gold\|admin`**（刪 `seed_data.py`） | ☐ |
| A12 | Threads 回覆第一行帶 `category_label`；固定文案三種；分享文案四種 | 第一行**改回共識**（只有燈 + 判定）→ D-12；固定／分享文案維持 | ☐ |
| A13 | `POST /api/threads/poll` 改同步回 stats | **撤回**：維持非同步 202，`/bot` 頁與腳本輪詢 `status`（tunnel 100 s 上限） | ☐ |
| A14 | `similar_news` 改由知識庫向量近鄰 top-3 填入（googlesearch 移除後唯一來源） | **v1.2 降 P1**（本次 `[]`、S2 元件 5 隱藏；D-18） | ☐（D-18） |
| A15 | 靜態頁改純 HTML（`public/*.html`）+ 新增 `/deauthorize`；OG 只有通用一組 | 新增 | ☐ |
| A16 | 不寫 `migrate_2026_09.py`、`bench.py`；`evaluate.py --timing` 承擔績效量測 | 新增（依共識 §7） | ☐ |
| A17 | 來源分級實作細節（共識 §9 未定）：Tier 3 不丟棄而存 `related_discussions`（P0 不顯示）；`verification_status` 三值（`verified`／`rule`／`unverified`）；`verified=false` 列**仍寫入** Parquet 且 L1 hash 仍命中（只擋 vector 與知識庫頁）；未清洗舊列 `_load()` 預設 `verified=False`（保守） | v1.2 新增 | ☐ |
| A18 | 紅燈不受 `verified` 影響（僅橫幅提示），只有綠燈要求「已證實」；SAFE 未證實 → 黃「尚無查核機構證實」（7.8 第 8 列） | v1.2 新增（共識 §9 只規定「不得綠燈高信心」） | ☐ |
| A19 | 清洗腳本規則：Google News 解析失敗即**刪列**（非標記）；Cofacts 查詢逾時視為無回覆（Tier 3）；`--apply` 前自動備份；不動 `eval_*.csv` | v1.2 新增 | ☐（D-17） |
| A20 | FR-19 拆兩段：prompt 逐字規則 P0、`allowed_domains` **固定 P1**（OP-2 只記錄閘道是否支援；支援時 Day 6 下午有餘裕順手做、不支援不做，D-16；預設清單 = `TIER1_DOMAINS`，無萬用字元） | v1.2 新增；v1.3 明訂不升 P0 | ☐（D-16） |

---

### 變更紀錄

| 版本 | 日期 | 摘要 |
|------|------|------|
| v1.0 | 2026-09-14 | 草稿 A／B 合併定稿 |
| v1.1 | 2026-09-15 | 依審查意見修訂（45 條，全部採納、2 條部分採納）：**部署**——具名 tunnel 需自有網域，改 quick tunnel + Vercel rewrites 同源代理（D-5 三選一）、§9 刪「網址固定」；**範圍**——FR-14 降 P1、速率限制 P2、`/history` P2、`/bot` 縮只讀最小版升 P0、refresh-token 端點與自動續期 P1、reaper P1、刪 `migrate_2026_09.py`／`bench.py`／`seed_data.py`；**時程**——加 Day 0 與帳號憑證清單（C1–C14）、Day 1 上午 mockup + grill + ticket、Day 2 拆兩天、`threads_auth.py` 提前 Day 2、機器人拆 sim（Day 5）／live（Day 6 上午）、sim 素材 Day 5 晚上錄；**Threads**——7.6 主路徑改回共識兩段式 + FINISHED（`auto_publish_text` 為 D-11）、7.5 移除不存在的 `replied_to.owner`、`media_type` 改正向清單且 fixture 用 `TEXT_POST`、7.10 以 HTTP 狀態碼為主 + error.code 標待核對、7.7 第一行回共識格式 + `threads_len` 改 bytes 計 BMP emoji + 目標 ≤400 待實測、7.4 fields 只帶已確認欄位、7.3 加 90 天授權期限、7.2 帳號全部 Tester + 公開；**契約**——5.5 辨識點 7 處（含 `evaluate.py`／`test_ai_provider.py`）、`/health` 加 `scheduler`、`similar_news` 改知識庫近鄰、`label_source` 四值統一、poll 維持 202、爬取逾時統一 `CRAWLER_TIMEOUT`、FR-04 OG 改通用靜態、FR-05 驗收改可控部分、FR-13 純 HTML + `/deauthorize`；**FR-15**——補 STT／設定鍵死碼、加「標記規則三道防線不得改動」；**測試**——§10 每表加優先級、FN-2 拆 a/b、QA-1 拆閘門／量測、PF-3 拆 a/b、UI-1 改截圖檢核表、UI-3／UI-6／FR-04 v5 加量測方法、FN-1 允許改寫兩檔、4.3 加再繼續條件、新增 10.6 計畫書對照表；**待決**——D-1／3／5／9 標 Day 0 必答，新增 D-11～D-14；附錄 A 加狀態與同意欄。 |
| v1.2 | 2026-09-15 | 依共識 2026-09-15 三項更新修訂：**AI 額度（共識 §4）**——CGU AIR 新學期金鑰已到手並實測（`gpt-5.4-mini` + `text-embedding-3-small`、鏈 `['cgu']`、USD 10 + 1,000 萬本地 tokens），**取消**所有 OpenAI 直連假設（C2 儲值、Day 0 `.env` 切換 `OPENAI_RELAY_URL`／清空 `CLAUDE_RELAY_URL`、月預算硬上限、D-8「OpenAI 直連」、R1、OP-2 `--provider openai`、QA-1a、PF-5、§9 成本列、10.6 4.1 AI 列與成本證據）；demo 週護欄改為 CGU `GET /me/usage`（`batch_verify_pending.py` 既有）+ `USE_WEB_SEARCH`；`gpt-5.4` 列為績效測試可選比較組（PF-6、D-8）；C11 CGU 申請標已完成；§1 成功定義 4 改寫。**來源品質與資料清潔（共識 §9）**——新增 FR-16 來源分級與顯示（P0）、FR-17 知識庫寫入門檻（P0）、FR-18 一次性冪等清洗腳本 `clean_sources_2026_09.py --dry-run`（P0；236 筆知識庫／52 無來源／Cofacts 33 筆逐筆確認、63 筆熱門／31 筆 Google News）、FR-19 web_search 網域限制（prompt 規則 P0、`allowed_domains` P1 視 OP-2）；§5 `sources[].tier`／`tier_label`、`verified`、`verification_status`、`source_tier`、`related_discussions`，`/api/knowledge` 只回 `verified=true`；§6 三張表加 `verified`／`source_tier`（`_load()` 預設 False）、6.4 加清洗檔；7.7「查核來源」行只放 Tier 1／2、無來源改「尚無查核機構證實」、分享文案加 `share_text_yellow_unverified`；7.8 加第 8 列「SAFE 未證實 → 黃」、綠燈需已證實；8.3 S2 元件 4 tier chip + 橫幅、狀態 10、S3／S4 規則；8.4 加「未經證實」欄；8.7 加 `tier_1_chip`／`tier_2_chip`／`no_verified_source_*`／`frame_yellow_no_source`／`knowledge_verified_note`、改 `sources_empty`；§9 加「資料品質」列；§10 加 OP-9、FN-12／13／14、UI-8、QA-5、PF-6，FN-6 改 8 列，4.2 彙總更新；§11 加「v1.2 範圍調整」、Day 0／1／2／2.5／4／6 併入、分鏡更新；§12 R1 改寫、加 R15～R17；§13 加 D-15～D-18；附錄 A 加 A17～A20。**為不超過 v1.1 可行性修正，`similar_news` 向量近鄰降 P1**（FR-02、S2 元件 5、FN-2c、A14、D-18）。**機器人 handle**——`@factcommons_tw` 佔位全數替換為已建立的 `@factcheck_tw_bot`（§0 慣例、§2、7.9 fixture、分鏡、C1／C7、D-3）；品牌名 3 候選保留，D-3 改為只選品牌名與顯示名稱。 |
| v1.3 | 2026-09-15 | v1.2 審查修訂第二輪（21 條，全部採納）：**共識引用**——5.2 poll／6.2 `label_source`／6.3 `platform`／7.8 四處掃描事實改引「共識 §10」（§9 插入後改號）；§0 加註共識 §6「要買 OpenAI 額度」已被 §4 取代、本文件不採。**FR-16／17 內部一致**——`verified`／`source_tier` 改由 `PandasStore.save_record` 內部以 `tier_of(..., offline=True)` 計算（processor／`_index_factcheck_claim` 只傳 `label_source`），`test_cache_and_store` 五檔斷言不動（fixture `165.npa.gov.tw` = Tier 1）；`tier_of` 輸出統一為 int + `TIER_LABELS` 查表；Cofacts GraphQL 端點改 `https://api.cofacts.tw/graphql`（以程式碼為準）、同請求並行 + 總逾時 5 s + 程序內 LRU、§9 效能列註明另計；6.1 `tasks.parquet` 舊列 `verified` 一律 False（不在啟動路徑發網路請求）。**狀態推導**——5.3 明訂 `verification_status` 順序（rule → verified → unverified）、`rule`／`verified` 保證 `sources` 非空（`source_url` 補進 `sources`，FR-17／FR-18 規則 1）、UNVERIFIABLE／`ai_unavailable` 不觸發 `no_verified_source_*` 橫幅（S2 狀態 10 例外）；7.7 替代行只以 `verification_status=="unverified"` 觸發；S2 元件 4 同步。**FR-18**——加 `--retry-cofacts` 旗標定義；規則 4 熱門牆 Cofacts 列同樣逐筆查 GraphQL；`--apply` 通過 OP-9 後提交清洗後 `knowledge_base.parquet` 一次作新種子（FR-15 `.gitignore`、6.2、10.6 4.1、QA-4 例外同步）；OP-1 加 `stats.total ≥150`；D-17 門檻 >120 改 **>86**（與 OP-9 `verified ≥150` 一致，R15 同步）。**FR-19**——`allowed_domains` 固定 P1、OP-2 只記錄不升 P0（FR-19、OP-2、D-16、A20 統一）；預設清單 = `TIER1_DOMAINS`（≤20、無萬用字元、`gov.tw` 子網域涵蓋於 OP-2 驗證）；OP-2 拆「P0 條件（關 web_search 一次）」與「記錄項」，避免 400 觸發 4.3 中止。**時程**——Day 2.5 工時重排：後端契約 B 四項 + FN-2a／8／9 前移 Day 2 尾段，Day 2.5 只留 FR-18 全流程 + ALTER 回填 + FN-14，OP-5 由組員 A 主跑（§11「v1.2 範圍調整」⑤）。**其他**——FN-5 六種→七種並加「尚無查核機構證實 + 替代行」長度案例；FN-12 加 offline 案例與端點；S6 P1 加「知識庫未證實筆數」（5.1 `unverified_count` 用途對齊）；7.2 機器人帳號改「已建立 `@factcheck_tw_bot`」、§13 引言去掉「Day 1 建帳號／handle 綁死」；§0 狀態列補 Day 1 答 D-13／D-16／D-18。 |
| v1.4 | 2026-09-22 | 負責人於報告後提出兩項需求（查核機構之後更新的結論要能接回舊資料；熱門搜尋獨立成可與查核機構合作的功能）：新增 **FR-20 查核結果回補**（URL／hash 命中未證實列時只以確定性標記取代、`/api/trending/refresh?analyze=false` 只抓查核文章不呼叫判讀模型、`recheck_unverified.py` 唯讀盤點）與 **FR-21 本站熱門查證**（`GET /api/knowledge/hot`、半衰期 3 小時的時間衰減排序、熱門頁分頁；公開頁只列已證實內容，給查核機構的名單待隱私政策與去識別化後另做）；5.2、5.3 同步。 |
