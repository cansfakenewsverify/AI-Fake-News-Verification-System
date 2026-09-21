// 開發用 fixture 模式（P-10）：`VITE_FIXTURES=1 npm run dev` 時 api.js 的 request() 不發 fetch，
// 改由本模組依「API 路徑 + 頁面網址 ?fixture=」讀 src/dev/fixtures/*.json。
// - loader 以參數注入（node --test 用假 loader；瀏覽器用 viteFixtureLoader()）
// - fixture JSON 可帶 `_status`（HTTP 狀態）與 `_headers`（如 Retry-After），
//   回傳的回應物件與 fetch Response 同形，交給 api.js 走相同的 ApiError 正規化
// - production build 不含任何 fixture：api.js 只在 import.meta.env.DEV 分支呼叫 viteFixtureLoader()
// 對應規則見 src/dev/fixtures/README.md（改規則時兩處一起改）。

export const KNOWLEDGE_PAGE_SIZE = 30;

function withJson(name) {
  return name.endsWith(".json") ? name : `${name}.json`;
}

function fixtureParam(search) {
  const s = typeof search === "function" ? search() : search;
  if (!s) return "";
  try {
    return new URLSearchParams(s).get("fixture") || "";
  } catch {
    return "";
  }
}

/**
 * API 路徑（可含 query）→ fixture 檔名；無對應規則回 null。
 * @param {string} path   例如 `/api/knowledge?offset=30`
 * @param {string} method GET/POST
 * @param {string|(() => string)} search 頁面網址的 location.search（取 `fixture` 參數）
 */
export function resolveFixtureName(path, method = "GET", search = "") {
  const [pathname, query = ""] = String(path).split("?");
  const params = new URLSearchParams(query);
  const fx = fixtureParam(search);
  const upper = String(method).toUpperCase();

  if (upper === "POST" && pathname.startsWith("/api/analyze/")) {
    return fx ? withJson(fx) : "analyze_text_ok.json";
  }
  if (upper !== "GET") return null;

  const result = pathname.match(/^\/api\/result\/([^/]+)$/);
  if (result) {
    let id;
    try {
      id = decodeURIComponent(result[1]);
    } catch {
      return null;
    }
    // id 只允許安全字元，避免組出 ../ 之類的檔名
    return /^[\w.-]+$/.test(id) && !id.includes("..") ? `result_${id}.json` : null;
  }
  if (pathname === "/api/trending") return fx === "empty" ? "trending_empty.json" : "trending_ok.json";
  if (pathname === "/api/knowledge/stats") return "knowledge_stats.json";
  if (pathname === "/api/knowledge/hot") return fx === "empty" ? "knowledge_hot_empty.json" : "knowledge_hot.json";
  if (pathname === "/api/knowledge") {
    if (fx === "empty") return "knowledge_empty.json";
    const offset = Math.max(0, Number(params.get("offset")) || 0);
    return `knowledge_page${Math.floor(offset / KNOWLEDGE_PAGE_SIZE) + 1}.json`;
  }
  if (pathname === "/api/threads/status") {
    const v = /^[\w-]+$/.test(fx) ? fx : "sim";
    return `threads_status_${v}.json`;
  }
  if (pathname === "/api/threads/replies") return "threads_replies.json";
  if (pathname === "/api/health") return "health_ok.json";
  return null;
}

function makeResponse(status, body, headers = {}) {
  const lower = {};
  for (const [k, v] of Object.entries(headers || {})) lower[k.toLowerCase()] = String(v);
  const text = body === undefined || status === 204 ? "" : JSON.stringify(body);
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: { get: (k) => lower[String(k).toLowerCase()] ?? null },
    text: async () => text,
  };
}

/**
 * 以注入的 loader 產生「假 fetch 回應」。
 * loader(name) 回傳 JSON 物件（或 Promise）；檔案不存在回 null/undefined。
 * @returns {Promise<{ok, status, headers:{get}, text}>}
 */
export async function fixtureResponse(path, { method = "GET", loader, search = "" } = {}) {
  const name = resolveFixtureName(path, method, search);
  let data = null;
  if (name && typeof loader === "function") {
    try {
      data = await loader(name);
    } catch {
      data = null;
    }
  }
  if (data == null) {
    return makeResponse(404, {
      detail: `fixture not found: ${name || path}`,
      code: /^\/api\/result\//.test(String(path)) ? "result_not_found" : "fixture_not_found",
    });
  }
  if (typeof data !== "object" || Array.isArray(data)) return makeResponse(200, data);
  const { _status, _headers, ...body } = data;
  const status = Number.isInteger(_status) ? _status : 200;
  return makeResponse(status, body, _headers);
}

/**
 * 瀏覽器（Vite dev）用 loader：import.meta.glob 懶載入 src/dev/fixtures/*.json。
 * 只能在 import.meta.env.DEV 分支內呼叫，production build 會整段剔除。
 */
export function viteFixtureLoader() {
  const modules = import.meta.glob("../dev/fixtures/*.json", { import: "default" });
  return async (name) => {
    const load = modules[`../dev/fixtures/${name}`];
    return load ? load() : null;
  };
}
