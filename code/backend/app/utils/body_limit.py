"""
請求內容大小上限（spec §5.7 `payload_too_large`；公開上線前必備）。

uvicorn 本身不限制請求大小，而 FastAPI 在進到端點「之前」就會把整個 body（含上傳檔）收完，
所以大小限制只能做在 middleware：
- 有 Content-Length 且超過上限 → 直接回 413，不讀 body。
- 沒有 Content-Length（chunked）→ 邊收邊數，超過就中斷並回 413。
圖片上傳端點的上限較大（IMAGE_MAX_BYTES + multipart 表頭的餘裕），其餘端點只收小型 JSON。
"""
import json
from typing import Dict, Optional

from fastapi import HTTPException

MSG_PAYLOAD_TOO_LARGE = "內容太大，無法處理。"
IMAGE_MAX_BYTES = 10 * 1024 * 1024          # FR-03：圖片 10 MB 以內
DEFAULT_MAX_BODY_BYTES = 1 * 1024 * 1024    # 文字上限 20,000 字（UTF-8 約 60 KB），1 MB 綽綽有餘
PATH_MAX_BODY_BYTES: Dict[str, int] = {
    "/api/analyze/image": IMAGE_MAX_BYTES + 1 * 1024 * 1024,
}


class PayloadTooLarge(HTTPException):
    """FastAPI 解析 body 時只會原樣往上拋 HTTPException（其他例外會被改成 400），所以繼承它。"""

    def __init__(self) -> None:
        super().__init__(status_code=413, detail=MSG_PAYLOAD_TOO_LARGE)


def payload_too_large_body() -> Dict[str, str]:
    return {"detail": MSG_PAYLOAD_TOO_LARGE, "code": "payload_too_large"}


class BodySizeLimitMiddleware:
    """純 ASGI middleware（不用 BaseHTTPMiddleware：那個會先把整個 body 讀進記憶體）。"""

    def __init__(self, app, default_limit: int = DEFAULT_MAX_BODY_BYTES,
                 path_limits: Optional[Dict[str, int]] = None):
        self.app = app
        self.default_limit = default_limit
        self.path_limits = dict(PATH_MAX_BODY_BYTES if path_limits is None else path_limits)

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope.get("method") in ("GET", "HEAD", "OPTIONS"):
            await self.app(scope, receive, send)
            return

        limit = self.path_limits.get(scope.get("path", ""), self.default_limit)
        declared = _content_length(scope)
        if declared is not None and declared > limit:
            await _send_413(send)
            return

        received = 0

        async def limited_receive():
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body") or b"")
                if received > limit:
                    raise PayloadTooLarge()
            return message

        await self.app(scope, limited_receive, send)


def _content_length(scope) -> Optional[int]:
    for name, value in scope.get("headers") or []:
        if name == b"content-length":
            try:
                return int(value)
            except ValueError:
                return None
    return None


async def _send_413(send) -> None:
    body = json.dumps(payload_too_large_body(), ensure_ascii=False).encode("utf-8")
    await send({
        "type": "http.response.start",
        "status": 413,
        "headers": [
            (b"content-type", b"application/json; charset=utf-8"),
            (b"content-length", str(len(body)).encode("ascii")),
        ],
    })
    await send({"type": "http.response.body", "body": body})
