# Graph Report - code  (2026-10-30)

## Corpus Check
- 284 files · ~160,774 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 35 file(s) not represented in the graph (top: .csv 21, (none) 6, .bat 2)

## Summary
- 3749 nodes · 10419 edges · 144 communities (123 shown, 21 thin omitted)
- Extraction: 93% EXTRACTED · 7% INFERRED · 0% AMBIGUOUS · INFERRED: 742 edges (avg confidence: 0.87)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- 機器人模擬測試輔助
- 首頁與共用元件
- 每週評測測試
- Threads 模擬服務
- Threads API 端點測試
- 熱門頁與後端狀態
- store 工廠
- 熱門牆資料表
- Postgres store 契約測試
- 三層快取主流程
- 結果頁判定畫面
- 分析 API 端點
- 健康檢查與熱門查證測試
- 本機知識庫 store
- Threads 發佈測試
- 後端入口與設定
- 前端 API 客戶端
- 證據信心
- RSS 搜尋與未證實盤點
- Parquet 讀寫與本機 store
- 機器人退避與時間
- PF-2 測試與向量服務
- 機器人固定回覆文案
- 前端建置設定
- 清洗腳本測試
- 查核結論同步
- Postgres 連線與機器人狀態
- AI 服務呼叫
- 每 IP 限速
- 導覽列與文案
- SSRF 防護與爬蟲
- Threads API 客戶端
- 知識庫寫入門檻測試
- 結果頁狀態與輪詢
- 分享文案與網址
- 內容 hash 與管理權限
- 來源分級與網域比對
- 熱門牆流程
- 資料清洗腳本
- Threads 授權與 token
- 設定與健康檢查測試
- TFC 與 MyGoPen 解析
- 本機任務 store
- Threads token 測試
- 燈號與 fallback 契約
- Postgres 欄位轉換
- 機器人輪詢迴圈
- 機器人處理提及
- 網址輸入流程測試
- 來源分級
- 機器人狀態 API
- 搬資料到 Supabase
- 查核資料批次入庫
- 燈號與 fallback 契約（2）
- 結果頁動作與相似查證
- 輪詢鎖與觸發
- 查核機構語料收錄
- 送出查證 hook
- 本機資料檢查
- 任務 store 與結果 API 測試
- 上線護欄測試
- Threads 回覆格式
- 機器人檔案鎖
- 分析 API 測試
- 查核結果回補測試
- 知識庫頁
- 評測腳本
- 知識庫 API
- 每日上限測試
- 輪詢狀態記帳
- Threads 授權測試
- 查核結論同步（2）
- 每日 AI 次數上限
- 發佈間諜測試
- 機器人回覆紀錄
- 機器人測試腳本
- 機器人測試腳本（2）
- 舊證據重新比對測試
- embedding 與模型下架處理
- Postgres 稽核 store
- 雲端機器人測試
- 內容 hash 與管理權限（2）
- UI 檢核表腳本
- UI 截圖腳本
- 發佈與錯誤分類
- 評測計時測試
- 知識庫 API 測試
- 文字輸入不爬取測試
- 標題主張修正腳本
- Threads 回覆格式（2）
- 處理流程測試
- 回應大小限制測試
- 本機查證歷史
- 機器人狀態頁
- 資料清洗腳本（2）
- Threads API 測試夾具
- 網址爬蟲
- 深淺色主題
- 管理端點報告
- Docker 設定
- 熱門牆抓取測試
- Threads HTTP 請求
- 死連結過濾
- 向量重算腳本
- HTML 轉 PDF 腳本
- 上線護欄測試（2）
- 熱門牆抓取測試（2）
- SSRF 測試
- Postgres 連線與機器人狀態（2）
- Postgres 任務 store
- 兩段式發佈
- 主張文字前處理
- 知識庫單筆更正腳本
- 評測計時測試（2）
- 評測計時測試（3）
- 熱門牆抓取測試（3）
- 輪詢逾時測試
- 機器人固定回覆文案（2）
- 輪詢鎖測試
- 機器人退避測試
- 機器人模擬測試輔助（2）
- 假 Graph API
- 熱門牆抓取測試（4）
- Google News 轉址
- 標記規則
- AI 逾時與提示規則
- 管理 token 腳本測試
- 手動觸發輪詢
- token 讀取來源
- 管理 token 補值
- 熱門牆抓取測試（5）
- 授權測試夾具
- 評測計時測試（4）
- 熱門牆抓取測試（6）
- SSRF 測試夾具
- Vercel 代理設定

## God Nodes (most connected - your core abstractions)
1. `PandasStore` - 119 edges
2. `t()` - 118 edges
3. `TaskStore` - 86 edges
4. `_poll()` - 79 edges
5. `_set_mentions()` - 74 edges
6. `ThreadsService` - 70 edges
7. `_state()` - 67 edges
8. `AIService` - 56 edges
9. `CacheService` - 51 edges
10. `_sim_replies()` - 48 edges

## Surprising Connections (you probably didn't know these)
- `test_settings_class_defaults_are_local()` --uses--> `Settings`  [INFERRED]
  backend/tests/test_store_factory.py → backend/app/config.py
- `test_fake_implements_protocol()` --uses--> `ThreadsClient`  [INFERRED]
  backend/tests/test_threads_bot_sim.py → backend/app/services/threads_service.py
