// 繁中文案表（spec §8.7 逐字 + §7.7 分享文案）。
// 所有使用者可見文字一律從這裡取，元件內不寫死中文。
// 規則：成對 key 已拆開；表內括號註解不收入字串。
// 佔位符 {name} 由 t() 置換；{BRAND}、{BOT_HANDLE} 自動帶入；
// {name≤N} 表示該參數超過 N 字時截為 N-1 字並補「…」（對應 7.7 的 {summary≤80}）。

export const BRAND = import.meta.env?.VITE_BRAND_NAME || "全民查證公社";
export const BOT_HANDLE = "factcheck_tw_bot";

const IS_DEV = import.meta.env ? Boolean(import.meta.env.DEV) : true;

export const STRINGS = {
  // ---- 首頁 / 輸入 ----
  home_tagline: "貼上訊息，10 秒知道真假",
  home_sub: "AI 判定詐騙／假訊息、尚待確認或查無異常，並附上查核來源。",
  tab_text: "文字",
  tab_url: "網址",
  tab_image: "圖片",
  input_placeholder_text: "貼上 LINE、Threads 或任何地方看到的訊息…",
  input_placeholder_url: "https://… 貼上新聞或貼文網址",
  upload_hint: "點擊或拖曳圖片到這裡（PNG／JPG／WEBP，10 MB 以內）",
  btn_analyze: "開始查證",
  btn_analyzing: "查證中…",
  analyze_note: "查證約需 5–20 秒；查過的內容會直接命中快取。",
  example_1: "健保卡即日起停用，請點連結重新驗證",
  example_2: "網傳吃香蕉配優格會中毒",
  example_3: "165 反詐騙專線提醒：遇到「保證獲利」請掛斷",
  err_empty: "請先貼上要查證的內容。",
  err_too_long: "內容超過 20,000 字，請刪減後再試。",
  err_invalid_url: "這不是有效的網址，請以 http:// 或 https:// 開頭。",
  err_blocked_url: "這個網址無法查證（內部或保留位址）。",
  err_image_type: "只支援 PNG、JPG、WEBP 圖片。",
  err_image_size: "圖片超過 10 MB，請壓縮後再上傳。",
  err_rate: "查證太頻繁，請 {n} 秒後再試。",
  backend_down: "暫時連不上伺服器，請確認網路或稍後再試。",

  // ---- 結果頁 ----
  result_loading: "AI 正在查證，通常 5–20 秒",
  result_step_1: "檢查快取",
  result_step_2: "讀取內容",
  result_step_3: "AI 判讀",
  error_timeout: "處理時間比預期久，你可以稍後再打開這個連結。",
  chip_live: "AI 即時判定",
  chip_cache_url: "快取命中・相同網址",
  chip_cache_hash: "快取命中・相同內容",
  chip_cache_vector: "快取命中・語意相似",
  cache_hint: "這筆內容先前已查證過，系統直接沿用結果，沒有再次呼叫 AI。",
  frame_red_scam: "詐騙警告",
  frame_red_misinfo: "假訊息",
  frame_red_other: "風險訊息",
  frame_yellow: "尚待確認",
  frame_yellow_unverifiable: "無法查證",
  frame_green: "查無異常",
  frame_grey: "AI 暫時無法使用",
  // 8.7 原文為「信心 {高|中|低}」：成對值拆成三個逐字 key（同 chip_cache_url|hash|vector）。
  confidence_chip_high: "信心 高",
  confidence_chip_mid: "信心 中",
  confidence_chip_low: "信心 低",
  confidence_note: "模型自評信心，未經機率校準（實際效能請參考評測報告）",
  section_input: "你查的內容",
  section_summary: "判讀摘要",
  section_explanation: "詳細說明",
  section_sources: "查核來源",
  section_similar: "知識庫中的相似查證",
  similar_item: "相似度 {pct}%・{frame_label}",
  sources_empty: "尚無查核機構證實這則訊息，請自行查證。",
  tier_1_chip: "查核機構",
  tier_2_chip: "媒體查核報導",
  no_verified_source_title: "尚無查核機構證實",
  no_verified_source_body:
    "目前找不到已對這則訊息做出判定的查核機構或媒體查核報導，以上為 AI 的初步判讀。轉傳前請先到台灣事實查核中心、MyGoPen 或 Cofacts 查證。",
  frame_yellow_no_source: "尚無查核機構證實",
  ai_unavailable_title: "AI 服務暫時無法使用",
  ai_unavailable_body:
    "可能是額度用盡或連線問題，這次沒有產生判定。你可以稍後再試，或先到知識庫搜尋是否已有人查過。",
  quota_exceeded_title: "今日查證額度已用完",
  quota_exceeded_body:
    "為控制成本，每天的 AI 查證次數有上限。已查過的內容仍可直接命中快取；明天再試或到知識庫搜尋。",
  unverifiable_body: "系統抓不到這個網址的內容，或內容太少無法判讀。請改貼文字內容再試一次。",
  unverifiable_threads_hint: "Threads 貼文網址目前無法直接讀取，請複製貼文文字後貼上查證。",
  error_title: "出了點問題",
  error_network: "連不上伺服器，請檢查網路後重試。",
  error_server: "伺服器發生錯誤（{code}），請稍後再試。",
  btn_retry: "重試",
  btn_reanalyze: "重新查證",
  btn_share_threads: "分享到 Threads",
  btn_share_opened: "已開啟 Threads",
  btn_copy_link: "複製連結",
  btn_copied: "已複製",
  btn_check_another: "再查一則",
  toast_share: "已開啟 Threads，發佈前可自行修改文字",
  result_not_found_title: "找不到這筆查證",
  result_not_found_body: "連結可能已過期或輸入錯誤。你可以回首頁重新查證。",
  btn_home: "回首頁",
  from_threads: "來自 Threads @{username}",
  label_source_ai: "AI 判定",
  label_source_rule: "查核機構標記",
  label_source_gold: "評測標註",
  label_source_admin: "人工覆寫",
  analyzed_at: "查證時間 {datetime}",
  disclaimer_short: "判讀由 AI 自動產生，僅供參考，請自行查證。",

  // ---- 熱門牆 ----
  trending_title: "今日熱門查核",
  trending_sub: "來源：MyGoPen、台灣事實查核中心、Cofacts。{scheduler_state}",
  scheduler_on: "每 {n} 小時自動更新",
  scheduler_off: "目前為手動更新",
  trending_updated: "資料更新時間：{time}",
  trending_empty: "還沒有熱門查核資料。",
  filter_empty: "這個分類目前沒有資料。",
  chip_pending: "未查證",

  // ---- 知識庫 ----
  knowledge_title: "查證知識庫",
  knowledge_sub: "所有查證過的內容都在這裡，重複的訊息不必再問 AI。",
  knowledge_search_placeholder: "搜尋關鍵字…",
  knowledge_stats: "共 {total} 筆・詐騙 {scam}・假訊息 {misinfo}・安全 {safe}・無法查證 {unv}",
  knowledge_verified_note: "知識庫只收錄有查核機構或媒體查核報導佐證的判定。",
  knowledge_empty: "知識庫是空的。",
  knowledge_no_match: "找不到符合「{q}」的資料，試試其他關鍵字，或直接貼到首頁查證。",
  hit_count: "命中 {n} 次",
  btn_load_more: "載入更多",
  knowledge_end: "已顯示全部 {total} 筆",

  // ---- 我的紀錄 ----
  history_title: "我的紀錄",
  history_sub: "紀錄只保存在這個瀏覽器，不需登入，也不會上傳。",
  history_empty: "還沒有查證紀錄。到首頁查一則試試。",
  history_unavailable: "這個瀏覽器無法保存紀錄（可能是無痕模式）。",
  btn_clear_history: "清除全部",
  confirm_clear: "確定要清除這台裝置上的所有紀錄嗎？此動作無法復原。",

  // ---- Threads 機器人 ----
  bot_howto: "在 Threads 回覆可疑貼文並 @{BOT_HANDLE}，機器人會在 {n} 分鐘內回覆判定與來源。",
  threads_title: "Threads 查核機器人",
  threads_mode_live: "開發模式（僅 Threads 測試者）",
  threads_mode_sim: "模擬模式",
  threads_mode_off: "已停用",
  threads_mode_invalid: "token 失效",
  threads_off: "機器人尚未啟用。設定 THREADS_MODE 與 token 後重新啟動後端。",
  threads_last_poll: "上次輪詢 {time}：檢查 {checked}、回覆 {replied}、略過 {skipped}、錯誤 {errors}",
  threads_token_days: "token 剩餘 {n} 天",
  threads_token_warn: "Threads 授權將於 {n} 天後到期，請執行續期。",
  threads_daily: "今日回覆 {n}／{cap}；Threads 配額 {usage}／{limit}",
  dev_mode_notice:
    "目前為開發模式：只有被加入為測試人員的 Threads 帳號 @{BOT_HANDLE} 才會收到回覆。公開服務需通過 Meta App Review 與企業驗證，為本專題論文所述之上線條件。",
  btn_run_poll: "執行一輪",
  threads_replies_title: "最近回覆",
  threads_replies_empty: "還沒有回覆紀錄。",
  btn_view_post: "原貼文",
  btn_view_result: "結果頁",

  // ---- 外殼 / 導覽 ----
  theme_dark: "深色",
  theme_light: "淺色",
  nav_home: "查證",
  nav_trending: "熱門",
  nav_knowledge: "知識庫",
  nav_bot: "機器人",
  nav_history: "紀錄", // 隨 /history 降 P2 保留 key，本次不顯示

  // ---- 靜態頁 / OAuth ----
  deauthorize_title: "取消授權",
  deauthorize_body: "本服務不保存授權狀態，取消授權後不需額外處理。",
  footer: "隱私政策 · 資料刪除 · 本站判讀由 AI 產生，僅供參考",
  privacy_title: "隱私政策",
  privacy_collect:
    "我們蒐集：你貼上的文字、網址或圖片；在 Threads 上 @機器人 時被回覆的公開貼文文字與貼文連結；AI 判定結果。這些內容會儲存在查證知識庫，供後續相同或相似內容快速比對。",
  privacy_not: "我們不蒐集：帳號、密碼、Cookie 追蹤；「我的紀錄」只存在你的瀏覽器。",
  privacy_ai: "判讀由 AI 自動產生，可能有誤，不構成任何法律或專業建議。使用本站即表示你了解並同意上述條款。",
  deletion_title: "資料刪除說明",
  deletion_body:
    "若你希望刪除某筆查證或被引用的 Threads 貼文文字，請來信 {CONTACT_EMAIL}，附上結果頁連結（/r/…）或 Threads 貼文連結，我們會在 7 日內刪除並回覆。",
  oauth_cb_title: "授權完成",
  oauth_cb_body: "請複製下方代碼，回到終端機貼上以完成 token 取得。",
  page_title_suffix: "｜{BRAND}",

  // ---- 分享文案（spec §7.7，FR-05 Web Intent text；url 另帶） ----
  // unverified 時紅燈文案去掉「。查核來源：{source_domain}」尾段由呼叫端處理（FR-16）。
  share_text_red_scam: "🔴 AI 判定這則訊息是詐騙：{summary≤80}。查核來源：{source_domain}",
  share_text_red_misinfo: "🔴 AI 判定這則訊息是假訊息：{summary≤80}。查核來源：{source_domain}",
  share_text_yellow: "🟡 這則訊息 AI 尚無法確認：{summary≤80}。轉傳前請先查證",
  share_text_green: "🟢 AI 查證這則訊息沒有發現異常：{summary≤80}",
  share_text_yellow_unverified: "🟡 這則訊息尚無查核機構證實：{summary≤80}。轉傳前請先查證",
};

