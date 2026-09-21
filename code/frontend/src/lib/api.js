// API client：所有後端呼叫的唯一入口（P-09）。
// - BASE 預設空字串 = 同源 /api（dev 走 vite proxy、Vercel 走 vercel.json 代理）
// - 逾時：GET 15s、POST 30s、圖片 60s，皆低於 Cloudflare Tunnel 單請求 100s 上限（spec §9）
// - 錯誤一律正規化為 ApiError（spec §5.7 `{detail, code}`）
// - 畫面層判斷 AI 不可用一律只讀 `ai_unavailable`；isFallback() 的前綴比對僅供舊資料相容

import { fixtureResponse, viteFixtureLoader } from "./fixtures.js";

const ENV = import.meta.env || {};

// ---- fixture 模式（P-10）------------------------------------------------------
// 開啟時 request() 不發 fetch，改讀 src/dev/fixtures/*.json（規則見 fixtures.js / README）。
// configureFixtures({ loader, search }) 供 node --test 注入；傳 null 關閉。
// production 剔除：以下兩處都用字面 `import.meta.env.DEV` 判斷，Vite build 替換成 false 後
// 整個 fixture 分支（含 fixtures.js 的 resolver）被 tree-shake；node --test 下 import.meta.env
// 不存在 -> 視為開發環境（與 i18n.js 同慣例）。
let fixtureConfig = null;

export function configureFixtures(config) {
  if (!(typeof import.meta.env === "undefined" || import.meta.env.DEV)) return;
  fixtureConfig = config && typeof config.loader === "function" ? { search: "", ...config } : null;
}

// 必須寫字面 `import.meta.env.DEV`，Vite build 才會替換成 false 並剔除整段（含 import.meta.glob）
if (typeof import.meta.env !== "undefined" && import.meta.env.DEV && import.meta.env.VITE_FIXTURES === "1") {
  configureFixtures({
    loader: viteFixtureLoader(),
    search: () => (typeof window !== "undefined" ? window.location.search : ""),
  });
}

export const BASE = ENV.VITE_API_BASE_URL || "";

export const DEFAULT_GET_TIMEOUT_MS = 15000;
export const DEFAULT_POST_TIMEOUT_MS = 30000;
export const IMAGE_TIMEOUT_MS = 60000;
// Submitting a check may be the request that wakes the sleeping backend (about a minute on the free host).
// Vercel's proxy waits up to 120 s, so waiting 75 s here turns a cold start into a slow submit instead of an error.
export const ANALYZE_TIMEOUT_MS = 75000;

// spec §5.5 fallback 字樣。辨識點清單（改字樣時要一起改）：
//   後端 app/services/ai_service.py `_default_fallback_result`、app/utils/verdict.py `is_fallback()`
//   （threads_bot、pandas_task_processor、news_fetcher、scripts/evaluate.py、scripts/test_ai_provider.py 皆呼叫它）
//   前端：本檔（唯一定義處）；封存查核儀 legacy/fake-news-detector.html
export const FALLBACK_PREFIX = "AI 分析暫時無法使用";

export const BACKEND_DOWN_EVENT = "fcc:backend-down";
export const BACKEND_UP_EVENT = "fcc:backend-up";

export class ApiError extends Error {
  constructor({ kind, status = null, code = null, message = "", retryAfter = null }) {
    super(message || code || kind);
    this.name = "ApiError";
    this.kind = kind; // "network" | "timeout" | "http"
    this.status = status;
    this.code = code;
    this.retryAfter = retryAfter;
  }
}

function emit(type) {
  if (typeof window === "undefined" || typeof window.dispatchEvent !== "function") return;
  try {
    window.dispatchEvent(new Event(type));
  } catch {
    /* 事件派發失敗不影響請求結果 */
  }
}

function abortError() {
  try {
    return new DOMException("The operation was aborted.", "AbortError");
  } catch {
    const e = new Error("The operation was aborted.");
    e.name = "AbortError";
    return e;
  }
}

/** Retry-After：秒數或 HTTP 日期 → 整數秒；無法解析回 null */
export function parseRetryAfter(value, now = Date.now()) {
  if (value == null || value === "") return null;
  const s = String(value).trim();
  if (/^\d+$/.test(s)) return Number(s);
  const t = Date.parse(s);
  if (Number.isNaN(t)) return null;
  return Math.max(0, Math.ceil((t - now) / 1000));
}

function pickMessage(body) {
  if (!body || typeof body !== "object") return "";
  if (typeof body.message === "string" && body.message) return body.message;
  const { detail } = body;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail) && detail.length) {
    const first = detail[0];
    if (typeof first === "string") return first;
    if (first && typeof first.msg === "string") return first.msg;
  }
  return "";
}

