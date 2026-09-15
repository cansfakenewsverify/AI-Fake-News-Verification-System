# 功能測試（3.2）與品質測試（3.5）執行結果

| 項目 | 內容 |
|------|------|
| 對應文件 | `docs/test/TP-FNV-2026-01.md` §3.2、§3.5；`docs/rebuild/01_spec.md` v1.3 §10.2、§10.5、§4.2 通過準則彙總 |
| 執行日期 | 2026-09-16 03:11–03:47（+08:00） |
| 執行者 | Claude（FN／QA 測試代理）；未修改任何程式碼、測試或文件本文，未 commit |
| 受測版本 | `main` @ `c114413`（= `origin/main`，工作樹乾淨時開始） |
| 本機環境 | Windows 11；Python 3.12.9（`code/backend/venv`）、pytest 7.4.3；Node v24.15.0／npm 11.12.1（CI 為 Python 3.12／Node 20） |
| AI 設定（評測） | `AI_PROVIDER=cgu`，provider 鏈 `['cgu']`，`CGU_MODEL=gpt-5.4-mini`，`CGU_REASONING_EFFORT=medium`，`USE_WEB_SEARCH=False`（`evaluate.py` 另固定 `use_web_search=False`）；以上由 `app.config.settings` 印出，未讀 `.env` |
| 原始輸出 | `docs/test/results/raw/`（UTF-8，清單見第 7 節） |

## 1. 結果摘要

| 類別 | P0 | P1 | 說明 |
|------|----|----|------|
| 3.2 功能測試 | 13 項：**通過 12、未通過 1**（FN-4） | 3 項：**未執行 3**（FN-2b、FN-2c、FN-10：功能未實作、無測試） | 全套 477 個 pytest；4 次全套執行中 3 次全綠、1 次有 1 個 Windows 間歇性失敗（見 2.3）；零對外網路呼叫已實測 |
| 3.5 品質測試 | 3 項：**通過 3**（QA-1a、QA-3、QA-5） | 3 項：**通過 1、未通過 2**（QA-2、QA-4） | 新模型 150 筆評測 accuracy 1.000、FN=0、FP=0；CGU 花費 ≤ USD 0.943（上限 USD 1.00 未觸發） |

依 spec §10／§4.2「全部 P0 達標、P1 ≥80%」：本兩類 **P0 有 1 項未達標（FN-4）**、P1 達標率 1／6（17%），兩類合計未達通過準則。FN-4 未達的三項子準則屬票 T-12／T-13，已依 `03_tickets.md` §0.5（負責人選範圍 A）延到報告後；此處仍依準則原文判為未通過。

## 2. 功能測試（3.2）

執行方式：`cd code\backend` → `.\venv\Scripts\python -m pytest tests -q`（全套）＋ 每個 FN 項目對應的測試檔單獨執行（`raw/fn_per_item_pytest.txt`）。

### 2.1 逐項結果

