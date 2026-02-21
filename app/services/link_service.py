"""
Service for managing document share links.

This service creates and revokes share links.  It relies on a storage
port to persist link state, a token port to generate and decode JWT
tokens, and an event bus to publish audit events.  Share links
determine how a document can be accessed by external visitors.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Iterable, Optional

from app.domain import ShareLink
from app.ports.storage_port import StoragePort
from app.ports.token_port import TokenPort
from app.ports import EventBusPort


class LinkService:
    """Business logic for share link lifecycle."""

    def __init__(self, storage: StoragePort, token_port: TokenPort, event_bus: EventBusPort) -> None:
        self._storage = storage
        self._token_port = token_port
        self._event_bus = event_bus

    async def create_share_link(
        self,
        *,
        tenant_id: str,
        document_id: str,
        created_by: str,
        expires_in_seconds: int,
        can_download: bool = False,
        can_print: bool = False,
        require_email: bool = False,
        allowed_emails: Optional[list[str]] = None,
    ) -> ShareLink:
        """Create a new share link and return its record.

        A JWT is generated representing the share link; the ``jti`` in
        the token is stored to support revocation.  The caller is
        expected to use the :meth:`generate_share_token` method to
        obtain the actual token string.
        """
        link_id = self._storage.generate_id("link")
        jti = self._token_port.generate_jti()
        expires_at = datetime.utcnow() + timedelta(seconds=expires_in_seconds)
        share_link = ShareLink(
            id=link_id,
            tenant_id=tenant_id,
            document_id=document_id,
            jti=jti,
            expires_at=expires_at,
            can_download=can_download,
            can_print=can_print,
            require_email=require_email,
            allowed_emails=allowed_emails or [],
            revoked_at=None,
            created_at=datetime.utcnow(),
            created_by=created_by,
        )
        await self._storage.save_share_link(share_link)
        await self._event_bus.publish_event(
            tenant_id,
            "link.created",
            {
                "link_id": link_id,
                "document_id": document_id,
                "created_by": created_by,
                "expires_at": expires_at.isoformat(),
            },
        )
        return share_link

    async def generate_share_token(self, link: ShareLink) -> str:
        """Generate a signed JWT string for a share link."""
        return self._token_port.encode_share_token(
            tenant_id=link.tenant_id,
            document_id=link.document_id,
            link_id=link.id,
            jti=link.jti,
            expires_at=link.expires_at,
            permissions={
                "download": link.can_download,
                "print": link.can_print,
            },
            require_email=link.require_email,
        )

    async def revoke_share_link(self, *, tenant_id: str, link_id: str, revoked_by: str) -> None:
        """Revoke an existing share link.

        Revoking a link sets ``revoked_at`` on the record and adds the
        link's JTI to the revocation list via the token port.  Visitors
        with the old token will be blocked immediately.
        """
        link = await self._storage.get_share_link(tenant_id=tenant_id, link_id=link_id)
        if link is None:
            return
        now = datetime.utcnow()
        # Persist revocation on the link record
        await self._storage.revoke_share_link(tenant_id=tenant_id, link_id=link_id, revoked_at=now)
        # Record the JTI in the revocation set so tokens are invalidated
        await self._token_port.revoke_jti(link.jti, expires_at=link.expires_at)
        await self._event_bus.publish_event(
            tenant_id,
            "link.revoked",
            {
                "link_id": link_id,
                "revoked_by": revoked_by,
            },
        )

    async def get_share_link(self, *, tenant_id: str, link_id: str) -> ShareLink | None:
        """Fetch a share link by ID."""
        return await self._storage.get_share_link(tenant_id=tenant_id, link_id=link_id)

    async def list_share_links(self, *, tenant_id: str, document_id: Optional[str] = None) -> Iterable[ShareLink]:
        """List share links for a tenant, optionally filtered by document."""
        return await self._storage.list_share_links(tenant_id=tenant_id, document_id=document_id)
