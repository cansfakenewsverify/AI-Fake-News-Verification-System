# Meta App Review 送審準備（Threads 機器人開放給所有人）

（2026-10-01 整理。目的：讓 `@factcheck_tw_bot` 不只回覆測試人員，而是任何公開帳號 @ 它都會回。
中文是給團隊看的說明；英文段落是要貼進 Meta 送審表單的草稿，送出前由負責人確認。）

> **狀態（2026-10-03）：先不送審。** 負責人決定機器人先維持開發模式（測試版），只給加入測試人員、帳號設公開的人使用；
> 圖示、英文隱私政策、問老師企業驗證都先不做。這份文件留著，之後要開放給所有人時從第 7 節的順序開始。

## 1. 先看結論

- **要送審的權限有 5 個**：`threads_basic`、`threads_content_publish`、`threads_manage_replies`、
  `threads_manage_mentions`、`threads_read_replies`。開發模式（Standard Access）只能用在有 App 角色的帳號（測試人員），
  要讀一般使用者的提及、回覆一般使用者，每個權限都要 **Advanced Access**，也就是要通過 App Review。
- **最可能卡住的是企業驗證（Business Verification）**。Meta 規定：app 需要進階權限時就要做企業驗證；
  只有「app 只給有角色的使用者用」才免驗證。驗證要附上合法登記組織的官方文件（台灣常見的是公司／商業登記、政府函），
  名稱、地址、電話要和 Meta 商業資產組合裡填的完全一致。**個人或未登記的學生專題無法通過**。
  → 要先問老師：能不能用學校、系所或實驗室的名義？（要由該組織的管理員在 Meta 商業管理工具操作）
- **時間**：企業驗證通常數天到一週；App Review 第三方指南說每次約 2～4 週，官方沒有保證。被退件可以修改後再送。
- **退路**：驗證做不到的話，機器人維持開發模式，只給測試人員用。專題展示與論文不受影響。

## 2. 要準備的東西與現況

| 項目 | Meta 的要求 | 現況 | 誰做 |
|------|-------------|------|------|
| 應用程式圖示 | 1024×1024，不能含 Meta 商標 | 沒有 | Claude 可以做 |
| 隱私政策網址 | 授權畫面會顯示給使用者 | 有（`/privacy.html`，只有中文）→ 建議加英文版 | Claude 可以做 |
| 資料刪除說明網址 | — | 有（`/data-deletion.html`） | — |
| 應用程式用途 | 「你自己或你的商家」或「客戶」 | 未設定 → 選「你自己或你的商家」 | 負責人（後台「基本資料」） |
| 應用程式類別 | 要符合實際用途 | 未設定 → 建議「教育」或「公用程式與生產力」 | 負責人 |
| 聯絡信箱 | 要收得到信 | 有 | — |
| 企業驗證 | 進階權限需要 | **沒有**（見第 1 節） | 負責人＋老師 |
| 5 個權限的用途說明 | 每個權限各寫一段，不可複製貼上 | 草稿見第 3 節 | Claude 草稿、負責人確認 |
| 螢幕錄影 | **每個權限都要有**，沒有影片的權限一律不通過 | 腳本見第 4 節 | 負責人或影片負責的組員 |
| 審查員測試說明 | 說明怎麼測；**不可附個人帳號密碼** | 草稿見第 5 節 | Claude 草稿 |
| 資料處理問卷 | 資料處理者、責任主體、政府調閱紀錄 | 草稿見第 6 節 | Claude 草稿、負責人確認 |

## 3. 權限用途說明（貼進表單的英文草稿）

Meta 要每個權限回答四件事：怎麼幫到使用者、為什麼需要、資料怎麼用、沒有它會少了什麼。以下五段各自獨立寫，不要合併。

**threads_basic**