| ID | 優先級 | 結果 | 實測數據 | 證據 |
|----|--------|------|----------|------|
| FN-1 | P0 | 通過 | 8 檔 37 passed。`test_cache_and_store`／`test_marking_rules`／`test_url_validator` 自 2026-07-12 起未改；`test_processor_flow.py`（B-03）與 `test_api.py::test_health_and_root`（B-22，`== {"status":"healthy"}` → `["status"] == "healthy"`）斷言有改，兩者為已登記的 FN-1 例外（B-03 負責人明確同意：`owner_decisions_day0.md` L13；B-22 依 `03_tickets.md` §0 預設同意），但 spec §10.2 FN-1 原文**尚未回寫**這兩項例外。新增測試：文字輸入不呼叫 crawler（`CountingCrawler.calls == 0`）、FR-19 逐字規則字串比對皆在 | `pytest tests/test_ai_service_contract.py tests/test_cache_and_store.py tests/test_marking_rules.py tests/test_api.py tests/test_url_validator.py tests/test_processor_flow.py tests/test_ai_prompt_rules.py tests/test_keyword_search_missing.py -q` → `37 passed in 2.12s`；`raw/fn1_protected_tests_git_history.txt`（`git diff 5536b7f..HEAD`） |
| FN-2a | P0 | 通過 | 53 passed。10 個私網／協定樣本在 `safe_url` 層全部拒絕且 0 請求；3 個公網放行；連線逾時 10 s、總逾時 `CRAWLER_TIMEOUT` 以 mock 驗證；爬取失敗 5 種錯誤碼回 UNVERIFIABLE 且 AI 0 次；非網址 422；同網域來源剔除（含 url／hash／vector 快取命中）。**補充實測**（臨時測試，未提交）：10 樣本逐一打兩個端點——9 個私網樣本兩端點皆 422 `blocked_url`、0 請求、不建任務；協定樣本 `ftp://example.com/file` 在 `/api/analyze/url` 回 422 `invalid_url`（非字面 `blocked_url`），在 `/api/analyze/sync` 不被視為網址而走文字管線（不發請求） | `pytest tests/test_safe_url.py tests/test_analyze_api.py::test_url_invalid_422_invalid_url -q` → `53 passed in 8.87s`；`raw/fn2a_adhoc_endpoint_all10.txt`（`HTTP {422: 19} codes {'blocked_url': 18, 'invalid_url': 1} netguard blocked attempts 0`） |
| FN-2c | P1 | 未執行 | `similar_news` 向量近鄰未實作：`pandas_task_processor.py` L215、L479 固定回 `[]`，現有測試反而斷言 `similar_news == []` | `raw/fn_per_item_pytest.txt` 末段 grep |
| FN-2b | P1 | 未執行 | 無 415／413／bytes hash 測試；`/api/analyze/image` 為舊端點，程式碼無 magic bytes 與 10 MB 檢查（B-26 報告後） | `grep -rn "status_code == 41[35]" tests/` → no matches；`app/api/analyze.py` L345-382 |
| FN-3 | P0 | 通過 | 38 passed。`/api/result/{id}` pending／completed／failed／404／ai_unavailable 五態 schema；threads_sim、`/sync`、`/text`（async）三種來源皆 200；`/health` 含 `scheduler.{enabled,interval_hours}` | `pytest tests/test_result_api.py tests/test_health.py -q` → `38 passed in 2.18s` |
| FN-4 | P0 | **未通過** | 73 passed，但 10 項子準則只有 7 項有測試且通過（文字 mention `threads_len ≤ 400` 含 `/r/`、IMAGE → `reply_media_only`、`get_post` 403 → `reply_cannot_read`、二次 poll 不重複、fallback 不回覆不標記、自我貼文兩種跳過、crash 後 state 已寫入）。**3 項未實作、無測試**：① HTTP 429 → `backoff_until` 設定（實作把 429 當 transient 下輪重試，`threads_bot.py` 沒有任何寫入 `backoff_until` 的程式）；② 未知 4xx → 標 failed 不回覆（實作依 spec §7.5「其他 4xx → unreadable」回 `reply_cannot_read` 並標記，`test_resolve_target_table[400_scalar_replied_to]` 斷言 `unreadable`；與 §7.10／FN-4 原文衝突）；③ container `FINISHED` 才 publish、`ERROR` 重試一次（`threads_service.reply_to` 建 container 後直接 publish，無狀態輪詢）。①② 屬 T-13、③ 屬 T-12 | `pytest tests/test_threads_bot_sim.py -q` → `73 passed in 7.69s`；`tests/test_threads_bot_sim.py` L639-667；`app/workers/threads_bot.py` L185-187；`app/services/threads_service.py` L299-311 |
| FN-5 | P0 | 通過 | 21 passed。七種第一行 ≤400（目標常數 `THREADS_TARGET_LEN = 400`）、連結 ≤2；4 emoji + 200 字與含 ⚠️ 兩個極端案例 ≤500 且保留結果頁連結；「尚無查核機構證實」替代行連結數 = 1；`threads_len` 對 U+26A0／U+FE0F／U+200D 以 bytes 計。**「實測長度規則紀錄欄」空白**：依賴 OP-5 live 實測，尚未執行 | `pytest tests/test_threads_reply_format.py -q` → `21 passed in 0.32s` |
| FN-6 | P0 | 通過 | 23 passed。`frame_of()` 表格 8 列 + 13 組額外輸入（≥11），含 SAFE 0.95 unverified → yellow「尚無查核機構證實」、SAFE 0.95 verified → green、缺 `verification_status` → unverified | `pytest tests/test_verdict.py::test_frame_of_table tests/test_verdict.py::test_frame_of_green_requires_all_three_conditions tests/test_ai_service_contract.py::test_frame_mapping -q` → `23 passed in 1.09s` |
| FN-7 | P0 | 通過 | 8 passed。fallback 同時帶 `ai_unavailable=True` 與 summary 前綴；`scripts/evaluate.py` L28／L48 與 `scripts/test_ai_provider.py` L17／L44 皆改呼叫 `verdict.is_fallback` | `pytest tests/test_verdict.py::test_is_fallback_contract tests/test_verdict.py::test_is_fallback_each_condition tests/test_ai_service_contract.py::test_fallback_summary_prefix_is_stable -q` → `8 passed in 1.04s` |
| FN-8 | P0 | 通過 | 8 passed。`q="("` 200、offset 分頁不重複不遺漏、stats 四格加總 = total、`verified=false` 列不在列表且不計入 total | `pytest tests/test_knowledge_api.py -q` → `8 passed in 3.83s` |
| FN-9 | P0 | 通過 | 10 passed。無／錯 token → 401、`ADMIN_TOKEN` 空或空白 → 403、正確 → 200（trending refresh）與 200／202／409（threads poll），比對用 `hmac.compare_digest` | `pytest tests/test_admin_auth.py -q` → `10 passed in 1.92s` |
| FN-10 | P1 | 未執行 | `DAILY_AI_CALL_CAP` 未實作（`app/` 與 `tests/` 皆無此字串） | `raw/fn_per_item_pytest.txt` 末段 grep |
| FN-11 | P0 | 通過 | 29 passed。同文 hash 命中；「換句話說的輸入」以固定向量走完整管線 `cache_layer == "vector"` 且 AI 0 次（`test_cache_hit_sources_have_tier`）；`verified=false` 列相似度 1.0 仍不命中 vector、hash 仍命中（`test_tier3_only_verified_false_and_vector_miss`） | `pytest tests/test_cache_and_store.py tests/test_kb_write_gate.py -q` → `29 passed in 4.55s` |
| FN-12 | P0 | 通過 | 32 passed。`test_tier_table` 20 組（≥15），含 `gov.tw.evil.com` → 3、`news.google.com/rss` → 3、MyGoPen 任意標題 → 1、ETtoday 查核標題 → 2／一般標題 → 3、offline Cofacts → 3；Cofacts 有回覆 mock → 1、無回覆 → 3、逾時 → 3、offline 不發請求；GraphQL 端點斷言 `https://api.cofacts.tw/graphql`；Tier 2 以 mock 斷言委派 `news_fetcher._title_indicates_debunk` | `pytest tests/test_source_tier.py -q` → `32 passed in 2.71s` |
| FN-13 | P0 | 通過 | 22 passed。FR-17 四組（Tier 1 → true；只有 Tier 3 → false 且 vector 不命中；`sources=[]` + rule → true；Tier 1 但 validator 判死 → false）；`verification_status` 三值；回應 `sources[]` 無 tier 3 | `pytest tests/test_kb_write_gate.py -q` → `22 passed in 3.54s` |
| FN-14 | P0 | 通過 | 11 passed。fixture Parquet 與 SQLite 在 `--dry-run` 後 mtime 與 sha 不變；`--apply` 兩次冪等且有備份；Google News 解析成功（覆寫＋去重）與失敗（刪列）；`label_source="rule"` 永不降級 | `pytest tests/test_clean_sources.py -q` → `11 passed in 2.06s` |

