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
| Supabase | 報告後再決定（選項：只當資料庫／全搬 Edge Functions／維持現狀） | 對話 |
| 「結果頁 3 秒看得懂」 | 延到實作後 visual review 用真手機測 | grill with mockup |

## 尚未提供（不擋實作）

- 報告確切日期（排程暫以 2026-09-22 計）
- 專題 Gmail 地址（`CONTACT_EMAIL`，隱私頁佔位符 `{{CONTACT_EMAIL}}`）
- 5 位組員姓名與分工（測試計畫書 §5，報告後）
