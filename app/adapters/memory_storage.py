"""
In‑memory storage adapter.

This adapter implements the :class:`~app.ports.StoragePort` using
Python data structures.  It is intended for development, testing and
examples.  The adapter is **not** thread‑safe and does not persist
across process restarts.  In a real deployment, replace this with a
database‑backed implementation.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Dict, Iterable, List, Optional

from app.domain import Document, ShareLink, VisitorSession, ViewEvent
from app.infra.factories import StorageFactory
from app.ports.storage_port import StoragePort


class MemoryStorage(StoragePort):
    def __init__(self) -> None:
        # Use per‑tenant dictionaries for isolation
        self._documents: Dict[str, Dict[str, Document]] = defaultdict(dict)
        self._share_links: Dict[str, Dict[str, ShareLink]] = defaultdict(dict)
        self._visitor_sessions: Dict[str, Dict[str, VisitorSession]] = defaultdict(dict)
        self._view_events: Dict[str, List[ViewEvent]] = defaultdict(list)
        self._id_counter = 0

    def generate_id(self, prefix: str) -> str:
        self._id_counter += 1
        return f"{prefix}_{self._id_counter}"

    async def save_document(self, document: Document) -> None:
        self._documents[document.tenant_id][document.id] = document

    async def get_document(self, *, tenant_id: str, document_id: str) -> Optional[Document]:
        return self._documents.get(tenant_id, {}).get(document_id)

    async def list_documents(self, *, tenant_id: str) -> Iterable[Document]:
        return list(self._documents.get(tenant_id, {}).values())

    async def save_share_link(self, link: ShareLink) -> None:
        self._share_links[link.tenant_id][link.id] = link

    async def get_share_link(self, *, tenant_id: str, link_id: str) -> Optional[ShareLink]:
        return self._share_links.get(tenant_id, {}).get(link_id)

    async def list_share_links(
        self, *, tenant_id: str, document_id: Optional[str] = None
    ) -> Iterable[ShareLink]:
        links = list(self._share_links.get(tenant_id, {}).values())
        if document_id:
            links = [l for l in links if l.document_id == document_id]
        return links

    async def revoke_share_link(
        self, *, tenant_id: str, link_id: str, revoked_at: Optional[datetime]
    ) -> None:
        link = self._share_links.get(tenant_id, {}).get(link_id)
        if link:
            # update link (replace with new instance to avoid side effects)
            link.revoked_at = revoked_at

    async def save_visitor_session(self, session: VisitorSession) -> None:
        self._visitor_sessions[session.tenant_id][session.id] = session

    async def save_view_event(self, event: ViewEvent) -> None:
        self._view_events[event.tenant_id].append(event)

    async def list_view_events(
        self, *, tenant_id: str, document_id: str
    ) -> Iterable[ViewEvent]:
        return [e for e in self._view_events.get(tenant_id, []) if e.document_id == document_id]


@StorageFactory.register("memory")
def create_memory_storage(**_) -> StoragePort:
    return MemoryStorage()