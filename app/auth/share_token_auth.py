from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException

from app.ports.token_port import TokenPort


@dataclass
class ShareTokenClaims:
    tenant_id: str
    document_id: str
    link_id: str
    jti: str
    expires_at: int
    permissions: dict[str, bool]
    require_email: bool
    email: str | None = None


class ShareTokenDependency:
    """Callable dependency that validates a share token."""

    def __init__(self, token_port: TokenPort) -> None:
        self._token_port = token_port

    def __call__(self, token: str) -> ShareTokenClaims:
        try:
            claims = self._token_port.decode_share_token(token)
        except Exception:
            raise HTTPException(status_code=401, detail="Invalid or expired share token")
        return ShareTokenClaims(
            tenant_id=claims.get("tid") or claims.get("tenant_id"),
            document_id=claims.get("sub") or claims.get("document_id"),
            link_id=claims.get("lid") or claims.get("link_id"),
            jti=claims.get("jti"),
            expires_at=claims.get("exp"),
            permissions=claims.get("perms", {}),
            require_email=claims.get("require_email", False),
            email=claims.get("email"),
        )