- `trigger_refresh()` --indirect_call--> `run_trending_fetch()`  [INFERRED]
  backend/app/api/trending.py → backend/app/services/news_fetcher.py
- `get_pg_engine()` --indirect_call--> `engine()`  [INFERRED]
  backend/app/database_sql.py → backend/tests/test_ai_budget.py
- `lifespan()` --indirect_call--> `init_sql_db()`  [INFERRED]
  backend/app/main.py → backend/app/database_sql.py

## Import Cycles
- None detected.

## Communities (144 total, 21 thin omitted)

### Community 0 - "機器人模擬測試輔助"
Cohesion: 0.08
Nodes (71): _assert_backoff(), _backoff_minutes_left(), _edit_container(), _edit_mentions(), _expire_backoff(), _inject(), fn(), _mention() (+63 more)

### Community 1 - "首頁與共用元件"
Cohesion: 0.08
Nodes (44): Button(), Spinner(), VARIANT, Card(), ConfirmDialog(), handleClose(), reportCancel(), autoGrow() (+36 more)

### Community 2 - "每週評測測試"
Cohesion: 0.06
Nodes (45): trigger_weekly_eval(), _cap(), fresh_items(), history_items(), history_risky_rows(), _item(), _judge(), _md5_key() (+37 more)

### Community 3 - "Threads 模擬服務"
Cohesion: 0.07
Nodes (23): ThreadsApiError, FakeThreadsService, _replied_to_id(), _read_lines(), test_bot_replies_normally_when_quota_lookup_fails(), broken(), test_fake_container_cache_sees_external_edits_and_deletion(), test_fake_container_error_injection_points_and_text_condition() (+15 more)

### Community 4 - "Threads API 端點測試"
Cohesion: 0.05
Nodes (42): _auth(), client(), _copy_example_mentions(), _DownHttp, _fresh_lock(), _kb(), _lines(), _mentions_only() (+34 more)

### Community 5 - "熱門頁與後端狀態"
Cohesion: 0.09
Nodes (45): EmptyState(), MARKS, HEALTH_RETRY_MS, isBackendDownError(), retryOnBackendUp(), startHealthRetry(), fakeClock(), clock (+37 more)

### Community 6 - "store 工廠"
Cohesion: 0.06
Nodes (29): AdminOverrideRequest, _mark_admin(), _mark_kb_row_admin(), override_task_result(), FeedbackRequest, submit_feedback(), _search_path_sql(), _get() (+21 more)

### Community 7 - "熱門牆資料表"
Cohesion: 0.05
Nodes (32): get_trending(), _is_cofacts(), trigger_refresh(), _db_secrets(), get_sql_db(), reset_pg_engine(), FactCheckRecord, _is_non_factcheck_post() (+24 more)

### Community 8 - "Postgres store 契約測試"
Cohesion: 0.08
Nodes (39): PgTaskStore, _ai(), audit(), _build_local_data(), kb(), kb_pg(), _leaks_credentials(), _load_migrate_module() (+31 more)

### Community 9 - "三層快取主流程"
Cohesion: 0.08
Nodes (34): _build_result(), _call_ai_within_budget(), _coerce_tier(), _complete(), _crawl_failure_explanation(), _drop_same_domain_sources(), _estimate_usd(), _evidence_inputs() (+26 more)

### Community 10 - "結果頁判定畫面"
Cohesion: 0.10
Nodes (41): Banner(), TONES, Disclosure(), DotRow(), metaText(), TITLE_CLAMP, ALIASES, Icon() (+33 more)

### Community 11 - "分析 API 端點"
Cohesion: 0.08
Nodes (24): AnalysisResult, analyze_image(), analyze_sync(), analyze_text(), analyze_url(), AnalyzeResponse, AnalyzeTextRequest, api_error() (+16 more)

### Community 12 - "健康檢查與熱門查證測試"
Cohesion: 0.06
Nodes (22): rank(), base_settings(), cgu_only(), client(), network_calls(), test_api_health_alias_same_payload(), test_health_embedding_shows_the_last_call(), test_health_has_scheduler_block() (+14 more)

### Community 13 - "本機知識庫 store"
Cohesion: 0.08
Nodes (14): _locked(), _neighbour_value(), newest_first(), PandasStore, _verified_scores(), test_load_old_parquet_defaults(), test_related_discussions_stored_as_json(), test_save_records_matches_save_record() (+6 more)

### Community 14 - "Threads 發佈測試"
Cohesion: 0.11
Nodes (40): ThreadsService, ThreadsTransientError, FakeAI, live(), livebot(), poll(), _mentions_page(), _no_leftover_poll_lock() (+32 more)

### Community 15 - "後端入口與設定"
Cohesion: 0.06
Nodes (16): describe_db_error(), custom_swagger_ui_html(), health_check(), lifespan(), payload_too_large_handler(), root(), trending_scheduler_enabled(), validation_exception_handler() (+8 more)

### Community 16 - "前端 API 客戶端"
Cohesion: 0.08
Nodes (41): abortError(), ANALYZE_TIMEOUT_MS, analyzeImage(), analyzeText(), ApiError, BACKEND_DOWN_EVENT, BASE, DEFAULT_GET_TIMEOUT_MS (+33 more)