// 待負責人確認，非 8.7 逐字：8.7 未定義但畫面需要的字串。
export const EXTRA = {
  filter_all: "全部",
  dot_scam: "詐騙",
  dot_misinfo: "假訊息",
  dot_safe: "安全",
  dot_pending: "未查證",
  back: "← 返回",
  home_recent_title: "最近查證",
  home_examples_title: "試試看",
  home_threads_card_title: "Threads 查核機器人", // 依 Main.dc.html 說明卡標題
};

const PLACEHOLDER = /\{([A-Za-z_][A-Za-z0-9_]*)(?:≤(\d+))?\}/g;

function truncate(value, max) {
  const chars = Array.from(value);
  if (chars.length <= max) return value;
  return chars.slice(0, Math.max(0, max - 1)).join("") + "…";
}

export function t(key, params = {}) {
  const template = Object.prototype.hasOwnProperty.call(STRINGS, key)
    ? STRINGS[key]
    : Object.prototype.hasOwnProperty.call(EXTRA, key)
      ? EXTRA[key]
      : undefined;
  if (template === undefined) {
    if (IS_DEV) console.warn(`[i18n] missing key: ${key}`);
    return key;
  }
  const values = { BRAND, BOT_HANDLE, ...params };
  return template.replace(PLACEHOLDER, (match, name, max) => {
    if (!Object.prototype.hasOwnProperty.call(values, name) || values[name] == null) {
      return match;
    }
    const str = String(values[name]);
    return max ? truncate(str, Number(max)) : str;
  });
}
