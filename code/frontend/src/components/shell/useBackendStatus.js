import { useEffect, useState } from "react";
import { ApiError, BACKEND_DOWN_EVENT, BACKEND_UP_EVENT, getHealth } from "../../lib/api.js";

// 後端可用狀態（P-14；spec §8.3 S1「後端不可用」、§5.1 /health）。
// - 掛載時打一次 GET /api/health（B-22 別名，同源代理）
// - 之後完全由 api.js 派發的事件驅動：任何請求 network／timeout／502–504 → fcc:backend-down；
//   任何成功回應 → fcc:backend-up。所有畫面的 backend_down 橫幅只由 AppShell 顯示。

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

  return { down };
}
