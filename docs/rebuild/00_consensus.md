# 00 · 重做共識（grill 結論）

> 日期：2026-09-14。本檔是「grill with doc」階段與專案負責人達成的共識，是 spec／mockup／ticket 的唯一上游依據。
> 流程：grill with doc → **spec（功能 + UX）** → mockup → grill with mockup → ticket（primitives → screens）→ implement → visual review。

## 1. 目標與定位

- 專題階段目標：**課程優先**。下週要交**進度報告 + demo 影片（預設 3 分鐘）**；公開上線不在本次範圍，論文寫明上線條件（Meta App Review + 企業驗證）。
- 純軟體專題（系上不要求硬體）；只做繁體中文／台灣。
- 團隊 5 人，實作以專案負責人一人為主；文件（測試計畫書 5.1）人員配置填 5 人。
- 產品定位：**假訊息／詐騙查證平台 + Threads 串接**。使用者貼文字／網址（圖片 P1），系統以 AI 判定 SCAM／MISINFO／SAFE 並附查核來源；Threads 上 @機器人可得到同樣的判定回覆；網站結果可一鍵分享到 Threads。

## 2. 範圍

**做（本次重做）**
- 文字／網址查證（P0）、圖片查證（P1）。
- 熱門牆（今日熱門查核）、知識庫搜尋（瀏覽快取過的判定）。
- **結果頁獨立網址** `/r/{id}`（分享與機器人回覆都需要可點的連結）+ 後端 `GET /api/result/{id}`。
- 分享到 Threads（Web Intent）。
- @機器人回覆（開發模式 + Threads Tester、輪詢制）。
- 模擬 Threads 模式（假 ThreadsService 讀本機 JSON、回覆寫檔）：demo 保險兼離線測試。
- 隱私政策／資料刪除說明靜態頁（Meta Threads use case 設定必填）。
- 每日查核貼文（模式 b）：**P2，有空才做**，spec 要寫但可不實作。

**不做**
- 影片查證（yt-dlp + Whisper）、FB/IG 封閉平台（Playwright 依賴一起移除）。
- 文字輸入的 Google 搜尋抓取（googlesearch-python）；熱門牆的 Google News 來源。
- 管理者覆寫 UI（`/api/admin` API 保留）。
- 使用者帳號／登入；英文介面；Threads Webhook；Threads 私訊（API 不存在）。
- 公開讓陌生人 @機器人（需 App Review + 企業驗證）。

## 3. Threads 整合規格輸入（已對照 2026-09 官方文件）

- 模式 (a) @機器人回覆：`GET /{user_id}/mentions` → 讀原貼文 → `POST /{user_id}/threads (reply_to_id)` → `threads_publish`。現有端點正確；要補：`threads_manage_mentions` 權限（原文件漏列）、`since` 游標 + 分頁、60 天長效 token 續期（`/refresh_access_token`）、container 狀態檢查（`status=FINISHED` 才 publish）、配額護欄（回覆 1,000/24h、`threads_publishing_limit`）、Meta 錯誤碼分流。
- 開發模式事實：未通過 App Review 前，mentions 只回傳 **Threads Tester** 的提及、`GET /{media-id}` 只能讀 Tester 的貼文；私人帳號的貼文不會出現在 mentions。→ demo 由負責人自己的帳號（加為 Tester）示範。
- 模式 (c) 分享：`https://www.threads.com/intent/post?text=...&url=...`，純前端、零審核、零配額。
- 模式 (b) 每日貼文：機器人自己的帳號（有 App 角色）發文**不需送審**；250 則/24h；`publish_text()` 已存在但無呼叫者。
- 回覆格式（≤500 字）：第 1 行 🔴／🟡／🟢 + 判定 → 一句摘要（≤120 字）→ 1 個查核來源連結 → 結果頁連結 → 「AI 自動判讀，請自行查證」。連結 ≤5。
- 不做 Webhook（需企業驗證）；不做 keyword search（未審核只能搜自己的貼文）。

## 4. 後端決策