async function readBody(res) {
  if (res.status === 204) return null;
  let text;
  try {
    text = await res.text();
  } catch {
    return null;
  }
  if (!text) return null;
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

function withQuery(path, params = {}) {
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null || v === "") continue;
    qs.append(k, String(v));
  }
  const s = qs.toString();
  return s ? `${path}?${s}` : path;
}

/**
 * 發出請求並正規化錯誤。
 * @returns {Promise<any>} 解析後的 JSON（成功回應；含 202）
 */
export async function request(path, { method = "GET", body, timeoutMs, signal, headers = {}, cache } = {}) {
  const upper = method.toUpperCase();
  const limit = timeoutMs ?? (upper === "GET" ? DEFAULT_GET_TIMEOUT_MS : DEFAULT_POST_TIMEOUT_MS);

  if (signal?.aborted) throw abortError();

  const controller = new AbortController();
  let timedOut = false;
  let timer;
  let onExternalAbort;

  const guard = new Promise((_, reject) => {
    timer = setTimeout(() => {
      timedOut = true;
      controller.abort();
      reject(new ApiError({ kind: "timeout", message: "request timed out" }));
    }, limit);
    if (signal) {
      onExternalAbort = () => {
        controller.abort();
        reject(abortError());
      };
      signal.addEventListener("abort", onExternalAbort, { once: true });
    }
  });

  const init = { method: upper, signal: controller.signal, headers: { Accept: "application/json", ...headers } };
  if (cache) init.cache = cache; // fetch RequestCache mode, e.g. "no-store"
  const isForm = typeof FormData !== "undefined" && body instanceof FormData;
  if (body !== undefined) {
    if (isForm) {
      init.body = body; // 讓瀏覽器自帶 multipart boundary
    } else {
      init.body = JSON.stringify(body);
      init.headers["Content-Type"] = "application/json";
    }
  }

  let res;
  try {
    const pending =
      (typeof import.meta.env === "undefined" || import.meta.env.DEV) && fixtureConfig
        ? fixtureResponse(path, { method: upper, loader: fixtureConfig.loader, search: fixtureConfig.search })
        : globalThis.fetch(`${BASE}${path}`, init);
    res = await Promise.race([pending, guard]);
  } catch (err) {
    if (err instanceof ApiError) {
      emit(BACKEND_DOWN_EVENT);
      throw err;
    }
    if (signal?.aborted) throw abortError();
    if (timedOut) {
      emit(BACKEND_DOWN_EVENT);
      throw new ApiError({ kind: "timeout", message: "request timed out" });
    }
    emit(BACKEND_DOWN_EVENT);
    throw new ApiError({ kind: "network", message: err?.message || "network error" });
  } finally {
    clearTimeout(timer);
    if (signal && onExternalAbort) signal.removeEventListener("abort", onExternalAbort);
  }
  guard.catch(() => {}); // 已結束的 race 不留下未處理的 rejection

  const data = await readBody(res);

  if (res.ok) {
    emit(BACKEND_UP_EVENT);
    return data;
  }

  // 代理層回 502/503/504 通常代表 tunnel／後端不在
  if (res.status === 502 || res.status === 503 || res.status === 504) emit(BACKEND_DOWN_EVENT);

  const obj = data && typeof data === "object" ? data : null;
  throw new ApiError({
    kind: "http",
    status: res.status,
    code: obj && typeof obj.code === "string" ? obj.code : null,
    message: pickMessage(obj) || (typeof data === "string" ? data : `HTTP ${res.status}`),
    retryAfter: parseRetryAfter(res.headers?.get?.("Retry-After")),
  });
}

// ---- 端點函式 -------------------------------------------------------------

export const analyzeText = (content, opts = {}) =>
  request("/api/analyze/text", { timeoutMs: ANALYZE_TIMEOUT_MS, ...opts, method: "POST", body: { content } });

export const analyzeUrl = (content, opts = {}) =>
  request("/api/analyze/url", { timeoutMs: ANALYZE_TIMEOUT_MS, ...opts, method: "POST", body: { content } });

/** P1（S-13）：multipart 欄位名 `file` */
export function analyzeImage(file, opts = {}) {
  const form = new FormData();
  form.append("file", file);
  return request("/api/analyze/image", { timeoutMs: IMAGE_TIMEOUT_MS, ...opts, method: "POST", body: form });
}

export async function getResult(id, opts = {}) {
  try {
    return await request(`/api/result/${encodeURIComponent(id)}`, opts);
  } catch (err) {
    if (err instanceof ApiError && err.status === 404 && !err.code) err.code = "result_not_found";
    throw err;
  }
}