### Community 17 - "證據信心"
Cohesion: 0.07
Nodes (29): assess(), degrees(), _nearest_risky(), pattern_margin(), _prototypes(), similar_news(), _CloseVector, _FakeAI (+21 more)

### Community 18 - "RSS 搜尋與未證實盤點"
Cohesion: 0.07
Nodes (23): _is_confirmed_false(), _title_indicates_debunk(), _title_says_false(), _is_aggregator_url(), _is_real_text(), _is_valid_url(), _parse_rss_xml(), SearchService (+15 more)

### Community 19 - "Parquet 讀寫與本機 store"
Cohesion: 0.09
Nodes (19): build_kb_record(), wrapper(), _locked(), wrapper(), atomic_write_parquet(), _cast_all_na(), concat_rows(), path_lock() (+11 more)

### Community 20 - "機器人退避與時間"
Cohesion: 0.09
Nodes (31): backoff_remaining_seconds(), default_state(), load_state(), _normalize(), parse_until(), rate_limit_backoff_minutes(), _roll_daily(), save_state() (+23 more)

### Community 21 - "PF-2 測試與向量服務"
Cohesion: 0.09
Nodes (17): VectorService, cgu_cost_usd(), main(), pending_count(), judge(), load_rows(), main(), main() (+9 more)

### Community 22 - "機器人固定回覆文案"
Cohesion: 0.07
Nodes (28): bot(), cbot(), _expired_token_file(), fake(), FakeAI, _no_leftover_poll_lock(), _no_network(), _blocked() (+20 more)

### Community 23 - "前端建置設定"
Cohesion: 0.06
Nodes (42): dependencies, react@^19.2.0, react-dom@^19.2.0, react-router-dom@^7.18.3, devDependencies, autoprefixer@^10.4.27, eslint@^9.39.1, @eslint/js@^9.39.1 (+34 more)

### Community 24 - "清洗腳本測試"
Cohesion: 0.12
Nodes (29): _is_real_claim(), default_kb_rows(), default_trending_rows(), kb_row(), make_kb_parquet(), make_trending_db(), trending_rows_d04(), _checker() (+21 more)

### Community 25 - "查核結論同步"
Cohesion: 0.08
Nodes (29): is_running(), run_sync(), client(), empty_store(), _entry(), _fresh_status(), _rows(), sources() (+21 more)

### Community 26 - "Postgres 連線與機器人狀態"
Cohesion: 0.10
Nodes (12): ensure_pg_schema(), _PgStoreBase, _as_utc_naive(), ThreadsPgStore, log(), main(), _drop_schema(), pg() (+4 more)

### Community 27 - "AI 服務呼叫"
Cohesion: 0.09
Nodes (11): AIService, call(), embedding_status(), main(), test_parse_json_loose_invalid_raises(), test_parse_json_loose_plain_and_fenced(), test_validate_result_bad_risk_type_coerced_to_safe(), test_validate_result_keeps_unverifiable_as_not_risky() (+3 more)

### Community 28 - "每 IP 限速"
Cohesion: 0.09
Nodes (22): client_ip(), configured_limits(), rate_limited_response(), SlidingWindowLimiter, Clock, clock(), fresh_global_limiter(), limiter() (+14 more)

### Community 29 - "導覽列與文案"
Cohesion: 0.11
Nodes (28): AppShell(), routeHandle(), DesktopNav(), ITEMS, Footer(), linkStyle, DESKTOP_QUERY, NAV_BOT (+20 more)

### Community 30 - "SSRF 防護與爬蟲"
Cohesion: 0.09
Nodes (19): _abort_response(), BlockedURL, _call_bounded(), run(), check_url(), _close_quietly(), FetchTimeout, _ip_is_forbidden() (+11 more)

### Community 31 - "Threads API 客戶端"
Cohesion: 0.07
Nodes (3): parse_reply_quota(), ThreadsClient, test_parse_reply_quota_shapes()

### Community 32 - "知識庫寫入門檻測試"
Cohesion: 0.14
Nodes (23): _ai(), _FakeAI, _items(), _no_network(), _NoCrawler, _patch_proc(), _run_proc(), _save() (+15 more)

### Community 33 - "結果頁狀態與輪詢"
Cohesion: 0.13
Nodes (29): announcementFor(), Result(), LABEL_COLOR, prefersReducedMotion(), ResultLoading(), STEP_KEYS, StepMark(), subscribeReducedMotion() (+21 more)

### Community 34 - "分享文案與網址"
Cohesion: 0.10
Nodes (17): build_result_response(), get_result(), input_preview(), parse_platform_post(), request_base_url(), to_taipei_iso(), build_share(), configured_base_url() (+9 more)

### Community 35 - "內容 hash 與管理權限"
Cohesion: 0.09
Nodes (12): AuditStore, _admin_calls(), admin_env(), _auth(), client(), network_calls(), scheduled(), stores() (+4 more)

### Community 36 - "來源分級與網域比對"
Cohesion: 0.12
Nodes (17): source_name(), compute_write_gate(), _grade_sources_offline(), cofacts_article_id(), cofacts_has_verdict(), _cofacts_verdict_cached(), grade_sources(), _host_matches() (+9 more)

### Community 37 - "熱門牆流程"
Cohesion: 0.11
Nodes (17): _apply_ai_result(), _cleanup_legacy_strings(), _detect_source(), _extract_claim_from_title(), _fill_record_provenance(), _get_pending_records(), _index_factcheck_claim(), _is_tfc_report() (+9 more)

