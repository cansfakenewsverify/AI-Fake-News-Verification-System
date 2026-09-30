# Threads live 實測紀錄

（票 T-15、T-16、T-17。token 本體不記錄；時間為台灣時間。）

## token（T-15）

| 項目 | 內容 |
|------|------|
| 授權時間 | 2026-10-01 02:18 |
| 授權帳號 | `@factcheck_tw_bot`（`GET /me` 回傳的 username 相符） |
| user_id | 28537756515863830 |
| token 到期 | 2026-11-29 02:18（60 天；`scripts\threads_auth.py --refresh` 續期） |
| 授權到期 | 約 2026-12-29（90 天後要重新同意一次） |
| 權限 | `threads_basic`、`threads_content_publish`、`threads_manage_replies`、`threads_manage_mentions` |
| token 檔 | `code/backend/data/threads_token.json`（已確認 gitignored） |

Meta App「全民查證公社」：Threads 使用案例、四個權限皆為「可供測試」，三個回呼網址與隱私政策、資料刪除指示網址已填。
Threads 測試人員：`factcheck_tw_bot` 與負責人帳號已接受邀請；組員帳號尚未邀請。

## API 探測（T-17，2026-10-01，開發模式）

| 呼叫 | 結果 |
|------|------|
| `GET /{user_id}/mentions?fields=id,text,username,permalink,media_type,timestamp` | 200，正常 |
| 同上再加 `replied_to` | **500**「An unknown error occurred」（code 1） |
| 同上改加 `is_reply,root_post` | **500**（code 1） |
| `GET /{media_id}?fields=id,text,username,media_type`（負責人帳號的貼文） | 200，讀得到 |
| `GET /{media_id}?fields=id,replied_to` | 第一次 200（貼文不是回覆，欄位不存在）；約一小時後同樣的呼叫連續 **500** |
| `GET /{media_id}?fields=id,is_reply` | **500** |
| `GET /{media_id}?fields=id,is_reply,replied_to,root_post,has_replies` | **500**，code 10「Application does not have permission for this action」 |

結論：

1. 提及列表不能要求 `replied_to`，否則整個列表讀不到。程式已改為列表只取基本欄位，再逐則試讀 `replied_to`
   （`threads_service.MENTION_FIELDS`／`MENTION_NODE_FIELDS`）。
2. 回覆相關欄位（`replied_to`、`is_reply`、`root_post`、`has_replies`）在目前的四個權限下不穩定或被拒，推測需要
   `threads_read_replies`（規格原本決定不申請）。讀不到時機器人不會卡住：提及本文夠長就直接查本文，
   太短（例如在別人貼文底下只打「@機器人 這是真的嗎？」）就回「讀不到原貼文」的固定文案。
3. 所以「在別人貼文底下 @機器人、由機器人去讀原貼文」這條路目前還走不通，要先加 `threads_read_replies`
   並重新授權後再測；讀取非測試人員的貼文在開發模式下是否被允許，也要一起測。

## 端到端（T-16，第一次）

| 項目 | 內容 |
|------|------|
| 時間 | 2026-10-01 02:32 |
| 貼文 | 負責人帳號直接發文並 @機器人：「健保卡背面藏著黃金密碼，符合條件政府每年補助幾千元，這是真的嗎？」 |
| 執行方式 | 負責人電腦上以 `THREADS_MODE=live`、`STORAGE_BACKEND=supabase` 跑一輪（結果寫進正式資料庫，回覆裡的結果頁連結才打得開） |
| 輪詢結果 | checked 1、replied 1、errors 0；回覆配額 0／1000 |
| 判讀 | 語意快取命中台灣事實查核中心的查核報告（黃金密碼影片），紅燈「假訊息」、信心高（`factchecked`），沒有呼叫 AI |
| 回覆內容 | 🔴 假訊息／查核摘要／查核來源（台灣事實查核中心網址）／完整判讀連結／「AI 自動判讀，請自行查證。」 |
| 結果頁 | `https://fakenewsverify.vercel.app/r/ea681474-a1a4-430c-a479-10d418cf5b0a` 在正式站 200，`origin=threads` |
| 再跑一輪 | 同一則提及 checked 0、replied 0：不重複回覆 |

尚未完成：在別人貼文底下呼叫（見上節）、PF-3a／PF-3b 延遲量測、截圖存檔。