### 2.2 整體目標列（spec §10.2「目標」，非獨立 ID）

| 目標 | 結果 | 實測數據 | 證據 |
|------|------|----------|------|
| P0 測試數 ≥60 | 通過 | 全套收集 477 個測試（31 檔）；僅 FN P0 對應檔即 >300 個 | `raw/fn_pytest_collect.txt` → `477 tests collected in 1.81s` |
| CI 綠燈 | 通過 | 最新 run 35008720030（HEAD `c114413`）success；歷史 22 次全 success | `raw/qa3_gh_run_list.txt` |
| 執行 <60 s | 通過 | 本機 42.20 s／39.42 s／38.85 s／36.45 s；CI「Run unit tests」步驟 19 s | `raw/fn_pytest_full.txt`、`raw/fn_pytest_full_rerun.txt`、`raw/qa3_gh_run_list.txt` |
| 零付費呼叫 | 通過 | 以 pytest 外掛封鎖並記錄所有非 loopback 的 socket 連線與 DNS 查詢，全套 477 passed、攔截 0 次；正向對照（DNS、`requests.get` CGU、直連 1.1.1.1）3 次全被攔截，證明外掛有效 | `raw/fn_pytest_netguard.txt` → `477 passed in 36.45s`、`"blocked_attempt_count": 0`；對照 `blocked_attempt_count = 3` |
| FR-01／02／04～07／09／10／11／16／17／18 每條 ≥1 測試 | 通過 | FR-01 `test_processor_flow`；FR-02 `test_safe_url`；FR-04 `test_result_api`；FR-05 `test_result_api::test_share_text_by_frame` + 前端 `buildThreadsIntent.test.js`；FR-06 `test_sql_migration::test_trending_limit_ge_1` + 前端 `trending.test.js`；FR-07 `test_knowledge_api`；FR-09／10 `test_threads_bot_sim`；FR-11 `test_threads_api::test_status_*`；FR-16 `test_source_tier`；FR-17 `test_kb_write_gate`；FR-18 `test_clean_sources` | `raw/fn_pytest_collect.txt` |

### 2.3 執行紀錄

| 動作 | 結果 | 證據 |
|------|------|------|
| 後端全套 #1（03:14） | `1 failed, 476 passed, 440 warnings in 42.20s`；失敗：`tests/test_parquet_io.py::test_concurrent_task_updates_do_not_lose_writes_or_break_reads`，`AssertionError: assert [PermissionError(13, '存取被拒。')] == []` | `raw/fn_pytest_full.txt` |
| 同檔單獨重跑 10 次 | 10／10 `5 passed` | `raw/fn_pytest_parquet_io_rerun.txt` |
| 後端全套 #2、#3、netguard | `477 passed`（39.42 s／38.85 s／36.45 s） | `raw/fn_pytest_full_rerun.txt`、`raw/fn_pytest_netguard.txt` |
| 前端 `npm run lint` | exit 0（eslint 無輸出） | `raw/fe_npm_run_lint.txt` |
| 前端 `npm run build` | exit 0；vite v8.3.0，113 modules，`dist/assets/index-Zf5TthD4.js 369.50 kB`，built in 598ms | `raw/fe_npm_run_build.txt` |
| 前端 `npm run test:unit` | `tests 375 / pass 375 / fail 0` | `raw/fe_npm_run_test_unit.txt` |
| `gh run list --limit 3` | 3 筆皆 `completed success`（35008720030、35008438974、34998460386） | `raw/qa3_gh_run_list.txt` |

判讀：`test_parquet_io` 的並發測試在 Windows 上為間歇性失敗（4 次全套中 1 次；`os.replace` 或讀取遇到檔案被占用，重試預算約 1.6 s 用盡）。CI 跑在 Linux（無此檔案鎖語意）抓不到；它影響 spec §10「再繼續條件：`pytest tests` 全綠」在負責人 Windows 電腦上的穩定性。每次全套前後三個受保護資料檔雜湊不變（`raw/fn_pytest_full.txt`、`raw/fn_pytest_full_rerun.txt`）。

