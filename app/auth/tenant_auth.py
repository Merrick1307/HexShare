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
from typing import Sequence

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.ports.authn import AuthenticatorPort
from app.ports.token_port import TokenPort


_http_bearer = HTTPBearer(auto_error=False)


@dataclass
class TenantPrincipal:
    """Represents the authenticated tenant and user."""
    tenant_id: str
    user_id: str
    roles: Sequence[str] | None = None


class TenantAuthDependency:
    """Factory for FastAPI dependency that authenticates tenant tokens."""

    def __init__(self, authenticator: AuthenticatorPort) -> None:
        self._token_port = authenticator

    async def __call__(
        self, credentials: HTTPAuthorizationCredentials = Depends(_http_bearer)
    ) -> TenantPrincipal:
        if not credentials:
            raise HTTPException(status_code=401, detail="Missing Authorization header")
        token = credentials.credentials
        try:
            payload = await self._token_port.authenticate(token)
        except Exception:
            raise HTTPException(status_code=401, detail="Invalid or expired token")
        tenant_id = payload.tenant_id
        user_id = payload.subject or payload.user_id
        if not tenant_id or not user_id:
            raise HTTPException(status_code=401, detail="Token missing tenant or user claims")
        roles = payload.roles
        return TenantPrincipal(tenant_id=tenant_id, user_id=user_id, roles=roles)
