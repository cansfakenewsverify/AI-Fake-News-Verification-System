import { useEffect, useState } from "react";
import { ApiError, BACKEND_DOWN_EVENT, BACKEND_UP_EVENT, getHealth } from "../../lib/api.js";

// 後端可用狀態（P-14；spec §8.3 S1「後端不可用」、§5.1 /health）。
// - 掛載時打一次 GET /api/health（B-22 別名，同源代理）
// - 之後完全由 api.js 派發的事件驅動：任何請求 network／timeout／502–504 → fcc:backend-down；
//   任何成功回應 → fcc:backend-up。所有畫面的 backend_down 橫幅只由 AppShell 顯示。
// - 橫幅顯示期間每 10 秒自動重試 /api/health，成功就自己消失：雲端免費主機休眠後第一次喚醒
//   約 1 分鐘，使用者不必手動重新整理。

/**
 * 健康檢查失敗是否代表「連不上伺服器」。
 * network／timeout 與 5xx（Vite 代理 502、Cloudflare tunnel 530）算；
 * 4xx 代表請求有到後端（例如 /api/health 別名尚未部署）→ 不顯示橫幅；
 * AbortError（卸載中止）不是 ApiError → 不判定。
 */
export function isBackendDownError(err) {
  if (!(err instanceof ApiError)) return false;
  if (err.kind === "network" || err.kind === "timeout") return true;
  return err.kind === "http" && Number(err.status) >= 500;
}

export const HEALTH_RETRY_MS = 10000;

/**
 * 每 intervalMs 呼叫一次 check()，回傳停止函式。上一次還沒結束就跳過這一輪
 * （health 逾時 15 秒比間隔長，不疊加請求）。check 的成功／失敗由呼叫端自己處理。
 */
export function startHealthRetry(check, { intervalMs = HEALTH_RETRY_MS, timers = globalThis } = {}) {
  let busy = false;
  const id = timers.setInterval(() => {
    if (busy) return;
    busy = true;
    Promise.resolve()
      .then(check)
      .catch(() => {})
      .finally(() => {
        busy = false;
      });
  }, intervalMs);
  return () => timers.clearInterval(id);
}

export function useBackendStatus() {
  const [down, setDown] = useState(false);

  useEffect(() => {
    const onDown = () => setDown(true);
    const onUp = () => setDown(false);
    window.addEventListener(BACKEND_DOWN_EVENT, onDown);
    window.addEventListener(BACKEND_UP_EVENT, onUp);

    const controller = new AbortController();
    // 成功時 api.js 已派發 backend-up；失敗只補判 api.js 不派發事件的 5xx（如 500、530）
    getHealth({ signal: controller.signal }).catch((err) => {
      if (!controller.signal.aborted && isBackendDownError(err)) setDown(true);
    });

    return () => {
      controller.abort();
      window.removeEventListener(BACKEND_DOWN_EVENT, onDown);
      window.removeEventListener(BACKEND_UP_EVENT, onUp);
    };
  }, []);

  useEffect(() => {
    if (!down) return undefined;
    // 成功時 api.js 派發 backend-up → setDown(false) → 這個 effect 清掉、停止重試
    return startHealthRetry(() => getHealth());
  }, [down]);

  return { down };
}