- **保留**：FastAPI；三層快取（hash → 向量 0.75 → AI）；AI 多 provider（cgu／openai／claude）；trafilatura 網址爬取；MyGoPen／TFC／Cofacts 三來源；標記規則（第 9 節三道防線）；pytest + GitHub Actions CI；SQLite（熱門）+ Parquet（快取）。
- **改**：文字輸入只走「快取 → AI（可開 provider web_search）」，不再把使用者原文送 Google；新增 `GET /api/result/{id}`；回應保留 `cached`／`cache_layer`；死碼移除（Serper、TRENDING_KEYWORDS、Playwright／yt-dlp 管線）；`news_fetcher` 阻塞呼叫改 `to_thread`；程式碼順手梳理。
- **AI 額度（已解決，2026-09-15 02:00）**：2026-09-14 實測三個 provider 全死（CGU 401、myai168 openai 400 no_pricing_info、myai168 claude 402）。負責人取得**新學期 CGU AIR 金鑰**（OpenAI 成本額度 USD 10 + 本地模型 1,000 萬 tokens），填入 `.env` 後實測 `gpt-5.4-mini` 判定正常、embedding 1536 維正常。**不買 OpenAI 直連額度。** `.env` 已刪除 myai168／Gemini 相關 6 個 key，provider 鏈現為 `['cgu']`（`_run_analysis` 只加入有設定 key 的 provider）。模型定案：分析 `gpt-5.4-mini`（config 預設）、embedding `text-embedding-3-small`（0.75 門檻依此校準，不換）；`gpt-5.4` 只作為績效測試的比較組（可選）。CGU 閘道可用模型清單另含 gpt-4.1／gpt-5 全系列、o3／o4-mini、whisper-1、本地 bge-m3／gpt-oss:20b 等。

## 5. 前端決策

- 技術棧保留：React 19 + Vite + Tailwind；**不加 UI 套件**。
- 視覺**全部重做**：淺色為預設、黑白為底 + 單一強調色、紅黃綠只用在判定結果；手機優先（使用者從 Threads 點進來）；深淺色切換可留。
- 畫面：首頁（輸入）／結果頁 `/r/{id}`／熱門牆／知識庫搜尋 + 隱私政策／資料刪除靜態頁。
- 舊單檔 `fake-news-detector.html` 移到 `legacy/` 封存、不再維護。
- 個人查證歷史用 `localStorage`，不做帳號。

## 6. 部署與資源

- 前端：Vercel（免費）。後端：demo 週跑負責人電腦 + Cloudflare Tunnel（免費、HTTPS）；報告後再評估 Fly.io／Render 免費層。
- 要申請（皆免費）：Meta 開發者帳號、Meta App（Threads use case：threads_basic、threads_content_publish、threads_manage_replies、threads_manage_mentions）、機器人專用**公開** Threads 帳號、把負責人（與要示範的人）加為 Threads Tester、60 天長效 token。
- 要買：OpenAI API 額度 USD 5–10。可選：網域（Vercel 子網域即可）。

## 7. 流程與交付

- 實作順序：① AI 恢復 → ② 新前端 → ③ 分享按鈕 → ④ @機器人回覆（含模擬模式）→ ⑤ 每日貼文（選）。
- 測試計畫書納入流程：編號 `TP-FNV-2026-01`；4.2 通過準則在 spec 定；visual review = 3.3 介面測試；`evaluate.py` = 3.4 績效／3.5 品質；`tests/` = 3.2 功能測試。
- 同步更新 CLAUDE.md（含修正 Threads 權限清單）。

## 8. 負責人已定／尚待提供

- **品牌名稱：保留「全民查證公社」**（2026-09-15 定案）。機器人 Threads 帳號已建立，handle `factcheck_tw_bot`（待負責人確認拼法）；顯示名稱用「全民查證公社」。
- 隱私政策／資料刪除頁的聯絡信箱：用**專題專屬 Gmail**（地址待負責人提供，先以佔位符 `{{CONTACT_EMAIL}}` 建頁）。隱私頁與資料刪除頁由 Claude 產出純 HTML，負責人不用動手。
- 下週報告的確切日期：**尚未提供，spec 暫以 2026-09-22（二）排程**。
- 5 位組員姓名／分工；指導教授是否列為審查者：尚未提供（測試計畫書 §5 用）。
- demo 影片長度：預設 3 分鐘。
- Vercel 專案：負責人 2026-09-15 白天建立（GitHub 登入 → Import repo → Root `code/frontend`）；Meta App 三個 URL 依此網址填。