> FactCheck Commons (全民查證公社) is a fact-checking assistant for Threads, run by a student research team in Taiwan.
> Our own bot account, @factcheck_tw_bot, authorizes the app. We use threads_basic to read the bot's own profile
> (id and username) so the service can confirm it is connected to the right account and can recognize its own posts,
> which prevents the bot from fact-checking or replying to itself. threads_basic is also the base permission that the
> reply and mention features depend on. Without it none of the bot's features can work.

**threads_manage_mentions**

> When a Threads user mentions @factcheck_tw_bot — usually in a reply under a post they doubt, or in their own post that
> contains a claim — our service reads that mention from the mentions endpoint to learn that someone asked for a
> fact-check. We use the public text and link of the mention only to decide which content to check and to answer in the
> same conversation. We store the post id, username and permalink so that each request is answered only once. The bot
> never reads anything it was not mentioned in. Without this permission the bot cannot know when someone asks it for help,
> so the core feature — fact-checking on request inside Threads — would not exist.

**threads_read_replies**

> Most requests arrive as a reply: a user writes "@factcheck_tw_bot" under a public post they are unsure about. To check
> the right content, the bot reads the replied_to reference of that mention and then the text of the post being replied
> to. We use threads_read_replies only for this lookup inside the conversation where the bot was mentioned, and to read
> replies under the bot's own verdict posts. Without it the bot only sees "@factcheck_tw_bot is this true?" and cannot
> tell which post the user means, so it can only answer that it could not read the original post.

（注意：Meta 對 `threads_read_replies` 寫的允許用途是「讀取 app 使用者自己串文底下的回覆」。我們主要是用來讀「提及所在串文的原貼文」，
審查員可能認為不完全相符。上面已照實說明；若被退件，可以同時實作「讀取機器人判定貼文底下的追問並回一句固定說明」，讓用途更貼近官方描述。）

**threads_manage_replies**

> After checking a post, the bot publishes exactly one reply in the same conversation. The reply contains a
> red / yellow / green verdict, a one-line summary, links to fact-checking organizations that have already reviewed the
> claim (for example Taiwan FactCheck Center and MyGoPen), a link to the full result page on our website, and a note that
> the verdict is AI-generated and should be double-checked. The bot replies only when it is mentioned, never twice to the
> same request, and within daily limits. Without this permission the result could not be delivered where the user asked
> for it.

**threads_content_publish**

> Replies on Threads are published through the two-step media container flow (create the container, then publish it),
> which requires threads_content_publish together with threads_manage_replies. The bot publishes content only on its own
> profile and only as replies to users who mentioned it. It does not publish on behalf of other users, does not post
> unsolicited content, and does not advertise. Without this permission the bot cannot create the containers that carry
> the fact-check replies.

## 4. 螢幕錄影腳本

Meta 的規格：解析度 1080 以上（寬度最多錄 1440）；只錄 app 視窗；游標放大；**不要聲音**（審查員不聽）；
介面盡量用英文，不是自明的步驟要加英文字幕。每個權限都要看得到：(1) 使用者授權這個權限的畫面、(2) app 怎麼使用它。
做法：錄一支完整影片，送審時每個權限都附同一支，字幕標明「這一段示範哪個權限」。

1. **授權**（五個權限都要）：開授權網址，以 `@factcheck_tw_bot` 登入 Threads，停在同意畫面、讓五個權限清楚入鏡，
   按允許；跳到網站的授權頁顯示 code。字幕：「The bot account grants the 5 permissions.」
2. **狀態頁**（threads_basic）：開 `https://fakenewsverify.vercel.app/bot`，顯示機器人帳號、上次檢查時間。
3. **在別人貼文底下 @機器人**（threads_manage_mentions、threads_read_replies）：切到另一個帳號（Threads 介面設成英文），
   找一則含可疑說法的公開貼文，回覆「@factcheck_tw_bot」。字幕：「A user asks the bot to check the post above.」
4. **機器人回覆**（threads_manage_replies、threads_content_publish）：30 秒內機器人的回覆出現在底下，停幾秒讓判定、
   查核來源與連結入鏡。字幕說明每一行的意思。