export const getTrending = ({ limit, risk_type } = {}, opts = {}) =>
  request(withQuery("/api/trending", { limit, risk_type }), opts);

export const getKnowledge = ({ q, risk_type, limit, offset } = {}, opts = {}) =>
  request(withQuery("/api/knowledge", { q, risk_type, limit, offset }), opts);

export const getKnowledgeStats = (opts = {}) => request("/api/knowledge/stats", opts);

/** 熱門頁「本站熱門查證」：最近 7 天被查證次數（時間衰減）排序的已證實內容 */
export const getKnowledgeHot = ({ limit } = {}, opts = {}) =>
  request(withQuery("/api/knowledge/hot", { limit }), opts);

export const getHealth = (opts = {}) => request("/api/health", opts);

export const getThreadsStatus = (opts = {}) => request("/api/threads/status", opts);

export const getThreadsReplies = (limit, opts = {}) =>
  request(withQuery("/api/threads/replies", { limit }), opts);

// ---- fallback 辨識 ---------------------------------------------------------

/** 可傳入 /api/result 的整包、或其中的 result 物件 */
export function isFallback(result) {
  if (!result || typeof result !== "object") return false;
  if (result.ai_unavailable === true) return true;
  if (result.result && typeof result.result === "object" && result.result.ai_unavailable === true) return true;
  const summary = result.summary ?? result.result?.summary;
  return typeof summary === "string" && summary.startsWith(FALLBACK_PREFIX);
}

// ---- 結果輪詢 --------------------------------------------------------------

function sleep(ms, signal) {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) return reject(abortError());
    const t = setTimeout(() => {
      if (signal) signal.removeEventListener("abort", onAbort);
      resolve();
    }, ms);
    function onAbort() {
      clearTimeout(t);
      reject(abortError());
    }
    if (signal) signal.addEventListener("abort", onAbort, { once: true });
  });
}

const TERMINAL = new Set(["completed", "failed"]);

/**
 * 每 intervalMs 查一次 /api/result/{id}，completed／failed 即停。
 * @returns {Promise<{timedOut: boolean, last: any}>}
 * 404 拋 ApiError(code="result_not_found")；其他錯誤照拋；signal 中止拋 AbortError。
 * 輪詢請求帶 cache:"no-store"：/api/result 回 Cache-Control: max-age=5（spec §5.3），
 * 不略過 HTTP 快取時 2 秒後與 4 秒後的輪詢會拿到快取的 pending，完成最多晚 5 秒才被看到（S-04 實測）。
 */
/**
 * 「後端可能正在喚醒」的錯誤：連不上、逾時、或代理回 502／503／504。
 * 免費雲端主機閒置後會休眠，第一個請求要等約 1 分鐘；這類錯誤值得再試，不該立刻當成失敗。
 */
export function isWakingError(err) {
  if (!(err instanceof ApiError)) return false;
  if (err.kind === "network" || err.kind === "timeout") return true;
  return err.kind === "http" && [502, 503, 504].includes(Number(err.status));
}

export async function pollResult(id, { intervalMs = 2000, maxMs = 90000, onUpdate, signal } = {}) {
  const started = Date.now();
  let last = null;
  let wakingError = null;
  for (;;) {
    const remaining = maxMs - (Date.now() - started);
    if (remaining <= 0) {
      // 整段時限內一次都沒連上：回報連線錯誤，而不是「還在處理中」
      if (!last && wakingError) throw wakingError;
      return { timedOut: true, last };
    }
    try {
      last = await getResult(id, {
        signal,
        timeoutMs: Math.min(DEFAULT_GET_TIMEOUT_MS, Math.max(remaining, 1)),
        cache: "no-store",
      });
    } catch (err) {
      // 單次請求被「剩餘時間」截斷而逾時 → 視為整體輪詢超時，而非網路錯誤
      if (err instanceof ApiError && err.kind === "timeout" && Date.now() - started >= maxMs && last) {
        return { timedOut: true, last };
      }
      // 後端喚醒中：在整體時限內繼續試（期間頁面維持載入畫面，AppShell 顯示連線橫幅）；
      // 時限用完還是連不上，才把最後一個錯誤丟出去讓頁面顯示「連不上伺服器」。
      const left = maxMs - (Date.now() - started);
      if (isWakingError(err) && left > 0) {
        wakingError = err;
        await sleep(Math.min(intervalMs, left), signal);
        continue;
      }
      throw err;
    }
    if (typeof onUpdate === "function") onUpdate(last);
    if (last && TERMINAL.has(last.status)) return { timedOut: false, last };
    const left = maxMs - (Date.now() - started);
    if (left <= 0) return { timedOut: true, last };
    await sleep(Math.min(intervalMs, left), signal);
  }
}