### Community 38 - "資料清洗腳本"
Cohesion: 0.16
Nodes (24): _as_items(), _bool_value(), _canon(), _clean_item(), clean_kb_row(), _key(), _created_key(), _describe_change() (+16 more)

### Community 39 - "Threads 授權與 token"
Cohesion: 0.14
Nodes (18): _days_left(), _default_sleep(), _parse_iso(), AuthError, build_authorize_url(), _call(), clean_code(), exchange_code() (+10 more)

### Community 40 - "設定與健康檢查測試"
Cohesion: 0.09
Nodes (14): Settings, Config, _launch_guards_off(), _clean_env(), make(), test_default_is_off(), test_defaults_for_new_keys(), test_demo_mode_does_not_affect_threads() (+6 more)

### Community 41 - "TFC 與 MyGoPen 解析"
Cohesion: 0.12
Nodes (20): mygopen_rows(), _skip(), tfc_rows(), _claim_for_index(), classification_slugs(), get_json(), is_rumor_text(), label_of() (+12 more)

### Community 42 - "本機任務 store"
Cohesion: 0.11
Nodes (12): _encode_value(), _is_na(), TaskStore, test_url_task_type_analyze_url(), test_task_store_lifecycle(), test_task_store_returns_completed_tasks_with_a_kb_row_since_the_cutoff(), test_concurrent_task_updates_do_not_lose_writes_or_break_reads(), test_recent_kb_refs_matches_local_store() (+4 more)

### Community 43 - "Threads token 測試"
Cohesion: 0.12
Nodes (17): save_token_db(), ThreadsAPIError, test_cloud_token_is_refreshed_when_due(), test_file_token_is_not_auto_refreshed(), test_token_is_read_from_the_database_in_cloud_mode(), _token(), env_token(), _iso() (+9 more)

### Community 44 - "燈號與 fallback 契約"
Cohesion: 0.10
Nodes (17): _default_fallback_result(), _confidence(), frame_of(), test_frame_mapping(), _r(), _run_analyze_record_with_ai_result(), test_ai_service_available_property(), test_analyze_record_other_fallback_is_ai_unavailable() (+9 more)

### Community 45 - "Postgres 欄位轉換"
Cohesion: 0.18
Nodes (16): _as_bool(), _as_datetime(), _as_float(), _as_int(), audit_row_params(), _clean_text(), _drop_none_keys(), fact_check_row_params() (+8 more)

### Community 46 - "機器人輪詢迴圈"
Cohesion: 0.11
Nodes (17): _to_epoch(), _accepts_kwarg(), _as_int(), _backoff_skip(), _bot_handle(), _cap_reached(), _count_outcome(), _daily() (+9 more)

### Community 47 - "機器人處理提及"
Cohesion: 0.12
Nodes (17): _analyze_and_reply(), _esc(), _finish_poll(), handle_mention(), _input_of(), _post_ref(), _preview(), _publish_reply() (+9 more)

### Community 48 - "網址輸入流程測試"
Cohesion: 0.11
Nodes (11): _CountingAI, _proc_patch(), _run_url(), test_allows_public_samples(), test_blocked_url_endpoint_422_no_request(), test_blocks_private_and_protocol_samples(), test_crawl_failure_real_crawler_http_404(), test_crawl_failure_returns_unverifiable_no_ai() (+3 more)

### Community 49 - "來源分級"
Cohesion: 0.09
Nodes (16): _article_payload(), _FakeResp, _no_network(), test_cofacts_lru_cache_hits_once(), _post(), test_cofacts_no_reply_tier3(), test_cofacts_with_reply_mock_tier1(), test_grade_sources_empty() (+8 more)

### Community 50 - "機器人狀態 API"
Cohesion: 0.11
Nodes (12): _bot_handle(), build_status(), _display_path(), _int_or_none(), _iso(), poll_allowed(), _reply_quota(), threads_replies() (+4 more)

### Community 51 - "搬資料到 Supabase"
Cohesion: 0.12
Nodes (16): build_pg_engine(), get_pg_engine(), upsert_statement(), drop_url_conflicts(), kb_summary(), load_audit(), load_fact_checks(), load_knowledge() (+8 more)

### Community 52 - "查核資料批次入庫"
Cohesion: 0.14
Nodes (17): cgu_usage(), degrees(), kmeans_centroids(), load_pf2_pairs(), main(), unit(), vectors_for(), cmd_apply() (+9 more)

### Community 53 - "燈號與 fallback 契約（2）"
Cohesion: 0.09
Nodes (13): is_fallback(), cache_would_hit(), _usable(), _cgu_only_service(), test_build_result_reports_cache_layer(), test_confidence_level_no_longer_follows_the_model_self_score(), test_fallback_summary_prefix_is_stable(), test_gateway_models_lists_ids_without_spending_quota() (+5 more)

### Community 54 - "結果頁動作與相似查證"
Cohesion: 0.11
Nodes (18): useToast(), contrast(), css, dark, light, luminance(), PAIRS, buildThreadsIntent() (+10 more)

### Community 55 - "輪詢鎖與觸發"
Cohesion: 0.11
Nodes (15): run_poll_quietly(), get_threads_pg(), _acquire_file_lock(), _acquire_poll_lock(), _lock_age_seconds(), poll_in_progress(), PollInProgress, _read_lock() (+7 more)

