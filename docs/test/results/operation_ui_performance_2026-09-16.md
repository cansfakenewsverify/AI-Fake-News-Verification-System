# 操作測試（3.1）、介面測試（3.3）與績效測試（3.4）執行結果

| 項目 | 內容 |
|------|------|
| 對應文件 | `docs/test/TP-FNV-2026-01.md` v0.9 §3.1、§3.3、§3.4、§4.2（判定用語）；`docs/rebuild/01_spec.md` v1.3 §8.4、§9、§10.1、§10.3、§10.4；`docs/rebuild/03_tickets.md` §0.5（報告週切片 A） |
| 執行日期 | 2026-09-16 03:07–04:12（+08:00） |
| 執行者 | Claude（OP／UI／PF 測試代理）。未讀取、未修改 `code/backend/.env`；未修改程式碼、測試與計畫書；未 commit（見 7.2 第 7 點） |
| 受測版本 | 開始時 `main` @ `c114413`。執行期間其他代理提交 `1b37dea`（計畫書 v0.9）與 `b1fc5c3`（`app/utils/parquet_io.py` 重試間隔加長、`evaluate.py`）；8030 後端於 03:17 啟動，執行的是 `c114413` 程式（`parquet_io.py` 檔案最後修改時間 03:48，晚於啟動）；OP-7／OP-9 重跑（03:53 起）使用含 `b1fc5c3` 之工作樹。前端程式在本輪期間未變動 |
| 本機環境 | Windows 11 家用版（build 26200）；Python 3.12.9（`code/backend/venv`）；Node v24.15.0、Vite 8.3.0；Microsoft Edge 153 headless（Chrome DevTools Protocol，由 Node 內建 WebSocket 驅動，未新增安裝） |
| 後端設定 | 只用程序環境變數覆寫（`.env` 由 pydantic 自行載入，本代理未開啟）：`THREADS_MODE=sim`、`PUBLIC_BASE_URL=https://fakenewsverify.vercel.app`、`THREADS_POLL_MINUTES=600`、`USE_WEB_SEARCH=false`、`ENABLE_SCHEDULER=false`、`AI_PROVIDER=cgu`、`CGU_MODEL=gpt-5.4-mini`、一次性 `ADMIN_TOKEN`（只存在程序環境與暫存檔，未印出，結束後刪除）。實際 provider 鏈 `['cgu']`；`CGU_REASONING_EFFORT` 沿用 `.env`／預設（功能測試代理實印為 medium） |
| 服務與埠 | 後端 `127.0.0.1:8030`（OP-7 另開 8031 指向舊資料複本）；暫存 Vite dev server（設定檔在 scratchpad、獨立 cacheDir）：5310＝真後端（`VITE_FIXTURES` 關）、5311＝fixture（`VITE_FIXTURES=1`，只用於無法以真後端誠實產生的狀態）、5330＝`/api` 代理到無服務的 8039（後端不可用）、5342＝代理到 8031（OP-7 畫面佐證）。負責人自己的 5173／5179／5199 未觸碰 |
| 並行作業 | 功能／品質測試代理同時執行 pytest 與 150 筆評測（03:11–03:47），共用 CGU 閘道；本輪 AI 延遲數據是在閘道同時承受評測流量下量得 |
| 原始輸出 | `docs/test/results/raw/`（UTF-8，清單見第 8 節）；截圖 `docs/test/screens/`；檢核表 `docs/test/ui_checklist.csv`；PF-2 改寫句 `docs/test/pf2_paraphrases.csv` |

結果用語依 TP v0.9 §4.2：通過、未通過、通過（待補驗）、報告後執行、未執行（附原因）。「通過（待補驗）」只用於 §4.2 第 2 點列名、且延後準則見第 3 節各表註的項目（OP-3、UI-1、UI-6、PF-3a）；延後內容以外的準則全部達標才使用。

## 1. 結果摘要

| 類別 | P0 | P1 | 說明 |
|------|----|----|------|
| 3.1 操作測試 | 6 項：**通過 3**（OP-2、OP-7、OP-9）、**通過（待補驗）1**（OP-3）、**未執行 1**（OP-1）、**報告後執行 1**（OP-8） | 3 項：**報告後執行 3**（OP-4、OP-5、OP-6） | OP-1 全新 clone＋`start.bat` 未執行，本機 8030 啟動檢查各子項皆達標；OP-8 依本次指示（公開 Vercel＋tunnel、手機 4G）延後 |
| 3.3 介面測試 | 5 項：**通過 3**（UI-2、UI-4、UI-8）、**未執行 2**（UI-1、UI-6） | 3 項：**通過 1**（UI-3）、**報告後執行 2**（UI-5、UI-7） | 85 張截圖；已擷取部分 84 列檢核全數符合。UI-1 深色全套與組員勾核、UI-6 之 OpenCC 與逐 key 介面比對未完成 |
| 3.4 績效測試 | 3 項：**通過（待補驗）1**（PF-3a）、**未通過 1**（PF-2）、**未執行 1**（PF-1） | 4 項：**通過 1**（PF-5）、**報告後執行 3**（PF-3b、PF-4、PF-6） | PF-1 之 L1／L2 命中子準則達標，未命中子準則需 `evaluate.py --timing`（票 B-23，未合入）；PF-2 本輪改寫句命中率 65% |

三類 P0 共 14 項：通過 6、通過（待補驗）2、未通過 1（PF-2）、未執行 4（OP-1、UI-1、UI-6、PF-1）、報告後執行 1（OP-8）。

主要數字：

