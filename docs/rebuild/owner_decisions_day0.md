# 負責人決策紀錄（Day 0，2026-09-15）

對應票 O-01。以下是負責人在對話中明確回覆的決定；未回覆項目照 `03_tickets.md` §0 預設值。

## 已定案

| 項目 | 決定 | 來源 |
|---|---|---|
| 報告週範圍 | **A：報告週切片**，只做影片看得到的部分，其他排到報告後（見 `03_tickets.md` §0.5） | 負責人回覆「A a」 |
| 強調色 | **a 墨黑 `#111111`**，連結加底線；`--c-accent` 一個 token | 同上 |
| mockup 方向 | A（淺色、黑白為底、紅黃綠只用在判定） | grill with mockup |
| 品牌 | 全民查證公社；機器人 Threads 帳號 `factcheck_tw_bot`（顯示名稱「全民查證公社」） | 對話 |
| 文字輸入不再送 Google 搜尋 | 同意（grill Q6「全部同意」）→ 視同 FN-1 例外同意，B-03 可改 `test_processor_flow.py` | grill 第二輪 |
| AI provider | CGU AIR 新金鑰，`gpt-5.4-mini`；不買 OpenAI | 共識 §4 |
| Supabase／上雲 | **2026-09-19 定案並實作**：Supabase 只當資料庫（Postgres + pgvector，東京區）；後端跑在 Render 免費主機；金鑰由負責人只貼進 Render 後台，不放 Supabase、不進 git、不貼聊天。目的：正式上線、不依賴負責人的電腦。步驟見 `runbook_cloud_deploy.md` | 2026-09-19 對話 |
| 「結果頁 3 秒看得懂」 | 延到實作後 visual review 用真手機測 | grill with mockup |

| 報告日期 | **2026-09-21～09-23 之間**（確切哪天未定）→ 排程以**最早 9/21（一）**為截止，比原假設 9/22 早一天 | 對話 |
| 專題信箱 | `cans.fakenewsverify@gmail.com`（已填入 `public/privacy.html`、`public/data-deletion.html`） | 對話 |
| GitHub 權限 | `soymilk0211` 已加為協作者（Write），邀請已接受，可推送 | 對話 + 截圖 |
| 機器人顯示名稱 | 先不改（O-06 延後） | 對話 |
| demo 影片配音 | **台灣華語男聲 `zh-TW-YunJheNeural`（雲哲）**，以 `edge-tts`（微軟 Edge 內建朗讀語音，免帳號免金鑰）產生；剪輯最後採用 **HyperFrames**（`video/hf-demo/`，HTML 組版、只在本機 render；先前試裝的 Remotion 未採用）；**不加背景音樂**（2026-09-19）。成品 `docs/demo/demo_v0.4.0.mp4`。負責人 2026-09-16 試聽三個台灣華語語音後選男聲 | 對話 |
| 組員分工 | 廖晢勛＝測試負責人／實作（本人，不負責簡報）、石岱勳＝影片與簡報、姚睿＝介面測試、張宇宏＝績效與品質數據、廖昱翔＝文件與審查 | 2026-09-16 對話 |
| demo 影片製作（舊） | **由 Claude 自動錄製網站畫面、配音、剪輯、上字幕**；配音用 CGU 閘道 `gpt-4o-mini-tts`（負責人試聽後選「自然的」）；已安裝 ffmpeg 9.0.1（winget `Gyan.FFmpeg`）。真實 Threads App／手機分享畫面不錄（範圍 A 用模擬模式） | 2026-09-16 對話 |
| 資料清洗 D-05 | 1a 2a 3a（照建議），已套用 | 2026-09-16 對話 |
| Vercel | 已建立：team `fakenewsverify`（Hobby）、project `fakenewsverify`、Root `code/frontend`。**PUBLIC_BASE_URL = `https://fakenewsverify.vercel.app`**；實測 `/`、`/privacy.html`（含信箱）、`/r/任意id`（SPA fallback）皆 200；CI（含前端 job）綠 | 2026-09-15 部署 |

## CGU 閘道本地模型（2026-09-15 實測，負責人要求「不要浪費」）

| 模型 | 實測 | 適合用途 | 時機 |
|---|---|---|---|
| `gpt-oss:20b` | 可用，判定正確（健保卡釣魚 → SCAM），但慢：13–93 秒（首次含載入） | **背景批次**，不讓使用者等：熱門牆 PENDING 預查證、產生測試用改寫謠言（O-11）、demo 貼文草稿、清洗審閱的第二意見 | 報告後；使用者即時判定仍用 `gpt-5.4-mini` |
| `bge-m3:latest` | 可用，1024 維，約 10 秒 | 中文 embedding 候選；換用需重算 236 筆向量並重新校準 0.75 門檻 | 報告後評估 |
| `translategemma:latest` | 可用，翻譯品質正常，首次 70 秒 | 英文查核來源（WHO、CDC）標題翻成繁中顯示 | 報告後、低優先 |
| `glm-ocr` / `deepseek-ocr` | **目前不可用**：閘道轉發圖片格式錯誤（OpenAI 陣列格式 502；Ollama `images` 欄位回空或逾時） | 圖片查證 FR-03：截圖先 OCR 成文字再走文字管線（比送多模態模型省） | 需先問 CGU 管理員正確傳圖方式 |

## 待負責人確認的文案（非 spec 8.7 逐字，O-01／O-28 一併確認）

| key | 暫用字串 | 用處 | 說明 |
|---|---|---|---|
| `btn_copy_code` | 複製代碼 | S-12 `/oauth/callback` 複製鈕（`src/i18n.js` `EXTRA`） | 8.7 只有 `btn_copy_link`「複製連結」／`btn_copied`；授權碼不是連結，另立此 key。負責人確認後回寫 spec 8.7，或改用其他字樣 |

## 尚未提供（不擋實作）

- 5 位組員姓名與分工（測試計畫書 §5，報告後）