## 3. 品質測試（3.5）

### 3.1 逐項結果

| ID | 優先級 | 結果 | 實測數據 | 證據 |
|----|--------|------|----------|------|
| QA-1a | P0（閘門） | 通過 | CGU `gpt-5.4-mini`（鏈 `['cgu']`）150 筆，有效 150、分析失敗 0：**FN = 0**。跑前後已查 `/me/usage`（4.5 節）。**與準則文字的偏差**：依本次任務指示**未加 `--seed-db`**（避免寫入正被其他代理使用的知識庫）；`--seed-db` 只影響「判對案例寫入知識庫」，不影響預測與指標 | `raw/qa1_evaluate_run.txt` → `TP=100  FP(偽陽性/誤報)=0  FN(偽陰性/漏報)=0  TN=50`；`code/backend/data/eval_binary.csv` |
| QA-1b | P1（量測） | 通過 | accuracy **1.000**（目標 ≥0.93）、FP **0**（目標 ≤8）；macro-F1 1.000。舊／新數字並列與錯誤分析見第 4 節 | `raw/qa1_evaluate_run.txt` → `整體準確率 Accuracy : 1.000`；`code/backend/data/eval_report.csv`；`raw/qa1_old_vs_new_comparison.txt` |
| QA-2 | P1 | **未通過** | ① `--report-only` 重算一致：`eval_report.csv`、`eval_binary.csv`、`confusion_matrix.png` 重算前後 sha256 完全相同（通過）。② 報告無 `provider/model/date/use_web_search` 欄、預測檔無 `elapsed_ms`、`evaluate.py` 無 `--timing`（未通過；B-23 報告後）。③ `eval_errors.csv`：程式對每筆錯誤寫 `error_type`，但**錯誤 0 筆時 `_save_error_cases` 直接 return、不重寫檔案**，現存檔仍是舊模型 6 筆（sha256 與封存檔相同、mtime 2026-06-06），與新報告矛盾（未通過） | `raw/qa2_report_only.txt`（前後 sha256、表頭 `label,precision,recall,f1,support`／`id,gold,pred,confidence,correct,errored,content`）；`raw/qa1_post_run_checks.txt` → `eval_errors.csv ... IDENTICAL to archive (NOT rewritten)`；`scripts/evaluate.py` L224-228 |
| QA-3 | P0 | 通過 | 最新 run 35008720030（HEAD `c114413`）：`test` job（pytest，19 s）與 `frontend` job（npm ci、build、unit tests）皆 success；歷史 22 次全 success，其中 2026-09-14 起 15 次、0 次失敗；`ci.yml` 無寫死測試數 | `raw/qa3_gh_run_list.txt`；`.github/workflows/ci.yml`（grep 無測試數字） |
| QA-4 | P1 | **未通過** | `.env.example` 對應項全數一致；`CLAUDE.md` 與 `README.md` 在勾核表 8 個指定項目**全部不符**，另缺 spec 新端點／設定名，勾核表交付物 `docs/test/doc_review.md` 不存在（逐項見 3.2）。與 `03_tickets.md` L2414「QA-4（P1）本週未達標、B-25 報告後」一致 | `raw/qa4_doc_review_grep.txt` |
| QA-5 | P0 | 通過 | 引用 `docs/test/clean_sources_review.md`（D-05 已套用，負責人核准 1a 2a 3a）。**數字對資料實測一致**：知識庫種子（git HEAD `db8c62d`）218 筆、verified 128（MISINFO 75／SCAM 29／SAFE 24）、未證實 90；熱門牆（`factcheck.db` 唯讀副本）24 筆、verified 24、`news.google.com` 0；清洗前後 236 → 218、63 → 24。第二次 apply 各規則影響 0（冪等）、`label_source=rule 被降級：0 筆`。證據缺口見下方附註 | `raw/qa5_data_verification.txt`；`code/backend/data/clean_sources_report.txt` L7-L13、L30-L35；`code/backend/data/check_before_d05.txt`、`check_after_d05.txt` |

QA-5 附註（證據缺口，不改判定，供負責人知悉）：
1. 審閱文件寫「其中 113 筆有向量可參與語意命中」；實測 128 筆 verified 中有向量 113 筆，但只有 **102 筆是 1536 維**，另 11 筆為 768 維（5）／3072 維（6），`find_similar_by_vector` 只比對同維度（`pandas_store.py` L199），實際可參與語意命中為 102 筆。
2. 目前 `clean_sources_report.txt` 是第二次 apply 的報告（各規則影響 0），dry-run 的逐筆 before→after、Cofacts 逐筆與 Google News 31 筆逐筆結論已被覆寫；現存報告列 Cofacts 23 篇（有回覆 19／無回覆 4），`clean_sources_cache.json` 27 筆，無法再以現存檔案核對準則中的「Cofacts 33 筆」。Google News 31 筆依決定 1a 全刪，`check_after_d05.txt` 顯示 0 筆。
3. 準則「隨機抽 10 筆降級列由負責人逐筆判斷，同意 ≥9」：審閱文件記錄的是負責人對三項決定的整體核准與本地模型 300 筆第二意見，**未見 10 筆逐筆判斷紀錄**。
4. 知識庫沒有 rule／gold／admin 列，「rule 被降級 0 筆」對知識庫為空集合檢核（報告 L14 已自行註明）；熱門牆 rule 列 25 → 15：與清洗前備份 `factcheck.db.bak-20260916` 比對，共刪 39 列（Google News 31＋髒資料 8），其中 rule 列 10 筆全是決定 1a 刪除的 `news.google.com` 列（刪除，非降級），留存的 15 筆 rule 列皆 verified。