- **L1 hash 命中**（32 筆已入庫原文，另 1 筆暖機不計）：用戶端 p50 **213 ms**／p95 **257 ms**；後端 `elapsed_ms` p50 156 ms／p95 183 ms。
- **L2 向量命中**（20 筆改寫句，門檻 0.75）：命中 **13／20 = 65%**；命中者用戶端 p50 **3.06 s**／p95 4.72 s（後端 p50 3.00 s）。
- **未命中 → AI**（5 則新訊息）：用戶端 p50 **8.84 s**、最大 **14.73 s**（後端 p50 8.81 s、最大 14.70 s）；本輪 8030 全部 14 次 AI 呼叫後端 p50 9.94 s、p90 12.46 s。
- **Threads 模擬輪詢**（`--reset-sim` → `--poll`，3 輪）：文字 mention 由取出到回覆寫入 205／215／264 ms；第 3 輪自 `--poll` 啟動至 3 則回覆全數寫入 1.33 s；腳本等待輪詢結束的牆鐘時間 3.3–3.4 s（腳本每 2 秒查一次 status）。
- **前端 production bundle**（`vite build`，558 ms）：JS 369.50 kB（gzip 115.85 kB）、CSS 14.75 kB（gzip 4.18 kB）、index.html 1.28 kB；dist 合計 397,293 bytes。
- **CGU 花費（本代理）**：約 **USD 0.096**（15 次 AI＋54 次 embedding），上限 USD 0.50 未觸及；見第 6 節。

## 2. 操作測試（3.1）

| ID | 優先級 | 結果 | 實測數據 | 證據 |
|----|--------|------|----------|------|
| OP-1 | P0 | 未執行（附原因：全新 clone＋`start.bat` 需在另一資料夾 clone、由 pip／npm 下載套件，並由組員 A 自填金鑰（TP 3.1 註 3），本代理不下載套件、不處理金鑰；TP 4.5 排 09-18） | 以本機 8030 預檢可在本機判定的子項，皆達標：`/health` 與 `/api/health` 200、`ai_available=true`、`threads_mode=sim`；`GET /api/knowledge/stats` → `total=128`（v0.9 門檻 ≥125）、`unverified_count=90`；`POST /api/threads/poll` 無 token／錯 token 皆 401 `unauthorized`，正確 token 202（OP-3 的 `--poll`）；`/api/result/{不存在}` 404 `result_not_found`；後端啟動至 `/health` 200 為 1.89 s（不含安裝）。未驗：<5 分鐘（含 pip／npm）、`.env` 自動產生 ≥32 字 `ADMIN_TOKEN`、前端 5173 | `raw/op_startup_health_8030.txt`；`raw/op_backend_runtime_notes.txt`；`raw/pf3a_threads_sim_rounds.txt`（202） |
| OP-2 | P0 | 通過 | P0 條件全數達標：`--provider cgu` 印出 provider 鏈 `['cgu']`、`risk_type=SAFE`（合法值）、非 fallback、`usage={input_tokens: 1259, output_tokens: 304}`、`model=gpt-5.4-mini`、embedding 維度 **1536**；exit 0，約 8.4 s。記錄項未執行：腳本無 `--web-search`／`--allowed-domains` 旗標（票 B-02 未合入 HEAD；TP 3.1 註 2），`docs/test/cgu_usage.txt` 不存在；「三次前後差合計 ≤ USD 0.06」只跑一次，無從比較，單次依閘道計價（輸入 USD 1.5／百萬、輸出 USD 9／百萬 tokens）約 USD 0.0046；`/me/usage` 前後差混入並行評測流量，無法單獨歸屬（第 6 節） | `raw/op2_test_ai_provider_cgu.txt` |
| OP-3（輪詢、`replies.jsonl`、`status.mode`） | P0 | 通過（待補驗） | 3 輪 `--reset-sim` → `--poll --api http://127.0.0.1:8030`：每輪 `POST /api/threads/poll` 202、`checked=3 replied=3 skipped=0 errors=0`；`data/threads_sim/replies.jsonl` 每輪新增 3 行（reset 先清空）；`status.mode == "sim"`。m1（文字）走 L1 hash 命中 `--reset-sim` 種入的 gold 列，回覆「🔴 詐騙警告」＋查核來源 mygopen.com＋`https://fakenewsverify.vercel.app/r/{id}`；m2（IMAGE）固定文案；m3（get_post 403）讀不到文案。待補驗：`/bot` 頁 ≤4 秒顯示該回覆（票 S-11 報告後；目前 `/bot` 為佔位頁，見 `screens/S6_placeholder_375_light.png`） | `raw/pf3a_threads_sim_rounds.txt`；`raw/pf_backend_structured_log_8030.txt`（`threads_bot:` 各行） |
| OP-4 | P1 | 報告後執行 | 需 Meta App、Threads Tester 與實機授權（TP 3.1） | — |
| OP-5 | P1 | 報告後執行 | 需 Threads 實機 token 與 Tester 帳號 | — |
| OP-6 | P1 | 報告後執行 | 需實機 token 取得滿 24 小時 | — |
| OP-7 | P0 | 通過 | 舊檔快照 SHA-256 與 `op7_legacy/README.txt` 三檔一致。複製到 scratchpad 工作目錄（無 `.env`），以 HEAD 程式（`--app-dir code/backend`）在 8031 啟動，2.17 s 健康。**載入成功**：`/health`、`/api/knowledge/stats`、`/api/knowledge`、`/api/trending`、`/api/threads/status` 與舊任務 completed×2、pending×2、failed×2 的 `/api/result/{id}` 皆 200。**新欄位為預設值**：知識庫 `verified` 補 False（stats `total=0`、`unverified_count=236`）；舊任務結果 `verification_status=unverified`、`verified=false`、`label_source=ai`、`source_tier=null`、`similar_news=[]`；`factcheck.db` 啟動時 `ALTER` 新增 6 欄（`platform`、`post_id`、`label_source`、`result_id`、`verified`、`source_tier`），除 `label_source` 回填 ai 38／rule 25 外皆 NULL。**筆數不變**：`check_db.py` 前後輸出逐字相同（知識庫 236、熱門 63），`tasks.parquet` 33 筆、兩個 parquet 欄位未改寫。與 TP 3.1 註 3 的差異：以 scratchpad 複本代替全新 clone（程式同為工作樹 HEAD）。附帶發現缺陷 D-1（舊 AI 失敗任務未標 `ai_unavailable`，7.1） | `raw/op7_check_db_before.txt`、`raw/op7_check_db_after.txt`、`raw/op7_legacy_api_checks.txt`、`raw/op7_legacy_results.txt`、`raw/op7_legacy-fallback-*.png` |
| OP-8 | P0 | 報告後執行（依本次指示：需公開 Vercel 部署＋Cloudflare tunnel 與手機行動網路，本週本機不執行；TP v0.9 原排 09-18） | 前端 `vercel.json` 的 tunnel 主機仍為 `REPLACE-ME.trycloudflare.com` | — |
| OP-9 | P0 | 通過 | 依 v0.9 修訂後準則：① dry-run 不改檔——D-05 審閱紀錄「目前沒有任何資料被改動」，另以提交種子的 scratchpad 複本重跑 `--dry-run`，`knowledge_base.parquet`／`factcheck.db` 的 SHA-256 與 mtime 皆不變；② 報告列出各規則影響筆數與逐筆 before→after（D-05 dry-run 報告經 `clean_sources_review.md` 審閱）；③ apply 後知識庫 **218 = 236 − 18**（核准刪除清單中存在於種子者；另 1 筆「測試文字」不在種子）、`verified=true` **128**（≥125）、熱門牆 24 筆、`news.google.com` **0**（`check_after_d05.txt`；8030 `/api/trending` 12 筆亦 0）；④ `knowledge_base.parquet.bak-20260916`、`factcheck.db.bak-20260916` 存在；⑤ 第二次 apply 各規則影響 0（`clean_sources_report.txt`；本輪複本連跑兩次 `--apply` 仍為 rule1–4 皆 0、Cofacts 網路查詢 0 次，兩檔 SHA-256 不變）；⑥ `pytest tests` 綠：功能測試代理 `raw/fn_pytest_full_rerun.txt` 477 passed（同代理記錄 4 次全套中 1 次 Windows 間歇失敗，見其報告 2.3；本代理未跑 pytest） | `docs/test/clean_sources_review.md`；`code/backend/data/clean_sources_report.txt`、`check_before_d05.txt`、`check_after_d05.txt`；`raw/op9_idempotency_rerun_scratch.txt`；`raw/fn_pytest_full_rerun.txt` |

