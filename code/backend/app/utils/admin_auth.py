"""
管理端點授權（spec §5.6、§5.7；測試 FN-9）。

- 標頭 X-Admin-Token 與 settings.ADMIN_TOKEN 以 hmac.compare_digest 比對（固定時間）。
- ADMIN_TOKEN 為空字串 → 403 {"code": "admin_disabled"}（避免忘記設定而全開）。
- 缺少或錯誤 → 401 {"code": "unauthorized"}。
- token 本體不寫進 log、也不出現在回應。

用法：Depends(require_admin)（router 層或單一端點）。錯誤格式 {detail, code} 由 main.py
註冊的 admin_auth_error_handler 輸出；AdminAuthError 繼承 HTTPException，未註冊時仍回正確狀態碼。
"""
import hmac
from typing import Optional

from fastapi import Header, HTTPException, Request
from fastapi.responses import JSONResponse

from app.config import settings

MSG_UNAUTHORIZED = "需要管理權限：請在 X-Admin-Token 標頭提供正確的管理 token。"
MSG_ADMIN_DISABLED = "管理功能未啟用：伺服器未設定 ADMIN_TOKEN。"


class AdminAuthError(HTTPException):
    def __init__(self, status_code: int, detail: str, code: str):
        super().__init__(status_code=status_code, detail=detail)
        self.code = code


def require_admin(x_admin_token: Optional[str] = Header(default=None)) -> None:
    expected = (settings.ADMIN_TOKEN or "").strip()
    if not expected:
        raise AdminAuthError(403, MSG_ADMIN_DISABLED, "admin_disabled")
    provided = (x_admin_token or "").strip()
    if not provided or not hmac.compare_digest(provided.encode("utf-8"), expected.encode("utf-8")):
        raise AdminAuthError(401, MSG_UNAUTHORIZED, "unauthorized")


async def admin_auth_error_handler(request: Request, exc: AdminAuthError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail, "code": exc.code})