### Community 56 - "查核機構語料收錄"
Cohesion: 0.11
Nodes (14): cofacts_nodes(), cofacts_rows(), content_hash(), dedupe_rows(), http_json(), is_message_text(), kb_item(), mygopen_entries() (+6 more)

### Community 57 - "送出查證 hook"
Cohesion: 0.15
Nodes (23): analyzeUrl(), configureFixtures(), DEFAULT_RETRY_AFTER_SECONDS, GATEWAY_DOWN, homePrefillState(), inline(), INPUT_KEY_PREFIX, inputStorageKey() (+15 more)

### Community 58 - "本機資料檢查"
Cohesion: 0.13
Nodes (16): init_sql_db(), _migrate_fact_check_records(), _fmt_counter(), kb_lines(), main(), _norm(), _safe_print(), trending_detail_lines() (+8 more)

### Community 59 - "任務 store 與結果 API 測試"
Cohesion: 0.13
Nodes (18): test_feedback_has_its_own_bucket_and_length_caps(), client(), _complete(), store(), test_ai_unavailable_grey_share_null(), test_completed_schema(), test_empty_public_base_url_falls_back_to_request_base(), test_failed_schema_no_raw_exception() (+10 more)

### Community 60 - "上線護欄測試"
Cohesion: 0.10
Nodes (16): FakeVector, ForbiddenCrawler, _not_blocked(), _sync(), test_async_endpoints_refuse_before_creating_a_task(), test_cache_hit_still_works_when_cap_is_reached(), test_cap_zero_means_unlimited(), test_health_reports_used_and_cap() (+8 more)

### Community 61 - "Threads 回覆格式"
Cohesion: 0.15
Nodes (19): format_verdict_reply(), threads_len(), test_threads_reply_unknown_type(), test_threads_reply_within_limit_and_has_verdict(), test_dry_run_uses_threads_len_and_writes_sample(), _base_url(), _links(), test_default_result_url_from_settings() (+11 more)

### Community 62 - "機器人檔案鎖"
Cohesion: 0.12
Nodes (14): _atomic_write_bytes(), check_mentions_file(), clear_stale_poll_lock(), drop_sim_reply_records(), ensure_mentions(), _jsonl_rows(), _load_json(), load_seeds() (+6 more)

### Community 63 - "分析 API 測試"
Cohesion: 0.11
Nodes (17): _assert_validation_error(), client(), enqueued(), _fake_processor_result(), store(), test_analysis_result_model_v2_fields_required_non_null(), test_legacy_task_payload_backfills_v2_fields(), test_sync_500_hides_exception_text() (+9 more)

### Community 64 - "查核結果回補測試"
Cohesion: 0.18
Nodes (17): _ai(), CountingVector, env(), _mix(), NoAI, NoCrawler, _run(), _save() (+9 more)

### Community 65 - "知識庫頁"
Cohesion: 0.15
Nodes (19): Chip(), PALETTE, pillStyle(), EXAMPLE_KEYS, ExampleChips(), KnowledgeCard(), SMALL_TEXT, SUMMARY_TEXT (+11 more)

### Community 66 - "評測腳本"
Cohesion: 0.13
Nodes (12): compute_metrics(), _engine_of(), _is_blank(), main(), predict_one(), _predictions_frame(), run_metadata(), run_predictions() (+4 more)

### Community 67 - "知識庫 API"
Cohesion: 0.16
Nodes (11): _count_key(), hot_knowledge(), knowledge_stats(), list_knowledge(), _num(), _offline_tier(), _public_record(), _public_sources() (+3 more)

### Community 68 - "每日上限測試"
Cohesion: 0.14
Nodes (12): _cap(), Clock, clock(), engine(), ExplodingEngine, test_concurrent_consumers_never_exceed_cap(), test_database_failure_still_enforces_cap_in_process(), test_day_boundary_uses_taipei_time_not_utc() (+4 more)

### Community 69 - "輪詢狀態記帳"
Cohesion: 0.16
Nodes (5): _complete_reply(), PollContext, _publish_pending(), test_threads_bot_context_uses_cloud_task_store(), test_threads_bot_context_uses_local_task_store_by_default()

### Community 70 - "Threads 授權測試"
Cohesion: 0.13
Nodes (13): FakeResp, _seed(), test_clean_code(), test_error_body_secret_straddling_300_chars_is_fully_redacted(), test_exchange_missing_expires_in_defaults_to_60_days(), test_exchange_writes_complete_json(), test_http_400_exits_nonzero_and_writes_nothing(), test_long_exchange_400_writes_nothing() (+5 more)

### Community 71 - "查核結論同步（2）"
Cohesion: 0.15
Nodes (11): trigger_factcheck_sync(), gateway_models(), collect(), embed_check(), model_check(), _now(), _reset(), _run_locked() (+3 more)

### Community 72 - "每日 AI 次數上限"
Cohesion: 0.20
Nodes (6): AiBudget, test_consumes_up_to_cap_then_refuses(), test_count_survives_a_new_instance(), test_new_day_in_taipei_resets_the_count(), test_processor_backstop_returns_fallback_without_calling_ai(), test_ai_budget_counts_atomically_on_postgres()