## 3. 介面測試（3.3）

擷取方式：Edge headless＋CDP。手機 375×812（`mobile:true`、觸控模擬）、桌機 1280×800、DPR 1；主題以模擬 `prefers-color-scheme` 設定、不預寫 `fcc_theme`（同時驗證 UI-4 預設路徑）。全頁截圖先把模擬視窗撐到文件高度再擷取，fixed 分頁列因此落在頁尾、不會蓋住內容；sticky 動作列在全頁圖中回到文件流，實際手機視窗位置另見 `S2_shared-viewport`、`S2_ui2-*`。每張截圖同時做 DOM 檢查：橫向溢出、h1 數、字級 <13 px 的可見文字、判定色 token（`--c-red|yellow|green` 及 `-soft`）出現在導覽／按鈕中、`title` 懸停提示、`news.google.com`、tier 小標、未證實橫幅，並以 Read 逐張目視。`S4_success` 兩張全頁高 14,110／11,566 px（60 張卡），單張縮圖無法辨識文字，改以同頁視窗高度分段截圖（首段、中段、末段）目視，全長仍由 DOM 檢查涵蓋。

截圖來源：真後端 50 張、真後端＋CDP 延後請求 6 張（`S1_submitting`、`S3_loading`、`S4_loading`）、後端不可用 8 張（dev 代理目標無服務，`/api/*` 回 502）、fixture 17 張（429、額度卡、AI 不可用、failed、timeout、熱門空／未查證卡、知識庫空），另 UI-2／UI-4 視窗截圖 4 張。81 張有 DOM 檢查的截圖：全部等到目標狀態、橫向溢出 0、每頁 h1 恰 1 個、<13 px 文字 0、導覽／按鈕內判定色 0（熱門與知識庫卡片本身是連結，卡內燈號點與判定字不計）、`title` 提示 0、console error 0、`news.google.com` 0；HTTP ≥400 只有刻意製造的 404（`S2_404`）與 502（後端不可用 4 組）。