### 3.2 QA-4 文件審查勾核表

| # | 勾核項目（spec §10.5 QA-4） | CLAUDE.md | README.md | .env.example | 判定 |
|---|------------------------------|-----------|-----------|--------------|------|
| 1 | Threads 權限清單修正（四權限含 `threads_manage_mentions`，不含 `threads_read_replies`） | 不符：§11 L357-359 仍列 `threads_read_replies`、無 `threads_manage_mentions`（僅 §8 待辦 L320 提及） | 未列權限 | 符合：L53-54 四權限正確 | 不符 |
| 2 | §2 表格「影片語音轉文字」列刪除 | 不符：L47 仍在 | — | — | 不符 |
| 3 | 移除 `ENABLE_THREADS_BOT`／STT 設定鍵 | 不符：L47 `STT_MODEL`／`CGU_STT_MODEL`、L362 `ENABLE_THREADS_BOT=true` | 不符：L172 `ENABLE_THREADS_BOT`、L49「whisper 逐字稿」 | 符合：兩者皆無 | 不符 |
| 4 | `legacy/` 標示 | 不符：§1 L25-26、§4 L163-167 仍寫根目錄 `fake-news-detector.html`／`_run_detector.bat`（實際只在 `legacy/`） | 符合：L38、L70、L85 | — | 不符 |
| 5 | §2 AI 引擎改寫為「CGU AIR 唯一 provider、myai168 已停用、額度查 `/me/usage`」 | 不符：L35-51 仍為「保留 myai168、新增 CGU」與三 provider 備援鏈；額度寫 $20（`/me/usage` 實回 `quota_usd: 10.0`） | 不符：L10、L36、L50、L63、L166-167 多 provider；L64 仍寫「Gemini 備援」 | 符合：L1-30 只留 CGU，myai168 在「已停用」註解區 | 不符 |
| 6 | §9 加來源分級三條規則（Tier 定義、只顯示 Tier 1／2、寫入門檻） | 不符：§9 L324-335 無 Tier 規則（僅 §4 L135 檔案地圖一行） | 無 | — | 不符 |
| 7 | `BOT_HANDLE=factcheck_tw_bot` | 不符：0 處 | 不符：0 處 | 符合：L70 | 不符 |
| 8 | §4／§7「runtime 變動不用 commit」補 FR-18 種子例外 | 不符：§4 L154-155 仍寫「已提交 178 筆 demo 種子…變動不用 commit」（種子現為 218 筆），§7 L231「runtime 檔（`*.db`、`*.parquet`）已 gitignore，不要提交」與 `.gitignore`（`knowledge_base.parquet` 不忽略、為種子）矛盾，無例外說明 | — | — | 不符 |
| 9 | 端點／設定名與 spec 一致 | 不符：`/api/result`、`/api/threads/replies`、`/api/health` 0 處；`THREADS_MODE`、`PUBLIC_BASE_URL`、`ADMIN_TOKEN`、`CONTACT_EMAIL`、`BRAND_NAME`、`THREADS_APP_ID`、`AI_TIMEOUT_SECONDS`、`WEB_SEARCH_ALLOWED_DOMAINS` 0 處；§4 仍列已刪的 `scripts/seed_data.py`；「31 tests」（實際 477）；§7「AI 呼叫 timeout 150s」（`config.py` 為 60） | 不符：上述端點與設定 0 處；「31 個單元測試」；L66 Playwright／yt-dlp（已移除） | 符合：上述設定皆有；spec §7.11 要求移除的 `ENABLE_THREADS_BOT`、`SERPER_API_KEY`、`GOOGLE_API_KEY`、`EMBEDDING_MODEL`、`STT_MODEL`、`CGU_STT_MODEL`、`CRAWL_WITH_SCREENSHOT`、`SEARCH_RESULTS_LIMIT` 皆不存在；`THREADS_BASE_URL` 已補 | 不符 |
| 10 | 勾核表交付物 `docs/test/doc_review.md`（spec §10.6 4.4） | — | — | — | 不存在 |

補充（設定名不一致，影響成本推估）：spec §9 成本列寫「`OPENAI_REASONING_EFFORT=low`」，但 provider `cgu` 實際讀的是 `CGU_REASONING_EFFORT`（`.env.example` 與執行時皆為 `medium`），本次評測即以 `medium` 執行。

## 4. 評測：舊模型 vs 新模型（QA-1a／QA-1b）

### 4.1 執行條件

