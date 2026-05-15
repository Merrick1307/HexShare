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

from app.domain import (
    Document,
    DocumentGroup,
    DocumentPermission,
    ShareLink,
    VisitorSession,
    ViewEvent,
)
from app.infra.factories import StorageFactory
from app.ports.storage_port import StoragePort


class MemoryStorage(StoragePort):
    def __init__(self) -> None:
        # Use per‑tenant dictionaries for isolation
        self._documents: Dict[str, Dict[str, Document]] = defaultdict(dict)
        self._share_links: Dict[str, Dict[str, ShareLink]] = defaultdict(dict)
        self._visitor_sessions: Dict[str, Dict[str, VisitorSession]] = defaultdict(dict)
        self._view_events: Dict[str, List[ViewEvent]] = defaultdict(list)
        # (tenant_id, document_id, user_id) -> DocumentPermission
        self._doc_permissions: Dict[str, Dict[str, Dict[str, DocumentPermission]]] = defaultdict(
            lambda: defaultdict(dict)
        )
        # tenant_id -> {group_id: DocumentGroup}
        self._doc_groups: Dict[str, Dict[str, DocumentGroup]] = defaultdict(dict)
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
        return sorted(links, key=lambda item: item.created_at, reverse=True)

    async def revoke_share_link(
        self, *, tenant_id: str, link_id: str, revoked_at: Optional[datetime]
    ) -> None:
        link = self._share_links.get(tenant_id, {}).get(link_id)
        if link:
            link.revoked_at = revoked_at

    async def save_visitor_session(self, session: VisitorSession) -> None:
        self._visitor_sessions[session.tenant_id][session.id] = session

    async def get_visitor_session(self, *, tenant_id: str, session_id: str) -> Optional[VisitorSession]:
        return self._visitor_sessions.get(tenant_id, {}).get(session_id)

    async def get_visitor_session_by_id(self, *, session_id: str) -> Optional[VisitorSession]:
        for tenant_sessions in self._visitor_sessions.values():
            if session_id in tenant_sessions:
                return tenant_sessions[session_id]
        return None

    async def end_visitor_session(self, *, tenant_id: str, session_id: str, ended_at: datetime) -> None:
        session = self._visitor_sessions.get(tenant_id, {}).get(session_id)
        if session:
            session.ended_at = ended_at

    async def save_view_event(self, event: ViewEvent) -> None:
        self._view_events[event.tenant_id].append(event)

    async def list_view_events(
        self, *, tenant_id: str, document_id: str
    ) -> Iterable[ViewEvent]:
        return [e for e in self._view_events.get(tenant_id, []) if e.document_id == document_id]


    async def save_document_permission(self, permission: DocumentPermission) -> None:
        self._doc_permissions[permission.tenant_id][permission.document_id][
            permission.user_id
        ] = permission

    async def get_document_permission(
        self, *, tenant_id: str, document_id: str, user_id: str
    ) -> Optional[DocumentPermission]:
        return (
            self._doc_permissions.get(tenant_id, {})
            .get(document_id, {})
            .get(user_id)
        )

    async def revoke_document_permission(
        self, *, tenant_id: str, document_id: str, user_id: str
    ) -> None:
        doc_perms = self._doc_permissions.get(tenant_id, {}).get(document_id)
        if doc_perms and user_id in doc_perms:
            del doc_perms[user_id]

    async def list_document_permissions(
        self, *, tenant_id: str, document_id: str
    ) -> Iterable[DocumentPermission]:
        return list(self._doc_permissions.get(tenant_id, {}).get(document_id, {}).values())

    async def list_ungrouped_documents_by_permission(
        self, *, tenant_id: str, user_id: str, required_permission: int
    ) -> Iterable[Document]:
        result: List[Document] = []
        for doc in self._documents.get(tenant_id, {}).values():
            if doc.room_id is not None:
                continue
            perm = (
                self._doc_permissions.get(tenant_id, {})
                .get(doc.id, {})
                .get(user_id)
            )
            if perm and (perm.permissions & int(required_permission)):
                result.append(doc)
        return sorted(result, key=lambda d: d.created_at, reverse=True)

    async def list_documents_by_room(
        self, *, tenant_id: str, room_id: str
    ) -> Iterable[Document]:
        docs = [
            d for d in self._documents.get(tenant_id, {}).values() if d.room_id == room_id
        ]
        return sorted(docs, key=lambda d: d.created_at, reverse=True)

    async def delete_document(self, *, tenant_id: str, document_id: str) -> None:
        self._documents.get(tenant_id, {}).pop(document_id, None)

    async def save_document_group(self, group: DocumentGroup) -> None:
        self._doc_groups[group.tenant_id][group.id] = group

    async def get_document_group(
        self, *, tenant_id: str, group_id: str
    ) -> Optional[DocumentGroup]:
        return self._doc_groups.get(tenant_id, {}).get(group_id)

    async def list_document_groups_by_ids(
        self, *, tenant_id: str, group_ids: Iterable[str]
    ) -> Iterable[DocumentGroup]:
        wanted = set(group_ids)
        groups = [
            g for gid, g in self._doc_groups.get(tenant_id, {}).items() if gid in wanted
        ]
        return sorted(groups, key=lambda g: g.created_at, reverse=True)

    async def update_document_group(
        self,
        *,
        tenant_id: str,
        group_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
    ) -> Optional[DocumentGroup]:
        existing = self._doc_groups.get(tenant_id, {}).get(group_id)
        if not existing:
            return None
        updated = existing.copy(
            update={
                "name": name if name is not None else existing.name,
                "description": description if description is not None else existing.description,
            }
        )
        self._doc_groups[tenant_id][group_id] = updated
        return updated

    async def delete_document_group(self, *, tenant_id: str, group_id: str) -> None:
        self._doc_groups.get(tenant_id, {}).pop(group_id, None)
        # Mirror the FK ON DELETE SET NULL behaviour from Postgres.
        for doc in self._documents.get(tenant_id, {}).values():
            if doc.room_id == group_id:
                # Pydantic v1 models are mutable by default; reassign via copy.
                self._documents[tenant_id][doc.id] = doc.copy(update={"room_id": None})

    async def update_document_room(
        self, *, tenant_id: str, document_id: str, room_id: Optional[str]
    ) -> Optional[Document]:
        docs = self._documents.get(tenant_id, {})
        doc = docs.get(document_id)
        if not doc:
            return None
        updated = doc.copy(update={"room_id": room_id})
        docs[document_id] = updated
        return updated


@StorageFactory.register("memory")
def create_memory_storage(**_) -> StoragePort:
    return MemoryStorage()