### Community 73 - "發佈間諜測試"
Cohesion: 0.10
Nodes (7): ContainerSpy, CrashAfterCreate, SimulatedCrash, SpyThreadsService, killed(), test_container_already_published_is_marked_not_published_again(), killed()

### Community 74 - "機器人回覆紀錄"
Cohesion: 0.16
Nodes (16): append_reply_record(), _dir(), _iter_records(), own_reply_ids(), _pg(), read_reply_records(), replies_path(), state_initialized() (+8 more)

### Community 75 - "機器人測試腳本"
Cohesion: 0.19
Nodes (16): BackendDown, _call(), _default_embedder(), dry_run(), _early_workdir(), live_check(), main(), _new_records() (+8 more)

### Community 76 - "機器人測試腳本（2）"
Cohesion: 0.12
Nodes (14): _analysis_targets(), describe_reply(), _first_hash_row(), _fixed_kind(), _pid_alive(), prewarm(), _promote_row(), _report_prewarm() (+6 more)

### Community 77 - "舊證據重新比對測試"
Cohesion: 0.14
Nodes (14): _ai(), embed_settings(), env(), FakeVector, _mix(), NoAI, NoCrawler, _Resp (+6 more)

### Community 78 - "embedding 與模型下架處理"
Cohesion: 0.10
Nodes (5): _classify_upstream_error(), _embed_error_label(), _is_model_missing(), _request_timeout(), _utc_now_iso()

### Community 79 - "Postgres 稽核 store"
Cohesion: 0.14
Nodes (6): _kb_frame(), _like_literal(), PgAuditStore, test_audit_store_writes(), test_knowledge_page_queries_match_local_store(), test_pg_stores_expose_the_local_public_interface()

### Community 80 - "雲端機器人測試"
Cohesion: 0.11
Nodes (7): set_threads_pg(), _AvailableClient, bot(), cloud(), FakePg, test_cloud_poll_uses_database_state_lock_and_records(), test_poll_waits_until_the_cloud_state_is_initialized()

### Community 81 - "內容 hash 與管理權限（2）"
Cohesion: 0.17
Nodes (13): CacheService, _seed_to_db(), _make_store(), test_find_by_hash_hit_and_miss(), test_find_by_url_hit_updates_hit_count(), test_generate_hash_deterministic(), test_vector_search_below_threshold_none(), test_vector_search_exact_hit() (+5 more)

### Community 82 - "UI 檢核表腳本"
Cohesion: 0.11
Nodes (16): ACTION_TEXT, added, already, argv, body, cell(), col, CSV (+8 more)

### Community 83 - "UI 截圖腳本"
Cohesion: 0.13
Nodes (16): argv, BASE, connect(), EDGE, fixture(), FIXTURES, FRONTEND, HERE (+8 more)

### Community 84 - "發佈與錯誤分類"
Cohesion: 0.14
Nodes (7): is_link_limit_error(), classify_api_error(), classify_status(), _create_and_publish(), _legacy_reply(), _LinkLimitExceeded, test_classify_status_table()

### Community 85 - "評測計時測試"
Cohesion: 0.28
Nodes (12): down(), ok(), test_console_output_is_cp950_safe(), test_report_metadata_columns(), test_report_metadata_shows_every_engine_that_answered(), test_report_only_consistent(), test_resume_with_legacy_predictions_without_elapsed_ms(), test_seed_db_writes_gold_verified() (+4 more)

### Community 86 - "知識庫 API 測試"
Cohesion: 0.22
Nodes (14): _add(), client(), _ids(), _list(), network_calls(), store(), test_limit_default_30_and_param_validation(), test_offset_pagination_no_dup_no_gap() (+6 more)

### Community 87 - "文字輸入不爬取測試"
Cohesion: 0.13
Nodes (5): _block_network(), FakeAI, FakeVector, test_crawler_rejects_keyword_type(), test_text_input_reaches_ai_without_googlesearch()

### Community 88 - "標題主張修正腳本"
Cohesion: 0.23
Nodes (12): embed_batch(), apply(), _as_json(), backup(), log(), main(), plan(), restore() (+4 more)

### Community 89 - "Threads 回覆格式（2）"
Cohesion: 0.18
Nodes (13): _assemble(), _base_url(), _clean_summary(), _cut(), _default_result_url(), first_verified_source_url(), _in_emoji_range(), reply_cannot_read_quoted() (+5 more)

### Community 90 - "處理流程測試"
Cohesion: 0.16
Nodes (9): CountingCrawler, FakeAI, FakeVector, _patch(), RecordingVector, _run(), test_text_input_analyzes_user_text_not_crawled_page(), test_text_input_never_calls_crawler() (+1 more)

### Community 91 - "回應大小限制測試"
Cohesion: 0.12
Nodes (9): _BlockingResp, _public_dns(), test_blocked_read_is_aborted_at_deadline(), test_custom_timeout_overrides_crawler_defaults(), test_later_hop_gets_only_remaining_time(), test_slow_headers_bounded_by_wall_clock(), slow_request(), test_trickling_body_bounded_by_wall_clock() (+1 more)

### Community 92 - "本機查證歷史"
Cohesion: 0.22
Nodes (13): addEntry(), HISTORY_KEY, isAvailable(), isEntry(), listAll(), listRecent(), MAX_ENTRIES, PREVIEW_MAX (+5 more)

