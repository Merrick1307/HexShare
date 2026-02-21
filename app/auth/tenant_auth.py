"""
Tenant authentication dependency.

This module defines a FastAPI dependency for extracting tenant and user
information from HexIAM access tokens.  The dependency expects an
``Authorization: Bearer <token>`` header.  It decodes the token via
``TokenPort.decode_share_token`` for demonstration purposes.  In a
production system you should integrate with HexIAM's OIDC or
introspection endpoints to validate access tokens.
"""
from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.ports.token_port import TokenPort


_http_bearer = HTTPBearer(auto_error=False)


@dataclass
class TenantPrincipal:
    """Represents the authenticated tenant and user."""
    tenant_id: str
    user_id: str
    roles: list[str] | None = None


class TenantAuthDependency:
    """Factory for FastAPI dependency that authenticates tenant tokens."""

    def __init__(self, token_port: TokenPort) -> None:
        self._token_port = token_port

    async def __call__(
        self, credentials: HTTPAuthorizationCredentials = Depends(_http_bearer)
    ) -> TenantPrincipal:
        if not credentials:
            raise HTTPException(status_code=401, detail="Missing Authorization header")
        token = credentials.credentials
        try:
            payload = self._token_port.decode_share_token(token)
        except Exception:
            # In a real implementation you would distinguish error types
            raise HTTPException(status_code=401, detail="Invalid or expired token")
        tenant_id = payload.get("tid") or payload.get("tenant_id")
        user_id = payload.get("sub") or payload.get("user_id")
        if not tenant_id or not user_id:
            raise HTTPException(status_code=401, detail="Token missing tenant or user claims")
        roles = payload.get("roles")
        return TenantPrincipal(tenant_id=tenant_id, user_id=user_id, roles=roles)
