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
from typing import Sequence, Callable

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.adapters.auth import HEXIAMAuthenticator
from app.core.authz import AUTH_COOKIE
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

    def __init__(self, authenticator: AuthenticatorPort = HEXIAMAuthenticator()) -> None:
        self._token_port = authenticator

    def __call__(self) -> Callable:
        def verify(credentials: HTTPAuthorizationCredentials = Depends(_http_bearer), request: Request = None):
            token = None

            # 1) Prefer Authorization header (API clients)
            if credentials:
                token = credentials.credentials

            # 2) Fallback to cookie (browser)
            if not token:
                token = request.cookies.get(AUTH_COOKIE)

            if not token:
                raise HTTPException(status_code=401, detail="Missing auth token")

            try:
                payload = self._token_port.authenticate(token)
            except Exception:
                raise HTTPException(status_code=401, detail="Invalid or expired token")
            tenant_id = payload.tenant_id
            user_id = payload.subject or payload.user_id
            if not tenant_id or not user_id:
                print(payload)
                raise HTTPException(status_code=401, detail="Token missing tenant or user claims")
            roles = payload.roles
            return TenantPrincipal(tenant_id=tenant_id, user_id=user_id, roles=roles)
        return verify


def get_tenant_auth() -> TenantPrincipal:
    return TenantAuthDependency()()

