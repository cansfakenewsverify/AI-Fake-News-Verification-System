# 開發用 fixture（P-10）

`VITE_FIXTURES=1 npm run dev` 時，`src/lib/api.js` 的 `request()` **不發任何 fetch**，
改讀本目錄的 JSON（`src/lib/fixtures.js` 以 `import.meta.glob` 懶載入）。
用途：逐格截圖（spec §8.4、O-24）時可重現每個畫面狀態，不必真的呼叫後端或花 AI 點數。

PowerShell 啟動：

```powershell
cd code\frontend
$env:VITE_FIXTURES="1"; npm run dev
```

production build（`npm run build`）整段剔除，不含任何 fixture；只在 `import.meta.env.DEV` 生效。

## 路徑對應規則

「頁面網址」指瀏覽器網址列的 `?fixture=` 參數（例如 `http://localhost:5173/trending?fixture=empty`）。

| API 請求 | 讀取檔案 |
|---|---|
| `GET /api/result/fx-{state}` | `result_fx-{state}.json`（例：`/r/fx-pending` → `result_fx-pending.json`） |
| `GET /api/trending` | `trending_ok.json`；頁面網址 `?fixture=empty` → `trending_empty.json` |
| `GET /api/knowledge?offset=N` | `knowledge_page{floor(N/30)+1}.json`；`?fixture=empty` → `knowledge_empty.json` |
| `GET /api/knowledge/stats` | `knowledge_stats.json` |
| `GET /api/threads/status` | `threads_status_{?fixture 值，預設 sim}.json` |
| `GET /api/threads/replies` | `threads_replies.json` |
| `GET /api/health` | `health_ok.json` |
| `POST /api/analyze/*` | 頁面網址 `?fixture=` 指定檔（可省略 `.json`），預設 `analyze_text_ok.json` |

- 檔案不存在或路徑無對應規則 → 回 **404**（`/api/result/*` 的 code 為 `result_not_found`，其餘 `fixture_not_found`）。
- `result` id 只接受英數、`_`、`-`、`.`。

## 模擬錯誤狀態

JSON 頂層可帶兩個保留欄位，會從回應 body 移除，並走與真實回應相同的 `ApiError` 正規化：

- `_status`：HTTP 狀態碼（預設 200）
- `_headers`：回應標頭（例如 `Retry-After`）

```json
{ "_status": 429, "_headers": { "Retry-After": "30" }, "detail": "查證太頻繁", "code": "rate_limited" }
```

## 各畫面票的約定

- 每張畫面票（S-）只新增自己用到的 JSON，檔名照上表；不要改 `fixtures.js` 的規則。
- 內容照 spec §5.3／§5.7 回應形狀寫，前端只讀 `frame_type`／`frame_label`（§0 規則 3）。
- 新增的 fixture 檔名與對照 mockup 列入 `docs/test/ui_checklist.csv`（§0 規則 5）。
