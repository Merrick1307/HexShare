"""
JWT token adapter.

This adapter implements :class:`~app.ports.TokenPort` using PyJWT
for encoding and decoding JSON Web Tokens.  It provides a simple
in‑memory JTI revocation mechanism suitable for development and
testing.  In a production deployment, revocations should be stored in
a shared cache (e.g. Redis) and tokens should be signed using an
asymmetric algorithm with rotation.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict

import jwt  # type: ignore

from app.ports.token_port import TokenPort


class JWTTokenAdapter(TokenPort):
    """PyJWT implementation of the token port."""

    def __init__(self, secret: str | None = None) -> None:
        self._secret = secret or os.environ.get("HEXSHARE_JWT_SECRET", uuid.uuid4().hex)
        self._revoked_jtis: Dict[str, datetime] = {}

    def generate_jti(self) -> str:
        return uuid.uuid4().hex

    def encode_share_token(
        self,
        *,
        tenant_id: str,
        document_id: str,
        link_id: str,
        jti: str,
        expires_at: datetime,
        permissions: Dict[str, bool],
        require_email: bool,
    ) -> str:
        payload = {
            "sub": document_id,
            "tid": tenant_id,
            "lid": link_id,
            "jti": jti,
            "exp": int(expires_at.replace(tzinfo=timezone.utc).timestamp()),
            "perms": permissions,
            "require_email": require_email,
        }
        token = jwt.encode(payload, self._secret, algorithm="HS256")
        return token

    def decode_share_token(self, token: str) -> Dict[str, Any]:
        payload = jwt.decode(token, self._secret, algorithms=["HS256"])
        jti: str = payload.get("jti")
        # Check revocation list
        now = datetime.now(timezone.utc)
        # Clean expired revocations
        expired = [key for key, exp in self._revoked_jtis.items() if exp <= now]
        for key in expired:
            self._revoked_jtis.pop(key, None)
        if jti in self._revoked_jtis:
            raise jwt.InvalidTokenError("Token has been revoked")
        return payload

    async def revoke_jti(self, jti: str, expires_at: datetime) -> None:
        self._revoked_jtis[jti] = expires_at


