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

from app.domain import (
    ExternalAccessGrant,
    ExternalAccessGrantType,
    ExternalAccessResourceType,
    ExternalParty,
    ExternalPartyEmail,
    ExternalPartyStatus,
    ShareLink,
    ShareLinkAccessMode,
)
from app.core.authz import ResourceAction
from app.ports.storage_port import StoragePort
from app.ports.token_port import TokenPort
from app.ports import EventBusPort


class LinkService:
    """Business logic for share link lifecycle."""

    def __init__(self, storage: StoragePort, token_port: TokenPort, event_bus: EventBusPort) -> None:
        self._storage = storage
        self._token_port = token_port
        self._event_bus = event_bus

    @staticmethod
    def _normalize_email(email: str | None) -> str | None:
        if email is None:
            return None
        normalized = email.strip().lower()
        return normalized or None

    @staticmethod
    def _document_permissions(*, can_download: bool) -> int:
        mask = int(ResourceAction.READ)
        if can_download:
            mask |= int(ResourceAction.EXPORT)
        return mask

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
        recipient_email: str | None = None,
        recipient_display_name: str | None = None,
    ) -> ShareLink:
        """Create a new share link and return its record.

        A JWT is generated representing the share link; the ``jti`` in
        the token is stored to support revocation.  The caller is
        expected to use the :meth:`generate_share_token` method to
        obtain the actual token string.
        """
        link_id = self._storage.generate_id("link")
        jti = self._token_port.generate_jti()
        now = datetime.utcnow()
        expires_at = now + timedelta(seconds=expires_in_seconds)
        normalized_recipient_email = self._normalize_email(recipient_email)
        recipient_label = (recipient_display_name or "").strip() or None
        external_access_grant_id: str | None = None
        access_mode = ShareLinkAccessMode.ANONYMOUS
        bound_email_normalized: str | None = None

        if normalized_recipient_email:
            require_email = True
            allowed_emails = [normalized_recipient_email]
            access_mode = ShareLinkAccessMode.IDENTIFIED
            bound_email_normalized = normalized_recipient_email

            external_party = await self._storage.get_external_party_by_email(
                tenant_id=tenant_id,
                email_normalized=normalized_recipient_email,
            )
            if external_party is None:
                external_party = ExternalParty(
                    id=self._storage.generate_id("ep"),
                    tenant_id=tenant_id,
                    display_name=recipient_label,
                    status=ExternalPartyStatus.ACTIVE,
                    created_by=created_by,
                    created_at=now,
                    updated_at=now,
                    archived_at=None,
                )
            elif recipient_label and external_party.display_name != recipient_label:
                external_party = external_party.copy(
                    update={"display_name": recipient_label, "updated_at": now}
                )
            await self._storage.save_external_party(external_party)
            await self._storage.save_external_party_email(
                ExternalPartyEmail(
                    id=self._storage.generate_id("epe"),
                    tenant_id=tenant_id,
                    external_party_id=external_party.id,
                    email_normalized=normalized_recipient_email,
                    email_original=recipient_email or normalized_recipient_email,
                    is_primary=True,
                    verified_at=None,
                    last_seen_at=None,
                    created_at=now,
                )
            )

            external_access_grant_id = self._storage.generate_id("eag")
            await self._storage.save_external_access_grant(
                ExternalAccessGrant(
                    id=external_access_grant_id,
                    tenant_id=tenant_id,
                    external_party_id=external_party.id,
                    resource_type=ExternalAccessResourceType.DOCUMENT,
                    resource_id=document_id,
                    grant_type=ExternalAccessGrantType.LINK,
                    permissions=self._document_permissions(can_download=can_download),
                    can_download=can_download,
                    can_print=can_print,
                    expires_at=expires_at,
                    revoked_at=None,
                    granted_by=created_by,
                    granted_at=now,
                    updated_at=now,
                )
            )

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
            external_access_grant_id=external_access_grant_id,
            access_mode=access_mode,
            bound_email_normalized=bound_email_normalized,
            revoked_at=None,
            created_at=now,
            created_by=created_by,
        )
        await self._storage.save_share_link(share_link)
        token = await self.generate_share_token(share_link)
        # Emit document.shared event for email notification
        if normalized_recipient_email:
            document = await self._storage.get_document(tenant_id=tenant_id, document_id=document_id)
            await self._event_bus.publish_event(
                tenant_id,
                "document.shared",
                {
                    "recipient_email": normalized_recipient_email,
                    "recipient_name": recipient_label or "User",
                    "document_name": document.name if document else "Document",
                    "document_id": document_id,
                    "shared_by": created_by,
                    "shared_by_name": "Someone on HexShare",  # TODO: Get actual user name
                    "access_link": token,  # TODO: Generate actual token URL
                    "expires_at": expires_at.isoformat(),
                    "can_download": can_download,
                    "can_print": can_print,
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
        if link.external_access_grant_id:
            await self._storage.revoke_external_access_grant(
                tenant_id=tenant_id,
                grant_id=link.external_access_grant_id,
                revoked_at=now,
            )
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