## 9. 來源品質與資料清潔（2026-09-15 補充，負責人明確要求）

負責人指出的缺陷：LLM 有時引用**還沒被查證的**來源（例如求證平台上只是「有人送來問」、尚無判定的貼文），而熱門牆／知識庫也把這類項目當成查核結果收進去——這是髒資料，會毀掉平台的可信度。

決策（spec、ticket、資料清洗都要照做）：
1. **來源分級**：Tier 1 = 已有判定的查核來源（TFC、MyGoPen、Cofacts **有回覆且回覆為 RUMOR／NOT_RUMOR** 的文章、政府機關 `*.gov.tw` 精確網域比對、WHO/CDC 等官方機構）；Tier 2 = 主流媒體查核報導（標題同時含查核語境詞＋判定詞）；Tier 3 = 其他（一般新聞、部落格、社群貼文、**求證平台未回覆的貼文**）。
2. **只有 Tier 1／2 可以顯示為「查核來源」**（Web 結果頁、Threads 回覆、每日貼文皆同）。Tier 3 不顯示或標「相關討論（未查證）」。沒有任何 Tier 1／2 來源時，結果頁要明示「尚無查核機構證實」，且不得顯示綠燈高信心。
3. **知識庫寫入門檻**：AI 判定要寫進 `knowledge_base.parquet` 並參與向量命中，必須 (a) 至少一個 Tier 1／2 來源通過 url_validator，或 (b) 規則命中確定性標記；否則以 `verified=false` 保存但不參與向量命中、不出現在知識庫頁。每筆記錄加 `source_tier`／`verified` 欄位。
4. **AI 的 web_search 限制網域**：provider web_search 若支援 allowed_domains，只允許 Tier 1／2 網域；prompt 明確要求「只引用已做出判定的查核來源，找不到就回 sources=[]，不要猜」。
5. **既有資料清洗（一次性腳本，冪等、--dry-run）**：2026-09-15 稽核——知識庫 236 筆中 **52 筆沒有任何來源**、cofacts.tw 是最常被引用的來源網域（33 筆，需逐筆確認有回覆）；熱門牆 63 筆中 news.google.com 轉址 31 筆（12 筆 UNVERIFIABLE）。清洗規則：沒有 Tier 1／2 來源且非規則命中 → 降級 `verified=false`；Cofacts LINE 對話片段的 claim 不索引；Google News 轉址記錄移除或解析真實網址後去重。

## 10. 掃描發現的既有事實（spec 要考慮）

- 爬蟲：四條新聞來源真實且免金鑰；Google News 轉址連結造成 12/31 筆 UNVERIFIABLE（故移除）；Playwright 瀏覽器在 Windows 本機未安裝（故移除 FB/IG）；使用者原文最長 20,000 字會整段送 Google（故移除搜尋）。
- 資料：`knowledge_base.parquet` 236 筆（TEXT 200／URL 36，200 筆帶向量）；`factcheck.db` 63 筆熱門（MISINFO 30／SAFE 13／UNVERIFIABLE 12／SCAM 8）。
- 安全：crawler 與 url_validator 對任意 URL 發請求無 SSRF 防護（私網位址過濾要補）；`POST /api/threads/poll` 無授權。
- 資料模型：FactCheckRecord 只有 source_url，無 platform／post_id；`ai_score` 混用規則硬編 0.9/0.95 與模型信心（缺 label_source）。
- 紅黃綠：Threads 回覆與 Web 端映射不一致（低信心 SAFE 在 Threads 顯示綠燈）；UNVERIFIABLE 無專屬文案。
- AI fallback 契約：`summary` 以「AI 分析暫時無法使用」開頭，三處前端／機器人靠此辨識（改字樣要一起改）。