### Community 93 - "機器人狀態頁"
Cohesion: 0.29
Nodes (14): Bot(), backoffText(), badgeKey(), count(), isOff(), KNOWN_ERRORS, lastErrorText(), lastPollText() (+6 more)

### Community 94 - "資料清洗腳本（2）"
Cohesion: 0.16
Nodes (9): build_parser(), cofacts_lines(), cofacts_status_of(), CofactsChecker, grade_url(), _is_cofacts(), load_drop_ids(), main() (+1 more)

### Community 95 - "Threads API 測試夾具"
Cohesion: 0.12
Nodes (6): env(), fake_ai(), FakeAI, network_calls(), sim(), spy_tasks()

### Community 96 - "網址爬蟲"
Cohesion: 0.24
Nodes (4): CrawlerService, test_crawler_blocked_url_error_code(), test_crawler_error_codes_http_error_and_too_short(), test_crawler_success_uses_safe_get()

### Community 97 - "深淺色主題"
Cohesion: 0.24
Nodes (9): applyTheme(), defaultMatchMedia(), getCurrentTheme(), getInitialTheme(), getStoredTheme(), getSystemTheme(), throwingStorage, THEME_KEY (+1 more)

### Community 98 - "管理端點報告"
Cohesion: 0.15
Nodes (8): _eval_report_guard(), get_factcheck_sync_status(), get_weekly_eval_report(), get_weekly_eval_results(), get_weekly_eval_status(), has_report(), is_running(), results_csv()

### Community 99 - "Docker 設定"
Cohesion: 0.14
Nodes (13): build, command, container_name, environment, ports, volumes, context, dockerfile (+5 more)

### Community 100 - "熱門牆抓取測試"
Cohesion: 0.15
Nodes (4): _FakeRec, _setup_analyze(), _no_net(), test_fill_record_provenance_matches_rule4()

### Community 102 - "死連結過濾"
Cohesion: 0.21
Nodes (5): filter_valid_sources(), _is_url_alive(), test_filter_valid_sources_drops_dead(), test_filter_valid_sources_empty(), test_is_url_alive_rejects_non_http()

### Community 103 - "向量重算腳本"
Cohesion: 0.27
Nodes (6): apply_local(), apply_supabase(), main(), reembed(), rows_to_fix(), vector_dim()

### Community 104 - "HTML 轉 PDF 腳本"
Cohesion: 0.18
Nodes (9): args, connect(), dst, EDGE, [input, output], landscape, main(), sleep() (+1 more)

### Community 105 - "上線護欄測試（2）"
Cohesion: 0.17
Nodes (6): budget(), client(), FakeAI, image_env(), limiter(), pipeline()

### Community 107 - "SSRF 測試"
Cohesion: 0.21
Nodes (8): _fake_getaddrinfo(), _FakeResp, test_connect_timeout_is_10s(), test_redirect_to_private_blocked(), test_redirects_followed_up_to_three(), test_response_over_2mb_aborted(), test_total_timeout_uses_crawler_timeout(), test_url_validator_blocks_private_without_request()

### Community 108 - "Postgres 連線與機器人狀態（2）"
Cohesion: 0.25
Nodes (3): insert_statement(), PgKnowledgeStore, _placeholders()

### Community 109 - "Postgres 任務 store"
Cohesion: 0.22
Nodes (4): input_type_from_task_type(), test_task_lifecycle_defaults_and_json_columns(), test_task_prune_only_finished_oldest_first(), ids()

### Community 111 - "主張文字前處理"
Cohesion: 0.31
Nodes (5): matching_text(), test_empty_input(), test_leaves_other_text_alone(), test_strips_lead_in_and_question(), test_too_short_after_stripping_keeps_original()

### Community 112 - "知識庫單筆更正腳本"
Cohesion: 0.42
Nodes (7): _as_json(), correct(), log(), main(), _read(), restore(), _write()

### Community 113 - "評測計時測試（2）"
Cohesion: 0.18
Nodes (4): box(), FakeClock, _real_result_files_untouched(), _sha256()

### Community 115 - "熱門牆抓取測試（3）"
Cohesion: 0.22
Nodes (5): _install_recording_to_thread(), test_run_trending_fetch_offloads_blocking_calls(), fetch_rss_items(), retry_pending_records(), test_run_trending_fetch_without_analysis_skips_the_ai_step()

### Community 116 - "輪詢逾時測試"
Cohesion: 0.20
Nodes (3): _Resp, _StuckHttp, test_poll_via_api_times_out_and_detects_backoff()

### Community 117 - "機器人固定回覆文案（2）"
Cohesion: 0.24
Nodes (9): reply_cannot_read(), reply_media_only(), reply_too_short(), _epoch(), _post_of(), test_bot_full_fixture_one_poll(), test_poll_cap_stop_is_reported(), test_unknown_4xx_on_get_post_marks_failed_without_reply() (+1 more)

### Community 118 - "輪詢鎖測試"
Cohesion: 0.22
Nodes (7): lock_path(), test_poll_cancelled_mid_poll_releases_lock(), scenario(), test_poll_concurrent_call_raises_poll_in_progress(), test_poll_does_not_delete_lock_taken_over_by_another_poller(), test_poll_lock_file_held_by_other_process(), test_poll_lock_file_unreadable_uses_mtime()

