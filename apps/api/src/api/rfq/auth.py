import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from uuid import UUID

from fastapi import Header, HTTPException, Request

from .config import settings
from .db import connection


@dataclass(frozen=True)
class Identity:
    user_id: str
    workspace_id: str
    role: str

    def require_write(self):
        if self.role not in {"owner", "admin", "reviewer", "editor"}:
            raise HTTPException(403, "This workspace role cannot edit RFQs.")

    def require_approve(self):
        if self.role not in {"owner", "admin", "reviewer"}:
            raise HTTPException(
                403, "Owner, admin or reviewer role is required for approval."
            )


def authenticate(request: Request, authorization: str = Header(default="")) -> Identity:
    secret = settings().auth_secret
    if len(secret) < 32:
        raise HTTPException(
            503,
            "RFQ authentication is not configured. Set RFQ_AUTH_SECRET on web and API.",
        )
    try:
        scheme, token = authorization.split(" ", 1)
        payload, signature = token.split(".")
        expected = hmac.new(
            secret.encode(), payload.encode(), hashlib.sha256
        ).hexdigest()
        if scheme != "Bearer" or not hmac.compare_digest(expected, signature):
            raise ValueError
        claims = json.loads(
            base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4))
        )
        now = int(time.time())
        if (
            not now - 65 <= claims["iat"] <= now + 5
            or not now <= claims["exp"] <= now + 65
            or not 0 < claims["exp"] - claims["iat"] <= 60
        ):
            raise ValueError
        if claims["method"] != request.method or claims["path"] != request.url.path:
            raise ValueError
        user = claims["sub"]
        workspace = str(UUID(claims["workspace"]))
        if not isinstance(user, str) or not user or len(user) > 200:
            raise ValueError
    except (ValueError, KeyError, TypeError, AttributeError):
        raise HTTPException(401, "Valid authenticated RFQ session required.") from None
    with connection() as conn:
        membership = conn.execute(
            "select role from public.workspace_members where workspace_id=%s and user_id=%s",
            (workspace, user),
        ).fetchone()
    if not membership:
        raise HTTPException(403, "You are not a member of this workspace.")
    return Identity(user, workspace, membership["role"])
