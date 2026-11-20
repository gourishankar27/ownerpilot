from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse

from .config import settings


class RfqBodyLimit:
    """Bound multipart bytes before Starlette spools the entire upload."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not scope.get("path", "").startswith("/api/rfq"):
            return await self.app(scope, receive, send)
        headers = dict(scope.get("headers", []))
        limit = settings().max_file_bytes + 1024 * 1024
        try:
            length = int(headers.get(b"content-length", b"0"))
        except ValueError:
            length = limit + 1
        if length > limit:
            return await JSONResponse(
                {"detail": "Request exceeds the RFQ upload limit."}, status_code=413
            )(scope, receive, send)
        size = 0

        async def bounded_receive():
            nonlocal size
            message = await receive()
            size += len(message.get("body", b""))
            if size > limit:
                raise HTTPException(413, "Request exceeds the RFQ upload limit.")
            return message

        await self.app(scope, bounded_receive, send)