| ID | 優先級 | 結果 | 實測數據 | 證據 |
|----|--------|------|----------|------|
| UI-1（S1–S4 淺色 375／1280 全部 8.4 格＋S2 深色抽查） | P0 | 通過（本代理預檢） | 8.4 母版逐格擷取：S1 空（範例 chip）、送出中、inline 驗證、後端不可用橫幅、429、額度卡；S2 404、載入（真 pending）、超時（fixture，實等 90 秒）、成功（未快取，AI 即時判定）、快取命中（hash、vector）、AI 不可用灰卡（fixture）、錯誤（網路＝後端不可用；failed＝fixture）、UNVERIFIABLE 黃框（真後端 YouTube 網址）、未經證實（SAFE 黃＋橫幅、紅＋橫幅）、分享後；S3 空（fixture）、載入、成功、錯誤、未查證 chip（fixture）、篩選無結果；S4 空兩種（`knowledge_empty` fixture、`knowledge_no_match` 真後端）、載入、成功、錯誤、「無法查證」篩選。淺色 74 張＋S2 深色 7 張全部符合 8.7 文案、無 8.6 違規（字級、hover-only），檢核表 84 列「通過」（含 UI-2／UI-4 視窗截圖 4 列） | `docs/test/ui_checklist.csv`；`docs/test/screens/`；`raw/ui_dom_audit_summary.txt` |
| UI-1（深色全套、S1／S2 與 mockup 對照、非實作組員勾核） | P0 | 未執行（附原因：本次指示只擷取淺色全套＋S2 深色抽查；勾核須由組員 B 勾核、組員 D 覆核，TP 4.5 排 09-17） | 檢核表「目視」欄為 Claude 預檢，不代替勾核者 | `docs/test/ui_checklist.csv` UI-1-088、UI-1-089 |
| UI-1（S6 `/bot`；S4 載入更多） | P0 | 報告後執行（S6：票 S-11）；S4 載入更多不適用（範圍刪減，TP 3.3 註 1） | `/bot` 目前只顯示「Threads 查核機器人／此頁由 screens lane 實作」 | `screens/S6_placeholder_375_light.png`；檢核表 UI-1-086、UI-1-087 |
| **UI-1 整體** | P0 | **未執行（附原因：同上，深色全套與組員勾核未完成）** | 已擷取的 84 列全數符合，無未通過列 | 同上 |
| UI-2 | P0 | 通過 | 360×780 開 `/`、`/r/{id}`、`/trending`、`/knowledge`：`scrollWidth` 皆 360（無橫向捲動）。結果頁動作列 `position: sticky`，頂端時 595–724 px 可見；捲到底時 443–572 px，在分頁列（top 723）之上、未遮住頁尾 disclaimer（403–419）。分頁列 `position: fixed` 貼齊視窗底（723–780），`padding-bottom: env(safe-area-inset-bottom)`、動作列 `bottom: calc(var(--tabbar-h) + env(safe-area-inset-bottom))`。瀏覽器模擬的 safe-area inset 為 0，瀏海機實際位移留待 UI-7 真手機觀察 | `raw/ui2_ui4_checks.txt`；`screens/S2_ui2-top_360_light.png`、`S2_ui2-bottom_360_light.png` |
| UI-3 | P1 | 通過 | ① `src/**/*.jsx` 中引用判定色 token（`c-red|c-yellow|c-green|c-verdict`，依 TP 3.3 註 3 以 brief token 名為準）的檔案 **2 個**（≤3）：`components/Banner.jsx`（warning 色調）、`components/InputCard.jsx`（inline 錯誤字）；燈號色集中在 `lib/verdict.js` 的 `toneOf()`。② 81 張截圖 DOM 檢查：導覽與動作按鈕內判定色 0；判定色只出現在燈號區、燈號點／判定字、未證實橫幅與 UNVERIFIABLE 黃框。觀察（非判定依據）：`backend_down` 橫幅用 yellow／yellow-soft（mockup brief §11 指定），inline 驗證錯誤為紅字（spec §8.3 S1 指定），兩者與 §8.1「紅黃綠只用於判定」字面並存，建議 6.4 審查時一併界定 | `raw/ui_dom_audit_summary.txt`；`screens/S1_backend_down_*`、`S1_validation_*` |
| UI-4 | P0 | 通過 | 全新設定檔、無 `fcc_theme`：系統淺色 → `data-theme=light`（body `rgb(255,255,255)`）；系統深色 → 自動 `dark`（body `rgb(15,17,21)`）。按「切換深淺色」→ 主題翻轉並寫入 `fcc_theme`；`Page.reload` 後保持（light→dark→重整仍 dark；dark→light→重整仍 light）；切換鈕文字依主題顯示「深色／淺色」 | `raw/ui2_ui4_checks.txt`；`screens/S1_ui4-system-light-toggled-reloaded_375_dark.png`、`S1_ui4-system-dark-toggled-reloaded_375_light.png` |
| UI-5（鍵盤部分，預檢） | P1 | 報告後執行（TP：無障礙基準票 P-18 報告後；Lighthouse、axe 本機未安裝且本次不新增安裝） | 鍵盤預檢達標：Tab 依序到品牌、4 個導覽連結、主題切換、模式 tab（方向鍵可切換文字／網址）、textarea、「開始查證」，每站 `outline: solid 2px`；在 textarea 輸入一則已入庫原文後，對送出鈕按 Enter，2.4 s 後進入 `/r/{id}` 並顯示「快取命中・相同內容」（hash 命中，未呼叫 AI）。Lighthouse Accessibility／Performance 與 axe 未執行 | `raw/ui5_keyboard_walkthrough.txt` |
| UI-6（`i18n.js` 對 §8.7 逐字） | P0 | 通過（靜態比對） | 自 spec §8.7 表解析 139 個 key：135 個與 `STRINGS` 逐字相同；其餘 4 個為表格寫法差異：`confidence_chip`（實作拆成 `confidence_chip_high/mid/low`＝「信心 高／中／低」）、`frame_yellow_no_source`、`knowledge_stats`、`nav_bot`（spec 儲存格含括號註解，文案本體一致）；缺漏 0 | `raw/ui6_i18n_static_check.txt` |
| UI-6（`[a-zA-Z]{4,}` 只允許品牌與 URL） | P0 | 未執行（附原因：命中字需審查界定） | 使用者可見字串（去除 URL）命中：品牌 Threads、MyGoPen、Cofacts、LINE、Meta；另有 Cookie、token、THREADS_MODE、WEBP、App Review 與 `{summary}`、`{total}` 等占位符。前者皆為 §8.7 原文逐字內容，依準則字面不屬「品牌與 URL」，須於 6.4 審查決定是否列入允許清單 | `raw/ui6_i18n_static_check.txt` |
| UI-6（逐 key 在介面出現；OpenCC `t2s`） | P0 | 未執行（附原因：OpenCC 未安裝且本次不新增安裝；逐 key 介面出現未系統化比對，本輪截圖只涵蓋 S1–S4 狀態，`/bot` 文案 key 依 TP 3.3 註 2 延後） | — | — |
| **UI-6 整體** | P0 | **未執行（附原因：同上）** | 靜態逐字比對達標 | 同上 |
| UI-7 | P1 | 報告後執行 | 需真手機與 Threads App 內建瀏覽器。本機已確認分享鈕 href 格式：`https://www.threads.com/intent/post?text={encodeURIComponent(share.text)}&url=https%3A%2F%2Ffakenewsverify.vercel.app%2Fr%2F{id}`（capture listener 攔下開新分頁，未對 threads.com 發出請求） | `raw/ui_dom_audit_summary.txt`；`screens/S2_shared*` |
| UI-8 | P0 | 通過 | ① 10 筆真實結果頁（已證實原文 hash 命中）：每頁「查核來源」1 列且皆帶「查核機構」小標，網域 mygopen.com×6、tfc-taiwan.org.tw×2、165.npa.gov.tw×1、cofacts.tw×1。以後端 `tier_of(offline=True)` 複核得 Tier 1×9；cofacts 文章 `236p4q2fmierk` 離線依設計回 3（FN-12：offline 時 Cofacts 一律 3），該文章在 FR-18 清洗報告為「有回覆」，存入之 Tier 1 有效，無 Tier 3 網域。② S3 截圖 12 張 DOM 皆無 `news.google.com`。③ 「尚無查核機構證實」SAFE 黃＋橫幅：真後端 `S2_unverified_safe` 375／1280 淺色與深色 4 張，另有紅＋橫幅 2 張 | `raw/ui8_source_tiers.txt`；`screens/S2_ui8-01…10_375_light.png`、`S2_unverified_safe_*`、`S3_*` |