5. **結果頁**（threads_basic 讀取的內容怎麼呈現）：點回覆裡的連結，網站顯示完整判讀與查核機構的原文連結。
6. **直接 @ 的用法**（threads_manage_mentions）：用戶自己發文「@factcheck_tw_bot ＋說法」，機器人回覆。

錄影時要用的都要是真實、可重現的流程。錄之前先確認機器人在雲端正常運作（`/bot` 頁的上次檢查時間會每 30 秒更新）。

## 5. 給審查員的測試說明（Step 4 草稿）

> The app has no login on our website: it is a bot account on Threads, @factcheck_tw_bot.
> How to test:
> 1. From a public Threads account, reply "@factcheck_tw_bot" under any public post that contains a claim
>    (for example: "Undersea cables from Taiwan to the US and Japan have all been cut").
> 2. Within about 30–60 seconds the bot replies in the same conversation with a verdict, fact-check sources,
>    and a link to the full result page.
> 3. You can also post "@factcheck_tw_bot" followed by a claim of at least 8 characters.
> 4. The bot's live status (last check, recent replies) is at https://fakenewsverify.vercel.app/bot
> In development mode only accounts with a role on the app receive replies. We can add a reviewer account as a
> Threads tester if needed. As instructed, we have not included any personal account credentials.

（開發模式下審查員的帳號不是測試人員，機器人看不到他的提及。可以另外申請一個**審查專用的測試帳號**（不是任何人的個人帳號），
加成測試人員後，把帳號密碼寫在這一欄，審查員就能實測；是否這樣做由負責人決定。）

## 6. 資料處理問卷（草稿）

| 問題 | 回答草稿 |
|------|----------|
| 有沒有資料處理者或服務供應商會接觸到平台資料？ | 有：Render（後端主機）、Supabase（資料庫）、Vercel（網站）、長庚大學 CGU AIR 閘道（AI 判讀，貼文文字會送去判讀） |
| 誰負責平台資料？ | 通過企業驗證的組織（待定，見第 1 節） |
| 過去 12 個月有沒有被公家機關要求提供個資？ | 沒有 |
| 有沒有處理公家機關資料請求的政策？ | 待補：只依法律程序提供、會先審查請求的合法性、只提供必要範圍（要寫進隱私政策） |
| 存哪些資料、存多久 | 只存公開貼文的編號、作者帳號名稱、連結與文字，以及判讀結果；查證知識庫無限期（公開查核用途）；查證紀錄最多保留 5,000 筆 |
| 使用者怎麼刪除資料 | `https://fakenewsverify.vercel.app/data-deletion.html`，或寄信到網站的聯絡信箱 |

## 7. 建議順序

1. **問老師**：企業驗證可以用誰的名義（最可能卡關，先確認再做其他事）。
2. Claude：做 1024×1024 圖示、隱私政策加英文版與「公家機關資料請求」一段。
3. 負責人：Meta 後台「基本資料」設定應用程式用途與類別、上傳圖示。
4. 決定要不要建立審查專用的測試帳號。
5. 錄影（照第 4 節腳本）→ 送審（每個權限貼第 3 節的說明、附影片）。
6. 通過後：應用程式切到 Live；機器人改用 webhook 即時回覆（Meta 只對 Live 的應用程式送 webhook）。

## 來源

- [App Review 送審指南（Meta 官方）](https://developers.facebook.com/docs/resp-plat-initiatives/individual-processes/app-review/submission-guide)
- [權限參考：threads_* 的說明與允許用途（Meta 官方）](https://developers.facebook.com/docs/permissions)
- [企業驗證何時需要（Meta 官方）](https://developers.facebook.com/docs/development/release/business-verification)
- [Threads Webhooks（Meta 官方）](https://developers.facebook.com/docs/threads/webhooks)
- [Meta 企業驗證各國文件（第三方整理，含台灣）](https://support.wati.io/en/articles/11463208-meta-business-verification-required-documents-by-country)
- [Threads API 送審經驗（第三方）](https://postproxy.dev/blog/threads-api-posting-integration-guide/)
