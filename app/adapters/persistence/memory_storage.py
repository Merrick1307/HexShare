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
    EventType,
    ExternalAccessGrant,
    ExternalParty,
    ExternalPartyEmail,
    ExternalRoomEvent,
    ExternalRoomSession,
    NdaAcceptance,
    NdaPolicy,
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
        self._external_parties: Dict[str, Dict[str, ExternalParty]] = defaultdict(dict)
        self._external_party_by_email: Dict[str, Dict[str, str]] = defaultdict(dict)
        self._external_party_emails: Dict[str, Dict[str, ExternalPartyEmail]] = defaultdict(dict)
        self._external_access_grants: Dict[str, Dict[str, ExternalAccessGrant]] = defaultdict(dict)
        self._external_room_sessions: Dict[str, Dict[str, ExternalRoomSession]] = defaultdict(dict)
        self._external_room_events: Dict[str, List[ExternalRoomEvent]] = defaultdict(list)
        # tenant_id -> {(scope_type, scope_id): NdaPolicy}
        self._nda_policies: Dict[str, Dict[tuple, NdaPolicy]] = defaultdict(dict)
        self._nda_acceptances: Dict[str, List[NdaAcceptance]] = defaultdict(list)
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

    async def list_visitor_sessions(
        self, *, tenant_id: str, document_id: str
    ) -> Iterable[VisitorSession]:
        link_ids = {
            link.id
            for link in self._share_links.get(tenant_id, {}).values()
            if link.document_id == document_id
        }
        return [
            session
            for session in self._visitor_sessions.get(tenant_id, {}).values()
            if session.share_link_id in link_ids
        ]

    async def save_view_event(self, event: ViewEvent) -> None:
        self._view_events[event.tenant_id].append(event)

    async def list_view_events(
        self, *, tenant_id: str, document_id: str
    ) -> Iterable[ViewEvent]:
        return [e for e in self._view_events.get(tenant_id, []) if e.document_id == document_id]

    async def get_latest_page_view_event(
        self, *, tenant_id: str, visitor_session_id: str
    ) -> Optional[ViewEvent]:
        page_events = [
            event
            for event in self._view_events.get(tenant_id, [])
            if event.visitor_session_id == visitor_session_id and event.event_type == EventType.PAGE_VIEW
        ]
        if not page_events:
            return None
        return max(page_events, key=lambda event: event.timestamp)

    async def update_view_event_duration(
        self, *, tenant_id: str, event_id: str, duration_ms: int
    ) -> None:
        for index, event in enumerate(self._view_events.get(tenant_id, [])):
            if event.id == event_id:
                self._view_events[tenant_id][index] = event.copy(update={"duration_ms": duration_ms})
                return


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

    async def save_external_party(self, party: ExternalParty) -> None:
        self._external_parties[party.tenant_id][party.id] = party

    async def get_external_party(
        self, *, tenant_id: str, external_party_id: str
    ) -> Optional[ExternalParty]:
        return self._external_parties.get(tenant_id, {}).get(external_party_id)

    async def get_external_party_by_email(
        self, *, tenant_id: str, email_normalized: str
    ) -> Optional[ExternalParty]:
        party_id = self._external_party_by_email.get(tenant_id, {}).get(email_normalized)
        if not party_id:
            return None
        return self._external_parties.get(tenant_id, {}).get(party_id)

    async def save_external_party_email(self, email: ExternalPartyEmail) -> None:
        self._external_party_emails[email.tenant_id][email.id] = email
        self._external_party_by_email[email.tenant_id][email.email_normalized] = email.external_party_id

    async def get_external_party_primary_email(
        self, *, tenant_id: str, external_party_id: str
    ) -> Optional[ExternalPartyEmail]:
        for record in self._external_party_emails.get(tenant_id, {}).values():
            if record.external_party_id == external_party_id and record.is_primary:
                return record
        return None

    async def mark_external_party_email_seen(
        self,
        *,
        tenant_id: str,
        email_normalized: str,
        seen_at: datetime,
        verified_at: Optional[datetime] = None,
    ) -> None:
        for email_id, record in self._external_party_emails.get(tenant_id, {}).items():
            if record.email_normalized != email_normalized:
                continue
            self._external_party_emails[tenant_id][email_id] = record.copy(
                update={
                    "last_seen_at": seen_at,
                    "verified_at": verified_at if verified_at is not None else record.verified_at,
                }
            )
            return

    async def save_external_access_grant(self, grant: ExternalAccessGrant) -> None:
        self._external_access_grants[grant.tenant_id][grant.id] = grant

    async def get_external_access_grant(
        self, *, tenant_id: str, grant_id: str
    ) -> Optional[ExternalAccessGrant]:
        return self._external_access_grants.get(tenant_id, {}).get(grant_id)

    async def revoke_external_access_grant(
        self, *, tenant_id: str, grant_id: str, revoked_at: datetime
    ) -> None:
        existing = self._external_access_grants.get(tenant_id, {}).get(grant_id)
        if existing:
            self._external_access_grants[tenant_id][grant_id] = existing.copy(
                update={"revoked_at": revoked_at, "updated_at": revoked_at}
            )

    async def list_external_access_grants(
        self,
        *,
        tenant_id: str,
        external_party_id: str | None = None,
        resource_type: str | None = None,
        resource_id: str | None = None,
    ) -> Iterable[ExternalAccessGrant]:
        grants = list(self._external_access_grants.get(tenant_id, {}).values())
        if external_party_id is not None:
            grants = [grant for grant in grants if grant.external_party_id == external_party_id]
        if resource_type is not None:
            grants = [grant for grant in grants if grant.resource_type.value == resource_type]
        if resource_id is not None:
            grants = [grant for grant in grants if grant.resource_id == resource_id]
        return grants

    async def save_external_room_session(self, session: ExternalRoomSession) -> None:
        self._external_room_sessions[session.tenant_id][session.id] = session

    async def get_external_room_session(
        self, *, tenant_id: str, session_id: str
    ) -> Optional[ExternalRoomSession]:
        return self._external_room_sessions.get(tenant_id, {}).get(session_id)

    async def end_external_room_session(
        self, *, tenant_id: str, session_id: str, ended_at: datetime
    ) -> None:
        session = self._external_room_sessions.get(tenant_id, {}).get(session_id)
        if session is not None:
            self._external_room_sessions[tenant_id][session_id] = session.copy(
                update={"ended_at": ended_at}
            )

    async def list_external_room_sessions(
        self, *, tenant_id: str
    ) -> Iterable[ExternalRoomSession]:
        return list(self._external_room_sessions.get(tenant_id, {}).values())

    async def save_external_room_event(self, event: ExternalRoomEvent) -> None:
        self._external_room_events[event.tenant_id].append(event)

    async def list_external_room_events(
        self, *, tenant_id: str, document_id: str
    ) -> Iterable[ExternalRoomEvent]:
        return [
            event
            for event in self._external_room_events.get(tenant_id, [])
            if event.document_id == document_id
        ]

    async def get_latest_external_room_page_view_event(
        self, *, tenant_id: str, external_room_session_id: str, document_id: str
    ) -> Optional[ExternalRoomEvent]:
        page_events = [
            event
            for event in self._external_room_events.get(tenant_id, [])
            if event.external_room_session_id == external_room_session_id
            and event.document_id == document_id
            and event.event_type == "document_page_view"
        ]
        if not page_events:
            return None
        return max(page_events, key=lambda event: event.timestamp)

    async def update_external_room_event_duration(
        self, *, tenant_id: str, event_id: str, duration_ms: int
    ) -> None:
        for index, event in enumerate(self._external_room_events.get(tenant_id, [])):
            if event.id == event_id:
                self._external_room_events[tenant_id][index] = event.copy(update={"duration_ms": duration_ms})
                return

    async def save_nda_policy(self, policy: NdaPolicy) -> None:
        key = (policy.scope_type.value, policy.scope_id)
        self._nda_policies[policy.tenant_id][key] = policy

    async def get_nda_policy(
        self, *, tenant_id: str, scope_type: str, scope_id: str, active_only: bool = True
    ) -> Optional[NdaPolicy]:
        policy = self._nda_policies.get(tenant_id, {}).get((scope_type, scope_id))
        if policy is None:
            return None
        if active_only and not policy.active:
            return None
        return policy

    async def deactivate_nda_policy(
        self, *, tenant_id: str, scope_type: str, scope_id: str
    ) -> None:
        key = (scope_type, scope_id)
        policy = self._nda_policies.get(tenant_id, {}).get(key)
        if policy is not None:
            self._nda_policies[tenant_id][key] = policy.copy(update={"active": False})

    async def save_nda_acceptance(self, acceptance: NdaAcceptance) -> None:
        self._nda_acceptances[acceptance.tenant_id].append(acceptance)

    async def get_nda_acceptance(
        self,
        *,
        tenant_id: str,
        scope_type: str,
        scope_id: str,
        nda_version: int,
        subject_kind: str,
        subject_id: str,
    ) -> Optional[NdaAcceptance]:
        for record in self._nda_acceptances.get(tenant_id, []):
            if (
                record.scope_type.value == scope_type
                and record.scope_id == scope_id
                and record.nda_version == nda_version
                and record.subject_kind.value == subject_kind
                and record.subject_id == subject_id
            ):
                return record
        return None

    async def list_nda_acceptances(
        self, *, tenant_id: str, scope_type: str, scope_id: str
    ) -> Iterable[NdaAcceptance]:
        return [
            record
            for record in self._nda_acceptances.get(tenant_id, [])
            if record.scope_type.value == scope_type and record.scope_id == scope_id
        ]

    async def list_nda_policies(
        self, *, tenant_id: str, active_only: bool = True
    ) -> Iterable[NdaPolicy]:
        policies = list(self._nda_policies.get(tenant_id, {}).values())
        if active_only:
            policies = [p for p in policies if p.active]
        return sorted(policies, key=lambda p: p.updated_at, reverse=True)

    async def get_workspace_summary(self, *, tenant_id: str) -> dict:
        now = datetime.utcnow()
        active_links = [
            link
            for link in self._share_links.get(tenant_id, {}).values()
            if link.revoked_at is None and link.expires_at > now
        ]
        external_parties = [
            party
            for party in self._external_parties.get(tenant_id, {}).values()
            if party.status.value == "active"
        ]
        opens = sum(
            1
            for e in self._view_events.get(tenant_id, [])
            if e.event_type == EventType.OPEN
        ) + sum(
            1
            for e in self._external_room_events.get(tenant_id, [])
            if e.event_type == "document_view_open"
        )
        return {
            "documents": len(self._documents.get(tenant_id, {})),
            "groups": len(self._doc_groups.get(tenant_id, {})),
            "active_links": len(active_links),
            "external_recipients": len(external_parties),
            "document_opens": opens,
        }

    async def list_recent_view_events(
        self, *, tenant_id: str, limit: int = 100
    ) -> Iterable[ViewEvent]:
        events = sorted(
            self._view_events.get(tenant_id, []), key=lambda e: e.timestamp, reverse=True
        )
        return events[:limit]

    async def list_recent_external_room_events(
        self, *, tenant_id: str, limit: int = 100
    ) -> Iterable[ExternalRoomEvent]:
        events = sorted(
            self._external_room_events.get(tenant_id, []), key=lambda e: e.timestamp, reverse=True
        )
        return events[:limit]


@StorageFactory.register("memory")
def create_memory_storage(**_) -> StoragePort:
    return MemoryStorage()