## 4. 績效測試（3.4）

量測方式：`POST /api/analyze/sync` 依序送出（不並行），用戶端以 `time.perf_counter` 計時，並以 `result_id` 對應後端每筆結構化 log `verification {"result_id","origin","cache_layer","provider","elapsed_ms","tier_ms","usd"}`。百分位以 `numpy.percentile`（線性內插）計算。量測期間知識庫會被寫入（hit_count、AI 結果新列、`--reset-sim` 種入 gold 列），結束後已自備份還原（第 8 節）。

| ID | 優先級 | 結果 | 實測數據 | 證據 |
|----|--------|------|----------|------|
| PF-1（L1 hash 命中） | P0 | 通過（子準則） | 準則 L1 p50 <1.5 s。已證實 TEXT 列逐字原文 32 筆（準則要求 10 筆）＋1 筆暖機不計：32／32 `cache_layer=hash`、回傳 `kb_id` 皆為該原文列、0 次 AI。用戶端 p50 **213.0 ms**、p95 256.5 ms、min 172.0、max 281.1；後端 p50 **156 ms**、p95 183.2、min 127、max 209；暖機一筆用戶端 200.0／後端 163 ms | `raw/pf_requests_2026-09-16.csv`（section=hash）；`raw/pf_backend_structured_log_8030.txt` |
| PF-1（L2 向量命中） | P0 | 通過（子準則） | 準則 L2 p50 <4 s。PF-2 的 13 筆向量命中：用戶端 p50 **3060.0 ms**、p95 4718.9、max 4735.5；後端 p50 **2996 ms**、p95 4670.2（主要為 embedding 呼叫）。spec §9「快取命中（任一層）p95 ≤6 s」亦達標 | 同上（section=vector、cache_layer=vector） |
| PF-1（未命中，150 筆 `evaluate.py --timing`） | P0 | 未執行（附原因：`evaluate.py` 無 `--timing`（票 B-23 未合入 HEAD），且本代理依指示不執行 `evaluate.py`） | 補充（非準則方法、樣本不足 150）：5 則新訊息用戶端 p50 **8844.1 ms**、p90 12540.3、最大 **14734.9 ms**（後端 p50 8805、最大 14698）；本輪 8030 全部 14 次 AI 呼叫後端 p50 9935 ms、p90 12455.4、最大 14698 ms。量測時閘道同時承受 150 筆評測，`CGU_REASONING_EFFORT` 為 medium | `raw/pf_requests_2026-09-16.csv`（section=miss）；`raw/pf_backend_structured_log_8030.txt` |
| **PF-1 整體** | P0 | **未執行（附原因：同上）** | L1、L2 子準則達標 | 同上 |
| PF-2 | P0 | 未通過 | 20 筆改寫句（見下表）送 `/api/analyze/sync`：`cache_layer=vector` **13／20 = 65%**，低於準則 ≥70%。命中 13 筆的 kb_id 皆為對應原文、燈號皆為預期 red。另以相同 embedding 模型離線計算與已證實 1536 維向量（102 列）的最高相似度，預測命中同為 13 筆，與線上結果逐筆一致。未命中 7 筆的最高相似度：0.7314、0.7213、0.7175（接近門檻），0.6894、0.6841、0.5989、0.5748（多為短句詐騙話術片段）；未命中者改走 AI（均寫入 unverified 新列，不參與向量命中）。**資料說明**：本組改寫句由 Claude 為本次量測撰寫，非準則所指之組員 C 版本，亦未經負責人逐筆確認（票 O-11 流程）；量測後未依相似度回頭修改句子，以免結果偏差 | `docs/test/pf2_paraphrases.csv`；`raw/pf_requests_2026-09-16.csv`（section=vector，含離線相似度欄） |
| PF-3a（模擬模式 3 次） | P0 | 通過（待補驗） | 準則 ≤60 s。3 輪 `--reset-sim` → `--poll`：文字 mention（m1）`handle_mention` 由取出到回覆寫入 `elapsed_ms` = **205、215、264 ms**；固定文案 m2 26／22／25 ms、m3 27／27／24 ms。第 3 輪自 `--poll` 啟動（19:28:12.113Z）到 m1 回覆寫入 1.24 s、3 則全部寫入 1.33 s。`--poll` 腳本牆鐘 3395／3359／3325 ms（含每 2 秒查一次 status）；`--reset-sim` 4828／1181／1118 ms（第 1 輪含種入 gold 列與 1 次 embedding）。待補驗：live 3 次（TP 3.4 註 1，報告後） | `raw/pf3a_threads_sim_rounds.txt`；`raw/pf_backend_structured_log_8030.txt`（`mention {...}`） |
| PF-3b | P1 | 報告後執行 | 需 Threads 實機 @ 回覆 | — |
| PF-4 | P1 | 報告後執行 | 本週無 10 則 mention fixture（sim 範例 3 則）；另 `THREADS_MAX_REPLIES_PER_POLL` 預設 5，量測前需調整 | — |
| PF-5 | P1 | 通過 | ① 150 筆評測總花費：功能／品質測試代理以閘道計價估算評測自身上限 **USD 0.943**（≤1.5；池總差額含本代理並行流量，見其報告 §4.5），非本代理量測。② 每次未命中平均：本代理 15 次 AI 呼叫依閘道計價合計約 USD 0.0954，平均 **USD 0.0064／次**（≤0.02）；功能代理估算評測約 USD 0.0063／筆，兩者一致 | `docs/test/results/functional_quality_2026-09-16.md` §4.5、`raw/qa1_cgu_usage.jsonl`；本代理 `raw/opuipf_cgu_usage_snapshots.jsonl`、`raw/pf_backend_structured_log_8030.txt`（`usd` 欄） |
| PF-6 | P1（可選） | 報告後執行 | 可選比較組，預算保留至報告後 | — |

### 4.1 PF-2 逐筆

