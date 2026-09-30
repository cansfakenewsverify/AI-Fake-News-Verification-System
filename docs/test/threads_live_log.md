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
| 權限 | `threads_basic`、`threads_content_publish`、`threads_manage_replies`、`threads_manage_mentions`；02:39 加 `threads_read_replies` 後重新授權 |
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
2. 回覆相關欄位（`replied_to`、`is_reply`、`root_post`、`has_replies`）在四個權限下不穩定或被拒。
   **加上 `threads_read_replies` 並重新授權後（02:39）全部正常**：提及列表帶 `replied_to` 回 200、
   單一節點的 `is_reply`、`has_replies` 也讀得到。程式仍保留逐則讀取與讀不到時的退路
   （提及本文夠長就直接查本文，太短就回「讀不到原貼文」），權限被拿掉時不會卡住。
3. 讀取**非測試人員**的貼文在開發模式下是否被允許，還沒測（目前的原貼文都是負責人的）。

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

## 在貼文底下呼叫（B-38，第二次端到端）

| 項目 | 內容 |
|------|------|
| 時間 | 2026-10-01 02:57 |
| 貼文 | 負責人帳號發文（不 @機器人）：「聽說台灣通往歐美日的海底電纜全部被切斷了，只剩下通往中國的還能用」 |
| 呼叫 | 負責人帳號在該貼文底下回覆「@factcheck_tw_bot」 |
| 只讀檢查 | 提及帶 `replied_to`，原貼文讀得到（TEXT_POST，32 字） |
| 輪詢結果 | checked 1、replied 1、errors 0；回覆配額 1／1000 |
| 判讀 | 以原貼文判讀：語意快取命中台灣事實查核中心的海底電纜報告，紅燈「假訊息」、信心高，沒有呼叫 AI |
| 結果頁 | `https://fakenewsverify.vercel.app/r/3d628339-82d0-42b8-a417-66f68f596790` 在正式站 200，`origin=threads` |

## 私人帳號（負責人朋友，2026-10-01）

朋友的帳號維持**私人**、已受邀為 Threads 測試人員，在上述貼文底下回覆「@factcheck_tw_bot」：
兩次檢查（間隔數分鐘）提及列表都沒有這則回覆。朋友是否已接受測試人員邀請尚未確認；
改成公開後再測一次，才能確定是「私人帳號收不到」還是「邀請還沒生效」。

尚未完成：私人帳號的確認、非測試人員貼文的讀取、PF-3a／PF-3b 延遲量測、截圖存檔。
