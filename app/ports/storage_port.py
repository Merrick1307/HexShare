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

from app.domain import Document, ShareLink, VisitorSession, ViewEvent


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
    async def save_view_event(self, event: ViewEvent) -> None:
        """Persist a view event."""

    @abstractmethod
    async def list_view_events(
        self, *, tenant_id: str, document_id: str
    ) -> Iterable[ViewEvent]:
        """List view events for a specific document."""