| 項目 | 舊模型（封存） | 新模型（本次） |
|------|----------------|----------------|
| Provider／模型 | myai168／`gpt-5-mini` | CGU AIR Gateway／`gpt-5.4-mini`（鏈 `['cgu']`） |
| 日期 | 結果於 2026-06-06 提交（git `9d63eef`）；spec D-8 記為「2026-07」 | 2026-09-16 03:14:22–03:29:32（+08:00） |
| 推理強度 | 未記錄 | `CGU_REASONING_EFFORT=medium` |
| web_search | 關（該版 `evaluate.py` L50 `use_web_search=False`） | 關（`evaluate.py` L47 `use_web_search=False`） |
| 指令 | `evaluate.py`（`--seed-db` 與否未記錄） | `cd code\backend` → `.\venv\Scripts\python scripts\evaluate.py --delay 0`（無 `--seed-db`；單次連續執行，未中斷、未用 `--resume`） |
| 資料集 | `data/eval_set.csv` 150 筆（SCAM／MISINFO／SAFE 各 50） | 同一檔 |
| 有效／分析失敗 | 150／0 | 150／0 |
| 耗時 | 未記錄 | 約 15 分 10 秒（循序，平均約 6.1 s／筆，含程序啟動；無逐筆 `elapsed_ms`） |
| 封存位置 | `code/backend/data/eval_archive_gpt5mini_2026-06/`（`eval_report.csv`、`eval_binary.csv`、`eval_errors.csv`、`eval_predictions.csv`、`confusion_matrix.png`，sha256 與原檔逐一相同） | `code/backend/data/eval_report.csv`、`eval_binary.csv`、`eval_predictions.csv`、`assets/confusion_matrix.png`（已重寫）；`eval_errors.csv` **未重寫、仍為舊內容**（見 QA-2） |

### 4.2 指標並列

| 指標 | 舊：gpt-5-mini（myai168，2026-06） | 新：gpt-5.4-mini（CGU AIR，2026-09-16） | 目標 |
|------|------------------------------------|------------------------------------------|------|
| Accuracy | 0.960（144／150；95% CI 0.915–0.985） | **1.000**（150／150；95% CI 0.976–1.000） | ≥0.93（QA-1b） |
| Macro-F1 | 0.960 | **1.000** | — |
| SCAM P／R／F1 | 0.893／1.000／0.943 | 1.000／1.000／1.000 | — |
| MISINFO P／R／F1 | 1.000／0.980／0.990 | 1.000／1.000／1.000 | — |
| SAFE P／R／F1 | 1.000／0.900／0.947 | 1.000／1.000／1.000 | — |
| 二分類 TP／FP／FN／TN | 100／5／0／45 | 100／**0**／**0**／50 | FN = 0（QA-1a）；FP ≤8（QA-1b） |
| FPR／FNR | 0.100／0.000 | 0.000／0.000 | — |
| 信心分數 中位數／最小值 | 0.90／0.60 | 0.97／0.68 | — |
| 花費 | 未記錄（myai168 點數） | ≤ USD 0.943（約 USD 0.0063／筆） | 150 筆 ≤ USD 1.5（PF-5） |

95% CI 為 Clopper-Pearson 精確區間。成對比較：兩模型判定不同的 6 筆全部是「舊錯新對」、0 筆「舊對新錯」，精確 McNemar 檢定雙尾 p = 0.031（`raw/qa1_old_vs_new_comparison.txt`）。

### 4.3 混淆矩陣（列 = 真實，欄 = 預測）

舊模型（gpt-5-mini）：

| 真實＼預測 | SCAM | MISINFO | SAFE |
|-----------|------|---------|------|
| SCAM | 50 | 0 | 0 |
| MISINFO | 1 | 49 | 0 |
| SAFE | 5 | 0 | 45 |

新模型（gpt-5.4-mini）：

| 真實＼預測 | SCAM | MISINFO | SAFE |
|-----------|------|---------|------|
| SCAM | 50 | 0 | 0 |
| MISINFO | 0 | 50 | 0 |
| SAFE | 0 | 0 | 50 |

圖檔：新 `assets/confusion_matrix.png`（已目視確認三格對角 50）；舊 `code/backend/data/eval_archive_gpt5mini_2026-06/confusion_matrix.png`。

### 4.4 錯誤清單摘要

舊模型 6 筆錯誤（封存 `eval_errors.csv`），新模型對同 6 筆的判定：

| id | 真實 | 舊預測（信心） | 錯誤類型（舊） | 題目備註 | 新預測（信心） |
|----|------|----------------|----------------|----------|----------------|
| 96 | MISINFO | SCAM（0.90） | 類別混淆 | 愛心轉傳騙局 | MISINFO（0.88） |
| 107 | SAFE | SCAM（0.90） | 偽陽性 FP | 官方反詐宣導 | SAFE（0.98） |
| 126 | SAFE | SCAM（0.95） | 偽陽性 FP | 真實疫情警示_易誤判恐慌 | SAFE（0.97） |
| 127 | SAFE | SCAM（0.90） | 偽陽性 FP | 真實反詐宣導 | SAFE（0.93） |
| 131 | SAFE | SCAM（0.95） | 偽陽性 FP | 真實政府補助_易誤判詐騙 | SAFE（0.97） |
| 140 | SAFE | SCAM（0.90） | 偽陽性 FP | 真實政策_含防詐提醒 | SAFE（0.93） |

新模型錯誤清單：**0 筆**（`(無判錯案例)`）。舊模型的錯誤型態（對詐騙字眼過度反應，把反詐宣導、政府補助公告判成 SCAM）在新模型上未再出現。新模型信心較低的 2 筆皆判對：id 124（SAFE，官方政策）信心 0.68、id 114（SAFE，官方藝文資訊）信心 0.78；其中 id 124 低於綠燈門檻 `GREEN_MIN_CONFIDENCE = 0.7`，在產品上會顯示黃燈「尚待確認」而非綠燈。

