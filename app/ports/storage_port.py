"""
Storage port interface.

The :class:`StoragePort` defines the operations required to persist and
retrieve HexShare domain entities.  It abstracts over the actual storage
mechanism (e.g. SQL database, NoSQL store, filesystem).  Implementations
are responsible for enforcing tenant isolation and returning domain
objects rather than raw database rows.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterable, Optional

from datetime import datetime

from app.domain import (
    Document,
    DocumentGroup,
    DocumentPermission,
    ExternalAccessGrant,
    ExternalParty,
    ExternalPartyEmail,
    ExternalRoomEvent,
    ExternalRoomSession,
    ShareLink,
    VisitorSession,
    ViewEvent,
)


class StoragePort(ABC):
    """Abstract base class for document and link persistence."""

    @abstractmethod
    def generate_id(self, prefix: str) -> str:
        """Generate a new unique identifier for a given entity prefix.

        Implementations may use UUIDs, database sequences or other
        mechanisms.  The prefix is provided to assist in debugging and
        log inspection.
        """

    @abstractmethod
    async def save_document(self, document: Document) -> None:
        """Persist a document metadata record."""

    @abstractmethod
    async def get_document(self, *, tenant_id: str, document_id: str) -> Optional[Document]:
        """Retrieve a document by ID if it exists and belongs to the tenant."""

    @abstractmethod
    async def list_documents(self, *, tenant_id: str) -> Iterable[Document]:
        """List all documents for a tenant."""

    @abstractmethod
    async def save_share_link(self, link: ShareLink) -> None:
        """Persist a share link."""

    @abstractmethod
    async def get_share_link(self, *, tenant_id: str, link_id: str) -> Optional[ShareLink]:
        """Return a share link by ID if it exists and belongs to the tenant."""

    @abstractmethod
    async def list_share_links(
        self, *, tenant_id: str, document_id: Optional[str] = None
    ) -> Iterable[ShareLink]:
        """List share links for a tenant, optionally filtered by document."""

    @abstractmethod
    async def revoke_share_link(
        self, *, tenant_id: str, link_id: str, revoked_at: Optional[datetime]
    ) -> None:
        """Mark a share link as revoked."""

    @abstractmethod
    async def save_visitor_session(self, session: VisitorSession) -> None:
        """Persist a visitor session."""

    @abstractmethod
    async def get_visitor_session(self, *, tenant_id: str, session_id: str) -> Optional[VisitorSession]:
        """Return a visitor session by ID if it exists and belongs to the tenant."""

    @abstractmethod
    async def get_visitor_session_by_id(self, *, session_id: str) -> Optional[VisitorSession]:
        """Return a visitor session by ID irrespective of tenant."""

    @abstractmethod
    async def end_visitor_session(self, *, tenant_id: str, session_id: str, ended_at: datetime) -> None:
        """Mark a visitor session as ended."""

    @abstractmethod
    async def list_visitor_sessions(
        self, *, tenant_id: str, document_id: str
    ) -> Iterable[VisitorSession]:
        """List visitor sessions for a specific document."""

    @abstractmethod
    async def save_view_event(self, event: ViewEvent) -> None:
        """Persist a view event."""

    @abstractmethod
    async def list_view_events(
        self, *, tenant_id: str, document_id: str
    ) -> Iterable[ViewEvent]:
        """List view events for a specific document."""

    @abstractmethod
    async def get_latest_page_view_event(
        self, *, tenant_id: str, visitor_session_id: str
    ) -> Optional[ViewEvent]:
        """Return the latest page-view event for a visitor session."""

    @abstractmethod
    async def update_view_event_duration(
        self, *, tenant_id: str, event_id: str, duration_ms: int
    ) -> None:
        """Persist a computed duration for an existing view event."""

    @abstractmethod
    async def save_document_permission(self, permission: DocumentPermission) -> None:
        """Insert or replace a document permission row."""

    @abstractmethod
    async def get_document_permission(
        self, *, tenant_id: str, document_id: str, user_id: str
    ) -> Optional[DocumentPermission]:
        """Return the permission row for ``(document, user)`` if any."""

    @abstractmethod
    async def revoke_document_permission(
        self, *, tenant_id: str, document_id: str, user_id: str
    ) -> None:
        """Remove a user's permission on a document."""

    @abstractmethod
    async def delete_document(self, *, tenant_id: str, document_id: str) -> None:
        """Remove a document and all its associated data."""

    @abstractmethod
    async def list_document_permissions(
        self, *, tenant_id: str, document_id: str
    ) -> Iterable[DocumentPermission]:
        """Return every permission row for a document."""

    @abstractmethod
    async def list_ungrouped_documents_by_permission(
        self, *, tenant_id: str, user_id: str, required_permission: int
    ) -> Iterable[Document]:
        """Return ungrouped documents the user has the requested permission on.

        Only documents with ``room_id IS NULL`` are considered; access to
        grouped documents is gated by the IAM provider via room policies.
        """

    @abstractmethod
    async def list_documents_by_room(
        self, *, tenant_id: str, room_id: str
    ) -> Iterable[Document]:
        """Return every document belonging to a room/group."""

    @abstractmethod
    async def save_document_group(self, group: DocumentGroup) -> None:
        """Persist a new document group."""

    @abstractmethod
    async def get_document_group(
        self, *, tenant_id: str, group_id: str
    ) -> Optional[DocumentGroup]:
        """Return a single document group by ID."""

    @abstractmethod
    async def list_document_groups_by_ids(
        self, *, tenant_id: str, group_ids: Iterable[str]
    ) -> Iterable[DocumentGroup]:
        """Return the document groups whose IDs are in ``group_ids``."""

    @abstractmethod
    async def update_document_group(
        self,
        *,
        tenant_id: str,
        group_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
    ) -> Optional[DocumentGroup]:
        """Patch a group's mutable metadata. Returns the updated group or None."""

    @abstractmethod
    async def delete_document_group(self, *, tenant_id: str, group_id: str) -> None:
        """Delete a group. ``documents.room_id`` is nullified via FK cascade."""

    @abstractmethod
    async def update_document_room(
        self, *, tenant_id: str, document_id: str, room_id: Optional[str]
    ) -> Optional[Document]:
        """Move a document to a group (room_id) or remove from group (room_id=None)."""

    @abstractmethod
    async def save_external_party(self, party: ExternalParty) -> None:
        """Insert or update an external party record."""

    @abstractmethod
    async def get_external_party(
        self, *, tenant_id: str, external_party_id: str
    ) -> Optional[ExternalParty]:
        """Return an external party by ID."""

    @abstractmethod
    async def get_external_party_by_email(
        self, *, tenant_id: str, email_normalized: str
    ) -> Optional[ExternalParty]:
        """Return the external party whose primary/known email matches."""

    @abstractmethod
    async def save_external_party_email(self, email: ExternalPartyEmail) -> None:
        """Insert or update a party email binding."""

    @abstractmethod
    async def get_external_party_primary_email(
        self, *, tenant_id: str, external_party_id: str
    ) -> Optional[ExternalPartyEmail]:
        """Return the primary email record for an external party."""

    @abstractmethod
    async def mark_external_party_email_seen(
        self,
        *,
        tenant_id: str,
        email_normalized: str,
        seen_at: datetime,
        verified_at: Optional[datetime] = None,
    ) -> None:
        """Update last-seen and optional verified timestamps for an email."""

    @abstractmethod
    async def save_external_access_grant(self, grant: ExternalAccessGrant) -> None:
        """Insert or update an external access grant."""

    @abstractmethod
    async def get_external_access_grant(
        self, *, tenant_id: str, grant_id: str
    ) -> Optional[ExternalAccessGrant]:
        """Return an external access grant by ID."""

    @abstractmethod
    async def revoke_external_access_grant(
        self, *, tenant_id: str, grant_id: str, revoked_at: datetime
    ) -> None:
        """Mark an external access grant as revoked."""

    @abstractmethod
    async def list_external_access_grants(
        self,
        *,
        tenant_id: str,
        external_party_id: str | None = None,
        resource_type: str | None = None,
        resource_id: str | None = None,
    ) -> Iterable[ExternalAccessGrant]:
        """List external grants filtered by tenant and optional attributes."""

    @abstractmethod
    async def save_external_room_session(self, session: ExternalRoomSession) -> None:
        """Persist an external room session."""

    @abstractmethod
    async def get_external_room_session(
        self, *, tenant_id: str, session_id: str
    ) -> Optional[ExternalRoomSession]:
        """Return an external room session by ID."""

    @abstractmethod
    async def end_external_room_session(
        self, *, tenant_id: str, session_id: str, ended_at: datetime
    ) -> None:
        """Mark an external room session as closed."""

    @abstractmethod
    async def list_external_room_sessions(
        self, *, tenant_id: str
    ) -> Iterable[ExternalRoomSession]:
        """List external room sessions for a tenant."""

    @abstractmethod
    async def save_external_room_event(self, event: ExternalRoomEvent) -> None:
        """Persist an external room audit event."""

    @abstractmethod
    async def list_external_room_events(
        self, *, tenant_id: str, document_id: str
    ) -> Iterable[ExternalRoomEvent]:
        """List external room audit events for a document."""

    @abstractmethod
    async def get_latest_external_room_page_view_event(
        self, *, tenant_id: str, external_room_session_id: str, document_id: str
    ) -> Optional[ExternalRoomEvent]:
        """Return the latest page-view event for an external room document session."""

    @abstractmethod
    async def update_external_room_event_duration(
        self, *, tenant_id: str, event_id: str, duration_ms: int
    ) -> None:
        """Persist a computed duration for an existing external room event."""