| # | 改寫句（摘要） | 結果層 | 用戶端 ms | 後端 ms | 離線最高相似度 |
|---|----------------|--------|-----------|---------|----------------|
| 1 | 80 萬無人機升空不到 20 秒墜落 | vector | 2767 | 2733 | 0.8025 |
| 2 | 台灣要求加入日菲海域協商遭拒 | 未命中→AI | 9662 | 9618 | 0.7314 |
| 3 | 南韓地方選舉上午 10 點選票不足 | vector | 4708 | 4651 | 0.8108 |
| 4 | 日菲瓜分台灣專屬經濟海域 | vector | 3312 | 3259 | 0.7722 |
| 5 | 南韓民眾抗議李在明政府選舉作弊影片 | vector | 3972 | 3919 | 0.8229 |
| 6 | 中國人假扮南韓警察 | vector | 4736 | 4699 | 0.8611 |
| 7 | 巴威颱風重創關島影片 | vector | 3060 | 2996 | 0.8105 |
| 8 | 坐飛機拍到巴威颱風眼 | vector | 2768 | 2713 | 0.8485 |
| 9 | NASA 發布巴威颱風衛星圖 | vector | 2918 | 2860 | 0.8490 |
| 10 | 歐洲高溫紅綠燈融化 | 未命中→AI | 10429 | 10340 | 0.7213 |
| 11 | 最近又要限電 | 未命中→AI | 10883 | 10816 | 0.7175 |
| 12 | 黃仁勳站上世界舞台身價飆升 | vector | 2828 | 2778 | 0.8520 |
| 13 | 辦成功才收錢（貸款話術片段） | 未命中→AI | 10294 | 10252 | 0.5748（最近鄰非原文；與原文 0.5465） |
| 14 | 綁定帳戶撥款失敗、凍結貸款 | vector | 3147 | 3115 | 0.8586 |
| 15 | 風控判定身分被冒用、凍結貸款 | vector | 2948 | 2914 | 0.8003 |
| 16 | 撥款後收一成手續費 | 未命中→AI | 12493 | 12462 | 0.5989 |
| 17 | 以投資名義申請政府補助金 | vector | 3904 | 3854 | 0.8088 |
| 18 | 申辦流程不用付半毛錢 | 未命中→AI | 7662 | 7596 | 0.6894 |
| 19 | 計畫書文件都幫您準備好 | vector | 2636 | 2601 | 0.7651 |
| 20 | 申請都要先提供個資 | 未命中→AI | 9116 | 9071 | 0.6841 |

### 4.2 其他量測（無測試 ID，供 spec §9 參考）

| 項目 | 實測 | spec §9 目標 | 證據 |
|------|------|--------------|------|
| 前端 production bundle | `vite build` exit 0、558 ms（含啟動牆鐘 1.9 s），113 modules；`index-Zf5TthD4.js` 369.50 kB（gzip 115.85 kB）、`index-BAyMNAWe.css` 14.75 kB（gzip 4.18 kB）、`index.html` 1.28 kB；dist 含靜態頁、og.png 合計 397,293 bytes。輸出導到 scratchpad，未動 `code/frontend/dist`；Browserslist 資料 7 個月未更新（警告） | 無容量門檻；首屏 LCP <2.5 s 需 Lighthouse，未執行 | `raw/pf_frontend_build.txt` |
| 結果頁 API | `GET /api/result/{id}` 連續 50 次（本機、無 tunnel）：p50 **14.9 ms**、p95 21.1 ms、max 32.7 ms，皆 200 | p50 <300 ms | `raw/pf_result_api_timing.txt` |
| 首頁送出到結果頁顯示 | 真後端未命中：375 寬 18.9 s、1280 寬 16.7 s（皆含 CDP 刻意延後 POST 4 秒；另含 AI 約 10 s 與每 2 秒輪詢） | — | `raw/ui_dom_audit_summary.txt`（`S2_success_*`） |
| 後端啟動 | uvicorn 啟動到 `/health` 200：1.89 s（8030）、2.17 s（8031，舊資料）；以 500 ms 間隔輪詢，解析度約 0.5 s | — | `raw/op_backend_runtime_notes.txt` |
| 錯誤率 | 8030 存取 log 共 328 筆：200×320、202×3、401×2（刻意）、404×3（刻意）、5xx **0**。送出後結果頁輪詢未再出現 DEF-01 的 500；8031（舊資料）48 筆皆 200 | — | `raw/op_backend_runtime_notes.txt` |

## 5. 截圖清單（`docs/test/screens/`，85 張，約 11 MB）

- S1 首頁（14）：`S1_empty`、`S1_validation`、`S1_submitting`、`S1_backend_down`、`S1_rate_limited`、`S1_quota` × 375／1280 淺色；`S1_ui4-system-light-toggled-reloaded_375_dark`、`S1_ui4-system-dark-toggled-reloaded_375_light`
- S2 結果頁（46）：`S2_success`、`S2_cache_hash`、`S2_cache_vector`、`S2_unverified_red`、`S2_unverified_safe`、`S2_unverifiable`、`S2_ai_unavailable`、`S2_loading`、`S2_timeout`、`S2_404`、`S2_network_error`、`S2_failed`、`S2_shared` × 375／1280 淺色（26）；`S2_shared-viewport_375_light`；深色抽查 `S2_success_375_dark`、`S2_cache_hash_375_dark`、`S2_cache_hash_1280_dark`、`S2_unverified_safe_375_dark`、`S2_unverified_safe_1280_dark`、`S2_ai_unavailable_375_dark`、`S2_unverifiable_375_dark`（7）；UI-8 `S2_ui8-01`…`S2_ui8-10_375_light`（10）；UI-2 `S2_ui2-top_360_light`、`S2_ui2-bottom_360_light`
- S3 熱門牆（12）：`S3_success`、`S3_filter_empty`、`S3_loading`、`S3_error`、`S3_empty`、`S3_pending_chip` × 375／1280 淺色
- S4 知識庫（12）：`S4_success`、`S4_no_match`、`S4_filter_unverifiable`、`S4_loading`、`S4_error`、`S4_empty` × 375／1280 淺色（`S4_success` 於知識庫還原為提交種子後重拍）
- S6 機器人（1）：`S6_placeholder_375_light`（佔位頁佐證）
- OP-7 佐證（2，放在 `raw/`）：`op7_legacy-fallback-with-frame_375_light.png`、`op7_legacy-fallback-no-frame_375_light.png`