### 4.5 成本與用量（CGU `GET {CGU_BASE_URL}/me/usage`，openai 池）

| 時點 | requests | prompt_tokens | completion_tokens | cost_usd | remaining_usd（quota 10.0） |
|------|----------|---------------|-------------------|----------|------------------------------|
| 評測前 03:14:22 | 53 | 6,566 | 6,309 | 0.155421 | 9.844579 |
| 評測後 03:29:39 | 268 | 214,500 | 79,119 | 1.119426 | 8.880574 |
| 差額 | +215 | +207,934 | +72,810 | **+0.964005** | −0.964005 |

- 同一把 CGU 金鑰在評測期間另有其他代理的後端呼叫：差額 215 次中 150 次為評測、65 次為其他（平均每次約 290 prompt tokens；由逐區間 token 與金額推斷幾乎沒有輸出 token，研判為 embedding 型呼叫）。
- 本評測自身花費：閘道計價在無外部流量的區間精確符合「輸入 USD 1.5／百萬 tokens + 輸出 USD 9／百萬 tokens」，以此估算上限（把池內全部輸出 token 都算給評測）為 **USD 0.943**，約 USD 0.0063／筆；池總差額 USD 0.964。兩者皆未超過本次上限 USD 1.00，也在 PF-5 目標（150 筆 ≤ USD 1.5、每次 ≤ USD 0.02）內。
- 預算看門狗：原以「池總差額 > USD 1.00 即中止」監看；約第 123 筆時發現他人流量會灌高總差額、可能在最後幾筆誤中止，改以「評測自身花費上限估算 > USD 1.00 即中止」接手監看（evaluate.py 程序未中斷）。逐次紀錄：`raw/qa1_cgu_usage.jsonl`（已去除帳號個資，不含金鑰）。

### 4.6 解讀與限制

1. 新模型在本評測集上滿分，FN 與 FP 皆為 0，QA-1a 閘門與 QA-1b 目標均達標。
2. 兩次並非只換模型：閘道（myai168 → CGU AIR）、推理強度（未記錄 → medium）與時間都不同，差異不能全歸因於模型本身。
3. 150 筆、滿分代表此評測集對新模型已飽和（accuracy 95% CI 下限 0.976）；要再區分模型或設定（如 PF-6 `gpt-5.4`、`CGU_REASONING_EFFORT=low`），需要更難或更大的題庫（CLAUDE.md §8 選項：擴充到 300 筆）。評測集自 2026-06 起公開在 repo，無法排除被新模型見過的可能。
4. 本次未量測逐筆延遲（`--timing` 未實作），PF-1 未命中 p50／p90 無法由此次資料計算；平均約 6.1 s／筆僅供參考。
5. 引用 `eval_errors.csv` 前須先處理 QA-2 的舊檔問題，否則會把舊模型 6 筆誤當成新結果。

## 5. 資料完整性與執行偏差

- **evaluate.py 未寫知識庫**：無 `--seed-db` 時 `run_predictions` 不建立 `PandasStore`（`evaluate.py` L76-L80、L106），執行紀錄無任何 `[seed-db]` 行。
- **`git status` 顯示 `knowledge_base.parquet` 已修改，但來源不是本次評測**：03:30 查得 `M code/backend/data/knowledge_base.parquet`（mtime 03:28:13.316）與 `tasks.parquet`（mtime 03:28:13.395，同一秒；evaluate.py 從不寫 tasks.parquet）。對快照副本與 git HEAD 比對：新增 13 列、刪除 0 列，建立時間 03:24:25–03:28:02，**0 列是 eval_set 題目**、7 列是其他代理 PF-2 用的 `docs/test/pf2_paraphrases.csv` 文字，`label_source` 為 ai 12／gold 1。同時段有其他代理的 uvicorn 後端在 `127.0.0.1:8030` 執行。依任務說明由該代理負責還原資料檔；本代理未寫入、未還原這三個檔案。證據：`raw/qa1_post_run_checks.txt`。
- `factcheck.db` sha256 全程不變（`880dab98…`，mtime 為 D-05 apply 的 00:07:36）；後端全套 pytest #1～#3 前後三檔雜湊皆不變。
- 為做 QA-5 核對，曾對 `knowledge_base.parquet` 與 `factcheck.db` 各做一次唯讀複製到暫存區再計算，未寫回。
- 其他偏差：QA-1a 未加 `--seed-db`（任務指示）；FN-2a 另跑一個不提交的臨時端點測試；零付費呼叫以臨時 pytest 外掛驗證；上述輔助腳本都放在 session 暫存區，未進 repo。
- 本代理新增到 repo 的檔案只有：`code/backend/data/eval_archive_gpt5mini_2026-06/`（5 個封存檔）與 `docs/test/results/`（本檔與 raw/）；另 `evaluate.py` 依設計重寫了 4 個評測輸出檔。

## 6. 發現事項（未修正，供負責人決定）

