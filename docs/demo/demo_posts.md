# demo 貼文與實測結果（O-12 sim 版）

| 項目 | 內容 |
|------|------|
| 對應 | O-12（sim 版）、O-18、O-19；影片 `docs/demo/demo_v0.3.0.mp4`；分鏡 `docs/demo/storyboard.md` |
| 實測日期 | 2026-09-16 01:23–01:50（+08:00） |
| 環境 | 本機後端 `127.0.0.1:8000`（`THREADS_MODE=sim`、`AI_PROVIDER=cgu`、`CGU_MODEL=gpt-5.4-mini`、`USE_WEB_SEARCH=false`、`SIMILARITY_THRESHOLD=0.75`、embedding `text-embedding-3-small`）＋本機 Vite 前端；詳見 `footage_log.md` |
| 知識庫 | 錄影期間的知識庫 = 已提交種子（218 列、已證實 128 列）＋ `--reset-sim` 種入的 p100 gold 列。錄完已還原成提交版，p100 gold 列與鏡 8 的 AI 列都**不在**提交的種子裡 |

可疑網址 `https://nhi-verify.xyz` 是模擬測試資料，影片中一律模糊遮蔽。

## 1. 主線貼文（鏡 1、3、4、5、6）

`data/threads_sim/mentions.json`（錄影用，只留 p100＋m1）：

| id | 帳號（測試帳號） | 文字 |
|----|------------------|------|
| p100（原貼文） | tester_a | `健保卡即日起停用！請點 https://nhi-verify.xyz 重新驗證，逾期停卡` |
| m1（提及） | tester_b | `@factcheck_tw_bot 這真的嗎`（replied_to p100） |

**`--reset-sim`**（01:24:03）：`p100：已預熱（gold，詐騙警告，sources: 1 x tier1；已寫入向量）`。種子來自 `scripts/threads_sim_seed.json`，查核來源為 MyGoPen `https://www.mygopen.com/2026/08/line.html`（Tier 1 查核機構）。

**`--poll`**（01:24:19–01:24:22，終端機實際輸出）：

```
poll -> mention m1 -> cache hash -> sources: 1 x tier1 -> reply sim_reply_1
       result_id=eb06622e-0592-4361-bfbd-0046b745cba6 frame_type=red
```

| 欄位 | 值 |
|------|----|
| result_id | `eb06622e-0592-4361-bfbd-0046b745cba6` |
| cache_layer | `hash`（L1，未呼叫 AI；後端 log `elapsed_ms` 134） |
| 判定 | 紅燈「詐騙警告」、釣魚詐騙、信心 0.95（高）、`label_source=gold`、`verification_status=rule` |
| 查核來源 | 查核機構：`https://www.mygopen.com/2026/08/line.html` |

`data/threads_sim/replies.jsonl` 的 `text` 欄（逐字，鏡 4 字卡內容）：

```
🔴 詐騙警告
冒用健保署名義的釣魚詐騙：以「即日起停用、逾期停卡」製造急迫感誘騙點連結，健保署不會要求民眾點連結驗證健保卡
查核來源：https://www.mygopen.com/2026/08/line.html
完整判讀：https://fakenewsverify.vercel.app/r/eb06622e-0592-4361-bfbd-0046b745cba6
AI 自動判讀，請自行查證。
```

鏡 6「分享到 Threads」產生的 Web Intent（解碼後）：

- text：`🔴 AI 判定這則訊息是詐騙：冒用健保署名義的釣魚詐騙：以「即日起停用、逾期停卡」製造急迫感誘騙點連結，健保署不會要求民眾點連結驗證健保卡。查核來源：mygopen.com`
- url：`https://fakenewsverify.vercel.app/r/eb06622e-0592-4361-bfbd-0046b745cba6`

## 2. 改寫版（鏡 7，語意相似命中）

先以唯讀腳本量相似度（同一個 embedding 模型、與 `PandasStore.find_similar_by_vector` 相同的算法，只比已證實列、不回寫命中次數），再到網站實錄。

| 候選 | 文字 | 最高相似度（對象） | 結果 |
|------|------|--------------------|------|
| P1（分鏡範例句） | 健保卡明天起失效，要重新認證才能繼續用 | 0.7364（p100 gold 列） | 低於 0.75、不會命中 → 未使用 |
| **P2（採用）** | **你的健保卡即將停用，請盡快點連結重新驗證，不然會被停卡** | **0.8026（p100 gold 列；次高 0.6747）** | **實錄 `cache_layer=vector`** |
| P3 | 健保卡馬上就要停用了，快點網址重新驗證，過期就停卡 | 0.8249（p100 gold 列） | 備用，未實錄 |

P2 實錄（take S7_t3）：result_id `af72a34b-2b20-4a82-99e1-44e2b8c2d83c`，`cache_layer=vector`，`kb_id=3e47b40d-2815-4a80-93e6-e8ad94f50eb9`（即 p100 gold 列），紅燈「詐騙警告」、信心 高、查核來源 mygopen.com，未呼叫 AI（後端 `elapsed_ms` 1969）。同一句前兩個 take（S7_t1、S7_t2）也都是 `vector`，向量命中不回寫新列。

## 3. 鏡 8 新訊息（AI 即時判讀＋尚無查核機構證實）

篩選條件：知識庫無同 hash 列、不在 `data/eval_set.csv`、非健保題材、無真實人名與網址，且與任一已證實列相似度遠低於 0.75（避免變成向量命中）。

| 候選 | 文字 | 最高相似度 | 使用 |
|------|------|------------|------|
| N1 | 群組瘋傳：下個月起全台停車場只收手機支付，現金和悠遊卡一律不能用 | 0.4687 | 備用，未送 AI |
| N2 | 聽說明天起搭高鐵要先下載新 App 完成實名登記，沒登記的車票一律作廢 | 0.3970 | 備用，未送 AI |
| **N3** | **網傳颱風天把冰箱插頭拔掉再插回去，電費會自動減半，電力公司都不說** | **0.4834** | **採用（第一句就成功）** |
| N4 | 朋友傳來說，下週起超商寄包裹一律要先綁定手機號碼，不然包裹會被退回 | 0.5672 | 備用，未送 AI |

N3 實錄（take S8_t1，01:46:13 送出、01:46:21 完成）：

| 欄位 | 值 |
|------|----|
| result_id | `330006c9-0d5b-486d-9af9-4f2b38413e78` |
| cache_layer | `null`（L3 AI；後端 log `provider=cgu`、`elapsed_ms` 7697、估算 USD 0.003073） |
| 判定 | 紅燈「假訊息」、都市傳說、信心 0.93（高）、chip「AI 即時判定」 |
| 來源 | `sources: []`、`verification_status=unverified` → 橫幅「尚無查核機構證實」＋來源區「尚無查核機構證實這則訊息，請自行查證。」 |
| 摘要 | 網傳「颱風天把冰箱插頭拔掉再插回去，電費會自動減半」屬於節電迷思。內容宣稱可大幅省電，但沒有合理依據，且可能導致食物變質。 |

## 4. 重錄須知

- 提交的知識庫不含 p100 gold 列：重錄前照分鏡先跑 `--reset-sim`（會重新種入並寫入向量），P2 才會再次命中 `vector`。
- N3 不在提交的知識庫：再送一次會重新呼叫 AI（花點數，判定文字可能不同）。要保留「AI 即時判定」畫面請換 N1／N2／N4，並確認結果仍無 Tier 1／2 來源。
