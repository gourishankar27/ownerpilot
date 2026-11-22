from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse


class ProcurementBodyLimit:
    """Bound new JSON workflows before Pydantic parses attacker-sized documents."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        path = scope.get("path", "")
        governed = path.startswith(
            ("/api/quotes", "/api/supplier-offers", "/api/agent-runs")
        ) or (
            path.startswith("/api/rfqs/")
            and path.rsplit("/", 1)[-1]
            in {"quotes", "research", "selection-resolution"}
        )
        if scope["type"] != "http" or not governed:
            return await self.app(scope, receive, send)
        try:
            length = int(dict(scope.get("headers", [])).get(b"content-length", b"0"))
        except ValueError:
            length = 262145
        if length > 262144:
            return await JSONResponse(
                {"detail": "Procurement JSON request limit: 256 KiB"}, status_code=413
            )(scope, receive, send)
        size = 0

        async def bounded():
            nonlocal size
            message = await receive()
            size += len(message.get("body", b""))
            if size > 262144:
                raise HTTPException(413, "Procurement JSON request limit: 256 KiB")
            return message

        await self.app(scope, bounded, send)
