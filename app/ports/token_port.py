"""
Token port interface.

This port defines the operations for creating, decoding and revoking
share tokens.  It is separate from HexIAM token processing; the
``TokenPort`` deals with tokens used for share links and optionally
admin/tenant authentication.  Implementations might use PyJWT,
authlib or another JWT library.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict


class TokenPort(ABC):
    """Abstract base class for token generation and validation."""

    @abstractmethod
    def generate_jti(self) -> str:
        """Generate a new unique JTI (JWT ID) for a share token."""

    @abstractmethod
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
        """Create a JWT string representing a share link.

        The claims should include the tenant, document, link ID, JTI,
        expiry and any additional permissions required by the viewer.
        """

    @abstractmethod
    def decode_share_token(self, token: str) -> Dict[str, Any]:
        """Decode and validate a share token.

        This method should verify the signature, expiry and ensure the
        JTI has not been revoked.  It returns a dictionary of claims
        extracted from the token.  An exception may be raised if the
        token is invalid or expired.
        """

    @abstractmethod
    async def revoke_jti(self, jti: str, expires_at: datetime) -> None:
        """Mark a JTI as revoked until ``expires_at``.

        Revoking a JTI will cause calls to :meth:`decode_share_token`
        with a token containing this JTI to fail.  Implementations
        typically store the revoked JTI in a Bloom filter or set.
        """
