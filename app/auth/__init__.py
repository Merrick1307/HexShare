"""
Authentication and authorisation utilities for HexShare.

This package defines reusable dependencies and middleware for verifying
HexIAM tenant access tokens and share tokens.  These dependencies
integrate with FastAPI and can be injected into route handlers via
``Depends``.  They rely on the :mod:`app.ports.token_port`
interface to perform token validation and extract claims.
"""

from .tenant_auth import TenantAuthDependency, TenantPrincipal
from .external_room_auth import ExternalRoomAuthDependency
from .share_token_auth import ShareTokenDependency, ShareTokenClaims

__all__ = [
    "ExternalRoomAuthDependency",
    "TenantAuthDependency",
    "TenantPrincipal",
    "ShareTokenDependency",
    "ShareTokenClaims",
]