| # | 嚴重度 | 發現 | 建議 |
|---|--------|------|------|
| 1 | P0 準則 | FN-4 三項子準則未實作：429 → `backoff_until`、未知 4xx → failed 不回覆、container `FINISHED`／`ERROR` 重試（T-12／T-13 延到報告後）；另 spec §7.5「其他 4xx → unreadable」與 §7.10／FN-4「未知 4xx → failed 不回覆」互相矛盾 | 報告前若要宣稱 P0 全達標，需完成 T-12／T-13 或由負責人正式把這三項標為範圍 A 例外；並統一 §7.5 與 §7.10 |
| 2 | 中 | Windows 上 `test_parquet_io.py::test_concurrent_task_updates_do_not_lose_writes_or_break_reads` 間歇性失敗（4 次全套 1 次，`PermissionError 13`）；CI 為 Linux 抓不到 | 加大 `parquet_io` 重試預算或讓測試容忍 Windows 檔案占用，避免「pytest 全綠」再繼續條件在本機誤判 |
| 3 | 中 | `evaluate.py` 在 0 筆錯誤時不重寫 `eval_errors.csv`，舊模型 6 筆殘留；報告缺 provider／model／date／use_web_search／elapsed_ms 欄與 `--timing`（B-23） | 0 筆時輸出只有表頭的檔；完成 B-23 後再以 `--report-only` 補欄位 |
| 4 | 低 | spec §10.2 FN-1 原文未回寫 B-03、B-22 兩項已同意的斷言例外（B-22 為預設同意） | 回寫 spec，或由負責人補明確同意 |
| 5 | 低 | spec §9 以 `OPENAI_REASONING_EFFORT=low` 推估成本，但 cgu 讀 `CGU_REASONING_EFFORT`（實際 medium）；本次每筆約 USD 0.0063 | 在 spec／`.env.example` 統一鍵名，若要省成本改 `CGU_REASONING_EFFORT` |
| 6 | 低 | QA-4：CLAUDE.md、README 大量過時（多 provider、STT、`ENABLE_THREADS_BOT`、權限清單、legacy 路徑、測試數、timeout、種子 commit 規則）且缺 `doc_review.md` | B-25 |
| 7 | 低 | QA-5 證據缺口：dry-run 逐筆報告已被 apply 覆寫；無 10 筆逐筆負責人判斷紀錄；「113 筆帶向量」實際可參與語意命中為 102 筆 | 若報告要引用 QA-5，補存 dry-run 報告與抽樣判斷紀錄，並更正向量數或重算 11 筆非 1536 維向量 |
| 8 | 資訊 | FN-2a：協定樣本 `ftp://` 在 `/api/analyze/url` 回 422 `invalid_url`（非 `blocked_url`），在 `/sync` 視為文字；兩者皆無對外請求 | 確認 spec 是否要求字面 `blocked_url` |
| 9 | 資訊 | FN-5「實測長度規則紀錄欄」待 OP-5 live 實測；新模型 id 124 信心 0.68 < 0.7，產品會顯示黃燈 | — |

## 7. 原始輸出檔（`docs/test/results/raw/`，UTF-8）

| 檔名 | 內容 |
|------|------|
| `fn_pytest_full.txt` | 後端全套 #1（含前後受保護檔 sha256、失敗 traceback） |
| `fn_pytest_full_rerun.txt` | 後端全套 #2、#3 |
| `fn_pytest_parquet_io_rerun.txt` | `test_parquet_io.py` 單獨重跑 10 次 |
| `fn_pytest_collect.txt` | `--collect-only`，477 個測試 ID |
| `fn_pytest_netguard.txt` | 封鎖對外網路的全套執行 + 正向對照 |
| `fn_per_item_pytest.txt` | FN-1～FN-14 逐項測試檔執行；FN-2b／2c／10 grep |
| `fn1_protected_tests_git_history.txt` | FN-1 五個不得改斷言檔案的 git log／diff |
| `fn2a_adhoc_endpoint_all10.txt` | FN-2a 10 樣本 × 2 端點臨時實測 |
| `fe_npm_run_lint.txt`、`fe_npm_run_build.txt`、`fe_npm_run_test_unit.txt` | 前端三個指令 |
| `qa1_evaluate_run.txt` | `evaluate.py --delay 0` 完整輸出（含看門狗標記） |
| `qa1_cgu_usage.jsonl` | 評測前／中／後 `/me/usage`（每 15–30 秒，已去除帳號資訊） |
| `qa1_post_run_checks.txt` | 評測後 git status、檔案雜湊、預測檔與執行紀錄一致性、知識庫變動歸因 |
| `qa1_old_vs_new_comparison.txt` | 舊新混淆矩陣、逐筆差異、信賴區間、McNemar |
| `qa2_report_only.txt` | `--report-only` 前後 sha256、表頭欄位、`--help` |
| `qa3_gh_run_list.txt` | `gh run list --limit 3` 與唯讀補充查詢（jobs、步驟時間、歷史結論） |
| `qa4_doc_review_grep.txt` | QA-4 勾核用 grep（含行號） |
| `qa5_data_verification.txt` | QA-5 數字核對（種子、熱門牆、向量維度、與清洗前備份比對的刪除列歸因） |

同資料夾內的 `op2_test_ai_provider_cgu.txt`、`op_startup_health_8030.txt`、`pf3a_threads_sim_rounds.txt`、`pf_frontend_build.txt` 由同時進行操作／績效測試的其他代理寫入，不屬本報告證據。本報告所有 raw 檔已掃描：不含 CGU 金鑰、不含帳號識別資訊。