### Community 119 - "機器人退避測試"
Cohesion: 0.20
Nodes (4): LegacyReplyOnlyClient, test_container_legacy_client_errors_use_the_same_triage(), test_resolve_target_table(), test_service_get_quoted_post_id_parses_both_shapes()

### Community 120 - "機器人模擬測試輔助（2）"
Cohesion: 0.20
Nodes (9): test_container_pending_of_other_mode_and_malformed_entries(), test_poll_backoff_skips_without_api_call(), test_poll_cursor_never_moves_backwards_when_only_overlap_mentions(), test_poll_cursor_stays_when_pending_mention_has_no_timestamp(), get_mentions(), test_poll_daily_cap_stops(), test_poll_max_replies_per_poll_1_replies_only_one(), _text_mentions() (+1 more)

### Community 121 - "假 Graph API"
Cohesion: 0.27
Nodes (3): FakeGraph, install(), _response()

### Community 122 - "熱門牆抓取測試（4）"
Cohesion: 0.32
Nodes (4): _analyze_record(), test_analyze_record_dead_tier1_verified_false(), test_analyze_record_tier1_source_url_verified_true(), test_analyze_record_tier3_moved_to_related()

### Community 124 - "標記規則"
Cohesion: 0.48
Nodes (4): _clean(), fix_parquet(), fix_sqlite(), main()

### Community 125 - "AI 逾時與提示規則"
Cohesion: 0.43
Nodes (4): _svc(), test_chain_stops_when_total_budget_spent(), test_request_timeout_never_exceeds_setting(), _fake_post()

### Community 126 - "管理 token 腳本測試"
Cohesion: 0.38
Nodes (3): test_appends_when_missing(), test_fills_empty_line_and_keeps_other_lines(), _token_line()

### Community 127 - "手動觸發輪詢"
Cohesion: 0.33
Nodes (3): trigger_poll(), get_threads_client(), test_fake_factory_by_mode()

## Knowledge Gaps
- **21 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `PandasStore` connect `本機知識庫 store` to `每週評測測試`, `Threads API 端點測試`, `store 工廠`, `熱門牆資料表`, `Postgres store 契約測試`, `三層快取主流程`, `健康檢查與熱門查證測試`, `證據信心`, `RSS 搜尋與未證實盤點`, `Parquet 讀寫與本機 store`, `查核結論同步`, `知識庫寫入門檻測試`, `內容 hash 與管理權限`, `網址輸入流程測試`, `搬資料到 Supabase`, `燈號與 fallback 契約（2）`, `上線護欄測試`, `查核結果回補測試`, `每日 AI 次數上限`, `機器人測試腳本`, `機器人測試腳本（2）`, `舊證據重新比對測試`, `Postgres 稽核 store`, `內容 hash 與管理權限（2）`, `評測計時測試`, `知識庫 API 測試`, `文字輸入不爬取測試`, `處理流程測試`, `熱門牆抓取測試`, `上線護欄測試（2）`, `熱門牆抓取測試（4）`, `標記規則`?**
  _High betweenness centrality (0.046) - this node is a cross-community bridge._
- **Are the 19 inferred relationships involving `PandasStore` (e.g. with `stores()` and `test_evidence_lookup_failure_falls_back_to_sources_only()`) actually correct?**
  _`PandasStore` has 19 INFERRED edges - model-reasoned connections that need verification._
- **Should `機器人模擬測試輔助` be split into smaller, more focused modules?**
  _Cohesion score 0.08072707832130446 - nodes in this community are weakly interconnected._
- **Why does `TaskStore` connect `本機任務 store` to `本機任務 store（2）`, `Threads API 端點測試`, `store 工廠`, `Postgres store 契約測試`, `三層快取主流程`, `健康檢查與熱門查證測試`, `Threads 發佈測試`, `證據信心`, `Parquet 讀寫與本機 store`, `機器人固定回覆文案`, `知識庫寫入門檻測試`, `內容 hash 與管理權限`, `機器人輪詢迴圈`, `網址輸入流程測試`, `搬資料到 Supabase`, `任務 store 與結果 API 測試`, `上線護欄測試`, `分析 API 測試`, `查核結果回補測試`, `輪詢狀態記帳`, `每日 AI 次數上限`, `機器人測試腳本`, `舊證據重新比對測試`, `Postgres 稽核 store`, `雲端機器人測試`, `內容 hash 與管理權限（2）`, `文字輸入不爬取測試`, `處理流程測試`, `Threads API 測試夾具`, `上線護欄測試（2）`?**
  _High betweenness centrality (0.039) - this node is a cross-community bridge._
- **Are the 22 inferred relationships involving `TaskStore` (e.g. with `_complete()` and `_finish_ai()`) actually correct?**
  _`TaskStore` has 22 INFERRED edges - model-reasoned connections that need verification._
- **Should `首頁與共用元件` be split into smaller, more focused modules?**
  _Cohesion score 0.07515734912995187 - nodes in this community are weakly interconnected._
- **Why does `ThreadsService` connect `Threads 發佈測試` to `token 讀取來源`, `Threads HTTP 請求`, `Threads 授權與 token`, `Threads token 測試`, `機器人測試腳本`, `兩段式發佈`, `雲端機器人測試`, `機器人狀態 API`, `機器人固定回覆文案`, `機器人退避測試`, `Threads API 客戶端`, `手動觸發輪詢`?**
  _High betweenness centrality (0.021) - this node is a cross-community bridge._