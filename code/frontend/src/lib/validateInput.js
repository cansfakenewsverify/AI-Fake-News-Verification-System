// 首頁輸入驗證（P-16；spec FR-01 驗收 4、FR-02、§8.3 S1「輸入驗證失敗」）。
// 純函式：回傳 i18n key（err_empty／err_too_long／err_invalid_url）或 null，不碰 DOM。
// 字數以 Unicode code point 計算，與後端 pydantic max_length=20000（Python len）一致，
// 首頁字數顯示 `{n}/20000` 也用同一個 countChars。

export const MAX_CHARS = 20000;

/** 以 code point 計數（emoji 等 surrogate pair 算 1 字）；不配置陣列，大量貼上也不卡。 */
export function countChars(value) {
  let n = 0;
  for (const _ of String(value ?? "")) n += 1;
  return n;
}

/** http(s) 開頭且 new URL() 解析得出 host。 */
export function isHttpUrl(value) {
  const text = String(value ?? "").trim();
  if (!/^https?:\/\//i.test(text)) return false;
  try {
    const url = new URL(text);
    return (url.protocol === "http:" || url.protocol === "https:") && url.hostname !== "";
  } catch {
    return false;
  }
}

/**
 * @param {"text"|"url"} mode
 * @param {string} value
 * @returns {null|"err_empty"|"err_too_long"|"err_invalid_url"}
 */
export function validateInput(mode, value) {
  const text = typeof value === "string" ? value : "";
  if (!text.trim()) return "err_empty";
  if (countChars(text) > MAX_CHARS) return "err_too_long";
  if (mode === "url" && !isHttpUrl(text)) return "err_invalid_url";
  return null;
}