## 6. CGU AIR 用量（`GET {CGU_BASE_URL}/me/usage`，openai 池；只記數值欄位）

| 時間（UTC） | 標記 | requests | cost_usd | remaining_usd |
|-------------|------|----------|----------|---------------|
| 2026-09-15 19:13:56 | 開工前 | 53 | 0.155421 | 9.844579 |
| 19:24:12 | PF-2 前（OP-2、離線相似度 25 次 embedding、PF-1 hash 已完成） | 172 | 0.710515 | 9.289485 |
| 19:26:08 | PF-2 後 | 221 | 0.897989 | 9.102011 |
| 19:27:33 | PF-1 未命中後 | 247 | 1.018195 | 8.981805 |
| 19:59:29 | 介面測試送出鏈（2 次 AI）後 | 272 | 1.130506 | 8.869494 |
| 20:10:52 | 清理完成 | 272 | 1.130506 | 8.869494 |

- 本輪視窗內池總差額：**+219 requests、+USD 0.975085**。其中 150 requests 與並行的 150 筆評測吻合（功能代理估算評測自身上限 USD 0.943）；本代理 69 requests＝AI 15 次（OP-2 1、PF-2 未命中 7、PF-1 新訊息 5、UI 送出鏈 2）＋embedding 54 次（離線相似度 25、PF-2 20、PF-1 新訊息 5、UI 送出鏈 2、`--reset-sim` 1、OP-2 1）。
- 本代理花費：後端 log `usd` 欄以 USD 0.75／4.50 每百萬 tokens 估算 14 次 AI 合計 USD 0.045403；閘道實際計價為 USD 1.5／9（功能代理於無外部流量區間實測），換算 USD 0.0908，加 OP-2（1,259／304 tokens）USD 0.0046，AI 合計約 **USD 0.0954**；embedding 約 1.6 千 tokens，<USD 0.001。**本代理合計約 USD 0.096**，未達停止門檻 USD 0.50。
- 觀察：後端 `MODEL_PRICING_PER_1M["gpt-5.4-mini"]` 為閘道實際計價的一半，log 的 `usd` 欄會低估 50%。

## 7. 缺陷與觀察（供 TP §6.3 登錄）

### 7.1 缺陷

| 編號 | 嚴重度 | 描述 | 重現步驟 | 建議 |
|------|--------|------|----------|------|
| D-1 | 低（舊資料；§6.1 註明舊任務不在 demo 範圍） | v1.0 前的 AI 失敗任務，`GET /api/result/{id}` 回 `ai_unavailable=false`。舊 `tasks.parquet` 28 筆 completed 中 17 筆 `result_data` 為 fallback（summary 以「AI 分析暫時無法使用」開頭，`is_fallback()` 為真），API 全部回 false；其中 11 筆帶舊 `frame_type`（yellow，舊文案「尚待確認或未知的信息」），`share` 非 null，分享文案為「🟡 這則訊息 AI 尚無法確認：AI 分析暫時無法使用。…」；6 筆無 `frame_type`，header 顯示灰色「AI 暫時無法使用」但走一般結果版面。兩類結果頁都顯示「AI 即時判定」chip 與「尚無查核機構證實」橫幅，沒有 §8.3 S2 狀態 5 的灰卡 | 1. 把 `docs/test/op7_legacy/` 三檔複製到空的工作目錄 `data/`（不放 `.env`）；2. 在該目錄執行 `<repo>\code\backend\venv\Scripts\python -m uvicorn app.main:app --app-dir <repo>\code\backend --port 8031`（`<repo>` 為專案根目錄絕對路徑）；3. `GET /api/result/d52e84e8-77e6-46d4-880b-e1de5f8cd495` → `ai_unavailable:false`、`result.summary` 以 fallback 前綴開頭、`share` 非 null；4. 前端代理到 8031 開 `/r/d52e84e8-…` → 黃框與「分享到 Threads」 | 在 `analyze.task_result_payload`（或 `_with_v2_defaults`）以 `is_fallback()` 補 `ai_unavailable`（前綴只留給舊碼相容，符合 §5.5），`share` 隨之為 null；或在 §6.1 明文接受並從檢核排除 |
| D-2 | 低（資料） | 知識庫頁同一主張出現兩張卡、標籤不同：`484ad500`（TEXT，假訊息，Cofacts 標題）與 `cac3a014`（URL，詐騙），`2ac98c6c`（TEXT，假訊息）與 `95acaa79`（URL，詐騙）。四列皆 `verified=true`，為提交種子既有資料 | 開 `/knowledge`（提交種子）：前兩張卡為 URL 列（詐騙），列表後段有同文的 TEXT 列（假訊息） | 清洗規則加「同一 Cofacts 文章之 TEXT／URL 列去重或統一 risk_type」；與 CLAUDE.md §9「同一謠言兩種標籤」同類 |
| D-3 | 低（資料，待人工確認） | 部分已證實列的「主張」是查核機構文章標題，被標為假訊息，摘要成為「此為已被查核的假訊息：『解析「馬鈴薯之亂」：被網路謠言挑動的食安焦慮』」（`5b12ca94`）、「此為已被查核的假訊息：『臉書詐騙廣告年賺5000億』」（`c1ca6a6a`）；`c792a37e`「禧年探索資本已被金管會通報為高風險投資詐騙黑平台」標為假訊息，內容讀來可能是正確警示。UI-8 抽查頁 07、08、09 可見 | 開 `screens/S2_ui8-07_375_light.png`、`-08`、`-09`，或以原文送 `/api/analyze/sync` | 請負責人逐筆確認；若屬誤標，改 `risk_type` 或移出知識庫（`/api/admin` 覆寫） |
| D-4 | 低（資料） | 128 筆已證實列中 11 筆向量為 3072／768 維，永遠不會命中向量層，實際可參與語意命中者 **102** 筆（`clean_sources_review.md` 寫 113 筆，是把非 1536 維列也算入） | 以 pandas 讀提交種子：`verified==True` 且 `len(content_vector)==1536` 計數 | 以 `text-embedding-3-small` 重算這 11 筆向量（11 次 embedding），或修正文件數字 |

### 7.2 觀察（不影響本輪判定）

1. **判定色使用**：`backend_down` 橫幅（brief §11）與 inline 驗證紅字（spec §8.3 S1）使用判定色 token，和 spec §8.1「紅黃綠只用於判定」字面衝突，建議 6.4 審查時界定（UI-3）。
2. **UI-6 字面準則**：§8.7 文案本身含 Cookie、token、THREADS_MODE、WEBP、App Review，`[a-zA-Z]{4,}` 準則需要允許清單。
3. **搜尋框清除鈕**：`S4_no_match` 的原生 `type=search` 清除鈕為瀏覽器預設藍色，與「黑白為底、單一強調色」不一致（外觀）。
4. **pandas FutureWarning**：`app/services/pandas_store.py:281` 的 `pd.concat` 在每次寫入知識庫時印出空欄或全 NA 欄之 dtype 棄用警告，升級 pandas 後可能改變欄位型別。
5. **測試前置未合入**：`test_ai_provider.py` 的 `--web-search`／`--allowed-domains`（B-02）與 `evaluate.py --timing`（B-23）不在 HEAD，OP-2 記錄項與 PF-1 未命中子準則因此無法依計畫方法執行。
6. **PF-2 未命中之 AI 判定**：兩句貸款話術片段（#13、#18）AI 判 SAFE、unverified，依 FR-16 顯示黃「尚無查核機構證實」而非綠燈；脫離上下文的短句判讀品質供 QA 參考。
7. **提交紀錄**：本代理早期產出的 5 個原始檔（`raw/op2_test_ai_provider_cgu.txt`、`raw/op_startup_health_8030.txt`、`raw/pf3a_threads_sim_rounds.txt`、`raw/pf_frontend_build.txt`、`raw/ui8_source_tiers.txt`）被功能／品質測試代理 03:49 的 commit `b1fc5c3` 一併提交；本代理未執行任何 commit，其餘產出仍為未追蹤檔。

## 8. 資料還原、程序清理與原始輸出

**資料還原**（開工前以 SHA-256 備份至 scratchpad；`data/threads_sim/`、`threads_state.json`、`threads_replies.jsonl` 開工前不存在）：

| 檔案 | 開工前 SHA-256 | 清理前（測試寫入後） | 還原後 |
|------|----------------|----------------------|--------|
| `code/backend/data/knowledge_base.parquet` | `B4F49CD7B9F29451…` | `E64E75F2C7495064…`（03:45 時曾 +15 列、46 列 hit_count 變動；S4 重拍前已還原一次，之後只剩 UI-5 一次 hash 命中的 hit_count 改寫） | `B4F49CD7B9F29451…`（相同；`git diff` 無差異） |
| `code/backend/data/tasks.parquet` | `59074EC3012C4ED0…` | `2435821F8BDEABB8…` | `59074EC3012C4ED0…`（相同） |
| `code/backend/data/factcheck.db` | `880DAB98E5F5F613…` | `880DAB98E5F5F613…`（未變） | `880DAB98E5F5F613…`（相同） |

- 已刪除測試產生的 `data/threads_sim/`（`mentions.json`、`replies.jsonl`）、`data/threads_state.json`、`data/threads_replies.jsonl`；無殘留 `threads_poll.lock`。`data/` 檔案清單與開工前一致；功能代理新增的 `eval_archive_gpt5mini_2026-06/` 與 `eval_*.csv` 變更不屬本代理，未觸碰。
- 知識庫曾在 S4 重拍前先還原一次，`S4_success` 截圖因此為提交種子內容；之後 UI-5 鍵盤測試的 hash 命中又改寫 hit_count，最終再次還原。
- 已停止本代理啟動的所有程序：後端 8030、8031，Vite 5310、5311、5330、5342，headless Edge（含子程序）。負責人的 5173／5179／5199 仍在執行，未觸碰。一次性 `ADMIN_TOKEN` 暫存檔已刪除。

**原始輸出**（`docs/test/results/raw/`，UTF-8）：

| 檔案 | 內容 |
|------|------|
| `op2_test_ai_provider_cgu.txt` | OP-2 腳本完整輸出 |
| `op_startup_health_8030.txt` | 8030 啟動與冒煙檢查（health、stats、trending、knowledge、poll 401、404） |
| `op_backend_runtime_notes.txt` | 8030／8031 啟動時間、啟動 log、存取 log 狀態碼統計 |
| `op7_check_db_before.txt`、`op7_check_db_after.txt` | OP-7 `check_db.py` 前後輸出與 diff |
| `op7_legacy_api_checks.txt`、`op7_legacy_results.txt` | OP-7 舊資料 API 檢查、28 筆舊 completed 任務 fallback 對照 |
| `op7_legacy-fallback-with-frame_375_light.png`、`op7_legacy-fallback-no-frame_375_light.png` | D-1 畫面佐證 |
| `op9_idempotency_rerun_scratch.txt` | OP-9 複本 dry-run／apply×2 輸出與 SHA-256、mtime |
| `pf_requests_2026-09-16.csv` | PF 逐筆請求（section、result_id、cache_layer、用戶端與後端 ms、provider、usd、燈號、來源 tier、離線相似度、原文） |
| `pf_backend_structured_log_8030.txt` | 8030 後端結構化 log 節錄（verification／threads_bot／app.main） |
| `pf3a_threads_sim_rounds.txt` | 3 輪 `--reset-sim`／`--poll` 輸出與時間戳 |
| `pf_frontend_build.txt` | `vite build` 輸出與逐檔大小（含 gzip） |
| `pf_result_api_timing.txt` | 結果頁 API 50 次計時 |
| `opuipf_cgu_usage_snapshots.jsonl` | 本代理 `/me/usage` 6 次快照（僅數值欄位） |
| `ui_dom_audit_summary.txt` | 81 張截圖逐張 DOM 檢查結果 |
| `ui2_ui4_checks.txt` | UI-2（360×780）與 UI-4（主題）程式檢查原始值 |
| `ui5_keyboard_walkthrough.txt` | UI-5 鍵盤預檢逐步紀錄 |
| `ui6_i18n_static_check.txt` | UI-6 §8.7 逐字比對與英文字掃描 |
| `ui8_source_tiers.txt` | UI-8 10 頁來源 tier 複核、S3 無 Google News、未證實橫幅頁 |
