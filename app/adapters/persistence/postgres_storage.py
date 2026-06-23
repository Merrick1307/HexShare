"""
PostgreSQL storage adapter using asyncpg.

This adapter implements :class:`~app.ports.StoragePort` using the
asyncpg library and raw SQL.  It requires a connection pool and
manages tenant isolation at the application layer.  PostgreSQL Row
Level Security (RLS) could be added in future revisions to further
constrain access.
"""
from __future__ import annotations

import asyncpg  # type: ignore
from datetime import datetime
from typing import Iterable, Optional

from app.domain import (
    Document,
    DocumentGroup,
    DocumentPermission,
    EventType,
    ExternalAccessGrant,
    ExternalParty,
    ExternalPartyEmail,
    ExternalRoomEvent,
    ExternalRoomEventType,
    ExternalRoomSession,
    ShareLink,
    VisitorSession,
    ViewEvent,
)
from app.infra.factories import StorageFactory
from app.ports.storage_port import StoragePort


class PostgresStorage(StoragePort):
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    def generate_id(self, prefix: str) -> str:
        import uuid
        return f"{prefix}_{uuid.uuid4().hex}"

    @staticmethod
    def _row_to_document(row) -> Document:
        return Document(
            id=row["id"],
            tenant_id=row["tenant_id"],
            name=row["name"],
            mime_type=row["mime_type"],
            size=row["size"],
            storage_key=row["storage_key"],
            created_at=row["created_at"],
            created_by=row["created_by"],
            room_id=row["room_id"] if "room_id" in row.keys() else None,
        )

    @staticmethod
    def _row_to_external_party(row) -> Optional[ExternalParty]:
        if not row:
            return None
        return ExternalParty(
            id=row["id"],
            tenant_id=row["tenant_id"],
            display_name=row["display_name"],
            status=row["status"],
            created_by=row["created_by"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            archived_at=row["archived_at"],
        )

    @staticmethod
    def _row_to_external_access_grant(row) -> Optional[ExternalAccessGrant]:
        if not row:
            return None
        return ExternalAccessGrant(
            id=row["id"],
            tenant_id=row["tenant_id"],
            external_party_id=row["external_party_id"],
            resource_type=row["resource_type"],
            resource_id=row["resource_id"],
            grant_type=row["grant_type"],
            permissions=int(row["permissions"] or 0),
            can_download=row["can_download"],
            can_print=row["can_print"],
            expires_at=row["expires_at"],
            revoked_at=row["revoked_at"],
            granted_by=row["granted_by"],
            granted_at=row["granted_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _row_to_external_room_session(row) -> Optional[ExternalRoomSession]:
        if not row:
            return None
        return ExternalRoomSession(
            id=row["id"],
            tenant_id=row["tenant_id"],
            external_party_id=row["external_party_id"],
            external_access_grant_id=row["external_access_grant_id"],
            room_id=row["room_id"],
            permissions=int(row["permissions"] or 0),
            presented_email=row["presented_email"],
            started_at=row["started_at"],
            ended_at=row["ended_at"],
            ip_hash=row["ip_hash"],
            ua_hash=row["ua_hash"],
        )

    async def save_document(self, document: Document) -> None:
        sql = """
        INSERT INTO documents (id, tenant_id, name, mime_type, size, storage_key, created_at, created_by, room_id)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
        """
        async with self._pool.acquire() as con:
            await con.execute(
                sql,
                document.id,
                document.tenant_id,
                document.name,
                document.mime_type,
                document.size,
                document.storage_key,
                document.created_at,
                document.created_by,
                document.room_id,
            )

    async def get_document(self, *, tenant_id: str, document_id: str) -> Optional[Document]:
        sql = """
        SELECT id, tenant_id, name, mime_type, size, storage_key, created_at, created_by, room_id
        FROM documents
        WHERE tenant_id = $1 AND id = $2
        """
        async with self._pool.acquire() as con:
            row = await con.fetchrow(sql, tenant_id, document_id)
            if row:
                return self._row_to_document(row)
            return None

    async def list_documents(self, *, tenant_id: str) -> Iterable[Document]:
        sql = """
        SELECT id, tenant_id, name, mime_type, size, storage_key, created_at, created_by, room_id
        FROM documents
        WHERE tenant_id = $1
        ORDER BY created_at DESC
        """
        async with self._pool.acquire() as con:
            rows = await con.fetch(sql, tenant_id)
        return [self._row_to_document(row) for row in rows]

    async def save_share_link(self, link: ShareLink) -> None:
        sql = """
        INSERT INTO share_links (
            id, tenant_id, document_id, jti, expires_at,
            can_download, can_print, require_email, allowed_emails,
            external_access_grant_id, access_mode, bound_email_normalized,
            revoked_at, created_at, created_by
        ) VALUES (
            $1, $2, $3, $4, $5,
            $6, $7, $8, $9,
            $10, $11, $12,
            $13, $14, $15
        )
        """
        async with self._pool.acquire() as con:
            await con.execute(
                sql,
                link.id,
                link.tenant_id,
                link.document_id,
                link.jti,
                link.expires_at,
                link.can_download,
                link.can_print,
                link.require_email,
                link.allowed_emails,
                link.external_access_grant_id,
                link.access_mode.value,
                link.bound_email_normalized,
                link.revoked_at,
                link.created_at,
                link.created_by,
            )

    async def get_share_link(self, *, tenant_id: str, link_id: str) -> Optional[ShareLink]:
        sql = """
        SELECT * FROM share_links
        WHERE tenant_id = $1 AND id = $2
        """
        async with self._pool.acquire() as con:
            row = await con.fetchrow(sql, tenant_id, link_id)
            if not row:
                return None
            return ShareLink(
                id=row["id"],
                tenant_id=row["tenant_id"],
                document_id=row["document_id"],
                jti=row["jti"],
                expires_at=row["expires_at"],
                can_download=row["can_download"],
                can_print=row["can_print"],
                require_email=row["require_email"],
                allowed_emails=row["allowed_emails"] or [],
                external_access_grant_id=row["external_access_grant_id"],
                access_mode=row["access_mode"],
                bound_email_normalized=row["bound_email_normalized"],
                revoked_at=row["revoked_at"],
                created_at=row["created_at"],
                created_by=row["created_by"],
            )

    async def list_share_links(
        self, *, tenant_id: str, document_id: Optional[str] = None
    ) -> Iterable[ShareLink]:
        sql = """
        SELECT * FROM share_links
        WHERE tenant_id = $1
        """
        params = [tenant_id]
        if document_id:
            sql += " AND document_id = $2"
            params.append(document_id)
        sql += " ORDER BY created_at DESC"
        async with self._pool.acquire() as con:
            rows = await con.fetch(sql, *params)
        return [
            ShareLink(
                id=row["id"],
                tenant_id=row["tenant_id"],
                document_id=row["document_id"],
                jti=row["jti"],
                expires_at=row["expires_at"],
                can_download=row["can_download"],
                can_print=row["can_print"],
                require_email=row["require_email"],
                allowed_emails=row["allowed_emails"] or [],
                external_access_grant_id=row["external_access_grant_id"],
                access_mode=row["access_mode"],
                bound_email_normalized=row["bound_email_normalized"],
                revoked_at=row["revoked_at"],
                created_at=row["created_at"],
                created_by=row["created_by"],
            )
            for row in rows
        ]

    async def revoke_share_link(
        self, *, tenant_id: str, link_id: str, revoked_at: Optional[datetime]
    ) -> None:
        sql = """
        UPDATE share_links
        SET revoked_at = $3
        WHERE tenant_id = $1 AND id = $2
        """
        async with self._pool.acquire() as con:
            await con.execute(sql, tenant_id, link_id, revoked_at)

    async def save_visitor_session(self, session: VisitorSession) -> None:
        sql = """
        INSERT INTO visitor_sessions (
            id, tenant_id, share_link_id, visitor_id,
            external_party_id, external_access_grant_id, presented_email, identity_source,
            ip_hash, ua_hash, started_at, ended_at
        ) VALUES (
            $1, $2, $3, $4,
            $5, $6, $7, $8,
            $9, $10, $11, $12
        )
        """
        async with self._pool.acquire() as con:
            await con.execute(
                sql,
                session.id,
                session.tenant_id,
                session.share_link_id,
                session.visitor_id,
                session.external_party_id,
                session.external_access_grant_id,
                session.presented_email,
                session.identity_source,
                session.ip_hash,
                session.ua_hash,
                session.started_at,
                session.ended_at,
            )

    async def get_visitor_session(self, *, tenant_id: str, session_id: str) -> Optional[VisitorSession]:
        sql = """
        SELECT id, tenant_id, share_link_id, visitor_id, external_party_id,
               external_access_grant_id, presented_email, identity_source,
               ip_hash, ua_hash, started_at, ended_at
        FROM visitor_sessions
        WHERE tenant_id = $1 AND id = $2
        """
        async with self._pool.acquire() as con:
            row = await con.fetchrow(sql, tenant_id, session_id)
        return self._row_to_visitor_session(row)

    async def get_visitor_session_by_id(self, *, session_id: str) -> Optional[VisitorSession]:
        sql = """
        SELECT id, tenant_id, share_link_id, visitor_id, external_party_id,
               external_access_grant_id, presented_email, identity_source,
               ip_hash, ua_hash, started_at, ended_at
        FROM visitor_sessions
        WHERE id = $1
        """
        async with self._pool.acquire() as con:
            row = await con.fetchrow(sql, session_id)
        return self._row_to_visitor_session(row)

    def _row_to_visitor_session(self, row) -> Optional[VisitorSession]:
        if not row:
            return None
        return VisitorSession(
            id=row["id"],
            tenant_id=row["tenant_id"],
            share_link_id=row["share_link_id"],
            visitor_id=row["visitor_id"],
            external_party_id=row["external_party_id"],
            external_access_grant_id=row["external_access_grant_id"],
            presented_email=row["presented_email"],
            identity_source=row["identity_source"],
            ip_hash=row["ip_hash"],
            ua_hash=row["ua_hash"],
            started_at=row["started_at"],
            ended_at=row["ended_at"],
        )

    async def end_visitor_session(self, *, tenant_id: str, session_id: str, ended_at: datetime) -> None:
        sql = """
        UPDATE visitor_sessions
        SET ended_at = $3
        WHERE tenant_id = $1 AND id = $2
        """
        async with self._pool.acquire() as con:
            await con.execute(sql, tenant_id, session_id, ended_at)

    async def list_visitor_sessions(
        self, *, tenant_id: str, document_id: str
    ) -> Iterable[VisitorSession]:
        sql = """
        SELECT vs.id, vs.tenant_id, vs.share_link_id, vs.visitor_id, vs.external_party_id,
               vs.external_access_grant_id, vs.presented_email, vs.identity_source,
               vs.ip_hash, vs.ua_hash, vs.started_at, vs.ended_at
        FROM visitor_sessions vs
        JOIN share_links sl ON sl.id = vs.share_link_id
        WHERE vs.tenant_id = $1 AND sl.document_id = $2
        ORDER BY vs.started_at ASC
        """
        async with self._pool.acquire() as con:
            rows = await con.fetch(sql, tenant_id, document_id)
        return [self._row_to_visitor_session(row) for row in rows if row]

    async def save_view_event(self, event: ViewEvent) -> None:
        sql = """
        INSERT INTO view_events (
            id, tenant_id, document_id, share_link_id,
            visitor_session_id, event_type, page_number, duration_ms, timestamp
        ) VALUES (
            $1, $2, $3, $4,
            $5, $6, $7, $8, $9
        )
        """
        async with self._pool.acquire() as con:
            await con.execute(
                sql,
                event.id,
                event.tenant_id,
                event.document_id,
                event.share_link_id,
                event.visitor_session_id,
                event.event_type.value,
                event.page_number,
                event.duration_ms,
                event.timestamp,
            )

    async def list_view_events(
        self, *, tenant_id: str, document_id: str
    ) -> Iterable[ViewEvent]:
        sql = """
        SELECT * FROM view_events
        WHERE tenant_id = $1 AND document_id = $2
        ORDER BY timestamp ASC
        """
        async with self._pool.acquire() as con:
            rows = await con.fetch(sql, tenant_id, document_id)
        return [
            ViewEvent(
                id=row["id"],
                tenant_id=row["tenant_id"],
                document_id=row["document_id"],
                share_link_id=row["share_link_id"],
                visitor_session_id=row["visitor_session_id"],
                event_type=row["event_type"],
                page_number=row["page_number"],
                duration_ms=row["duration_ms"],
                timestamp=row["timestamp"],
            )
            for row in rows
        ]

    async def get_latest_page_view_event(
        self, *, tenant_id: str, visitor_session_id: str
    ) -> Optional[ViewEvent]:
        sql = """
        SELECT *
        FROM view_events
        WHERE tenant_id = $1
          AND visitor_session_id = $2
          AND event_type = $3
        ORDER BY timestamp DESC
        LIMIT 1
        """
        async with self._pool.acquire() as con:
            row = await con.fetchrow(sql, tenant_id, visitor_session_id, EventType.PAGE_VIEW.value)
        if not row:
            return None
        return ViewEvent(
            id=row["id"],
            tenant_id=row["tenant_id"],
            document_id=row["document_id"],
            share_link_id=row["share_link_id"],
            visitor_session_id=row["visitor_session_id"],
            event_type=row["event_type"],
            page_number=row["page_number"],
            duration_ms=row["duration_ms"],
            timestamp=row["timestamp"],
        )

    async def update_view_event_duration(
        self, *, tenant_id: str, event_id: str, duration_ms: int
    ) -> None:
        sql = """
        UPDATE view_events
        SET duration_ms = $3
        WHERE tenant_id = $1 AND id = $2
        """
        async with self._pool.acquire() as con:
            await con.execute(sql, tenant_id, event_id, duration_ms)


    @staticmethod
    def _row_to_permission(row) -> DocumentPermission:
        return DocumentPermission(
            document_id=row["document_id"],
            tenant_id=row["tenant_id"],
            user_id=row["user_id"],
            permissions=int(row["permissions"]),
            granted_by=row["granted_by"],
            granted_at=row["granted_at"],
        )

    async def save_document_permission(self, permission: DocumentPermission) -> None:
        sql = """
        INSERT INTO document_permissions (
            document_id, tenant_id, user_id, permissions, granted_by, granted_at
        ) VALUES ($1, $2, $3, $4, $5, $6)
        ON CONFLICT (document_id, user_id) DO UPDATE
            SET permissions = EXCLUDED.permissions,
                granted_by = EXCLUDED.granted_by,
                granted_at = EXCLUDED.granted_at
        """
        async with self._pool.acquire() as con:
            await con.execute(
                sql,
                permission.document_id,
                permission.tenant_id,
                permission.user_id,
                permission.permissions,
                permission.granted_by,
                permission.granted_at,
            )

    async def get_document_permission(
        self, *, tenant_id: str, document_id: str, user_id: str
    ) -> Optional[DocumentPermission]:
        sql = """
        SELECT document_id, tenant_id, user_id, permissions, granted_by, granted_at
        FROM document_permissions
        WHERE tenant_id = $1 AND document_id = $2 AND user_id = $3
        """
        async with self._pool.acquire() as con:
            row = await con.fetchrow(sql, tenant_id, document_id, user_id)
        return self._row_to_permission(row) if row else None

    async def revoke_document_permission(
        self, *, tenant_id: str, document_id: str, user_id: str
    ) -> None:
        sql = """
        DELETE FROM document_permissions
        WHERE tenant_id = $1 AND document_id = $2 AND user_id = $3
        """
        async with self._pool.acquire() as con:
            await con.execute(sql, tenant_id, document_id, user_id)

    async def delete_document(self, *, tenant_id: str, document_id: str) -> None:
        sql = "DELETE FROM documents WHERE tenant_id = $1 AND id = $2"
        async with self._pool.acquire() as con:
            await con.execute(sql, tenant_id, document_id)

    async def list_document_permissions(
        self, *, tenant_id: str, document_id: str
    ) -> Iterable[DocumentPermission]:
        sql = """
        SELECT document_id, tenant_id, user_id, permissions, granted_by, granted_at
        FROM document_permissions
        WHERE tenant_id = $1 AND document_id = $2
        """
        async with self._pool.acquire() as con:
            rows = await con.fetch(sql, tenant_id, document_id)
        return [self._row_to_permission(r) for r in rows]

    async def list_ungrouped_documents_by_permission(
        self, *, tenant_id: str, user_id: str, required_permission: int
    ) -> Iterable[Document]:
        sql = """
        SELECT d.id, d.tenant_id, d.name, d.mime_type, d.size, d.storage_key,
               d.created_at, d.created_by, d.room_id
        FROM documents d
        JOIN document_permissions p
          ON p.document_id = d.id AND p.tenant_id = d.tenant_id AND p.user_id = $2
        WHERE d.tenant_id = $1
          AND d.room_id IS NULL
          AND (p.permissions & $3) <> 0
        ORDER BY d.created_at DESC
        """
        async with self._pool.acquire() as con:
            rows = await con.fetch(sql, tenant_id, user_id, int(required_permission))
        return [self._row_to_document(row) for row in rows]

    async def list_documents_by_room(
        self, *, tenant_id: str, room_id: str
    ) -> Iterable[Document]:
        sql = """
        SELECT id, tenant_id, name, mime_type, size, storage_key, created_at, created_by, room_id
        FROM documents
        WHERE tenant_id = $1 AND room_id = $2
        ORDER BY created_at DESC
        """
        async with self._pool.acquire() as con:
            rows = await con.fetch(sql, tenant_id, room_id)
        return [self._row_to_document(row) for row in rows]


    @staticmethod
    def _row_to_group(row) -> DocumentGroup:
        return DocumentGroup(
            id=row["id"],
            tenant_id=row["tenant_id"],
            name=row["name"],
            description=row["description"],
            created_by=row["created_by"],
            created_at=row["created_at"],
        )

    async def save_document_group(self, group: DocumentGroup) -> None:
        sql = """
        INSERT INTO document_groups (id, tenant_id, name, description, created_by, created_at)
        VALUES ($1, $2, $3, $4, $5, $6)
        """
        async with self._pool.acquire() as con:
            await con.execute(
                sql,
                group.id,
                group.tenant_id,
                group.name,
                group.description,
                group.created_by,
                group.created_at,
            )

    async def get_document_group(
        self, *, tenant_id: str, group_id: str
    ) -> Optional[DocumentGroup]:
        sql = """
        SELECT id, tenant_id, name, description, created_by, created_at
        FROM document_groups
        WHERE tenant_id = $1 AND id = $2
        """
        async with self._pool.acquire() as con:
            row = await con.fetchrow(sql, tenant_id, group_id)
        return self._row_to_group(row) if row else None

    async def list_document_groups_by_ids(
        self, *, tenant_id: str, group_ids: Iterable[str]
    ) -> Iterable[DocumentGroup]:
        ids = list(group_ids)
        if not ids:
            return []
        sql = """
        SELECT id, tenant_id, name, description, created_by, created_at
        FROM document_groups
        WHERE tenant_id = $1 AND id = ANY($2::text[])
        ORDER BY created_at DESC
        """
        async with self._pool.acquire() as con:
            rows = await con.fetch(sql, tenant_id, ids)
        return [self._row_to_group(row) for row in rows]

    async def update_document_group(
        self,
        *,
        tenant_id: str,
        group_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
    ) -> Optional[DocumentGroup]:
        sql = """
        UPDATE document_groups
        SET name = COALESCE($3, name),
            description = COALESCE($4, description)
        WHERE tenant_id = $1 AND id = $2
        RETURNING id, tenant_id, name, description, created_by, created_at
        """
        async with self._pool.acquire() as con:
            row = await con.fetchrow(sql, tenant_id, group_id, name, description)
        return self._row_to_group(row) if row else None

    async def delete_document_group(self, *, tenant_id: str, group_id: str) -> None:
        sql = "DELETE FROM document_groups WHERE tenant_id = $1 AND id = $2"
        async with self._pool.acquire() as con:
            await con.execute(sql, tenant_id, group_id)

    async def update_document_room(
        self, *, tenant_id: str, document_id: str, room_id: Optional[str]
    ) -> Optional[Document]:
        sql = """
            UPDATE documents
            SET room_id = $3
            WHERE tenant_id = $1 AND id = $2
            RETURNING *
        """
        async with self._pool.acquire() as con:
            row = await con.fetchrow(sql, tenant_id, document_id, room_id)
        return self._row_to_document(row) if row else None

    async def save_external_party(self, party: ExternalParty) -> None:
        sql = """
        INSERT INTO external_parties (
            id, tenant_id, display_name, status, created_by, created_at, updated_at, archived_at
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        ON CONFLICT (id) DO UPDATE
            SET display_name = EXCLUDED.display_name,
                status = EXCLUDED.status,
                updated_at = EXCLUDED.updated_at,
                archived_at = EXCLUDED.archived_at
        """
        async with self._pool.acquire() as con:
            await con.execute(
                sql,
                party.id,
                party.tenant_id,
                party.display_name,
                party.status.value,
                party.created_by,
                party.created_at,
                party.updated_at,
                party.archived_at,
            )

    async def get_external_party(
        self, *, tenant_id: str, external_party_id: str
    ) -> Optional[ExternalParty]:
        sql = """
        SELECT id, tenant_id, display_name, status, created_by, created_at, updated_at, archived_at
        FROM external_parties
        WHERE tenant_id = $1 AND id = $2
        """
        async with self._pool.acquire() as con:
            row = await con.fetchrow(sql, tenant_id, external_party_id)
        return self._row_to_external_party(row)

    async def get_external_party_by_email(
        self, *, tenant_id: str, email_normalized: str
    ) -> Optional[ExternalParty]:
        sql = """
        SELECT ep.id, ep.tenant_id, ep.display_name, ep.status, ep.created_by,
               ep.created_at, ep.updated_at, ep.archived_at
        FROM external_parties ep
        INNER JOIN external_party_emails epe
            ON epe.external_party_id = ep.id
           AND epe.tenant_id = ep.tenant_id
        WHERE ep.tenant_id = $1 AND epe.email_normalized = $2
        LIMIT 1
        """
        async with self._pool.acquire() as con:
            row = await con.fetchrow(sql, tenant_id, email_normalized)
        return self._row_to_external_party(row)

    async def save_external_party_email(self, email: ExternalPartyEmail) -> None:
        sql = """
        INSERT INTO external_party_emails (
            id, tenant_id, external_party_id, email_normalized, email_original,
            is_primary, verified_at, last_seen_at, created_at
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
        ON CONFLICT (tenant_id, email_normalized) DO UPDATE
            SET external_party_id = EXCLUDED.external_party_id,
                email_original = EXCLUDED.email_original,
                is_primary = EXCLUDED.is_primary,
                verified_at = COALESCE(EXCLUDED.verified_at, external_party_emails.verified_at),
                last_seen_at = COALESCE(EXCLUDED.last_seen_at, external_party_emails.last_seen_at)
        """
        async with self._pool.acquire() as con:
            await con.execute(
                sql,
                email.id,
                email.tenant_id,
                email.external_party_id,
                email.email_normalized,
                email.email_original,
                email.is_primary,
                email.verified_at,
                email.last_seen_at,
                email.created_at,
            )

    async def get_external_party_primary_email(
        self, *, tenant_id: str, external_party_id: str
    ) -> Optional[ExternalPartyEmail]:
        sql = """
        SELECT id, tenant_id, external_party_id, email_normalized, email_original,
               is_primary, verified_at, last_seen_at, created_at
        FROM external_party_emails
        WHERE tenant_id = $1 AND external_party_id = $2
        ORDER BY is_primary DESC, created_at ASC
        LIMIT 1
        """
        async with self._pool.acquire() as con:
            row = await con.fetchrow(sql, tenant_id, external_party_id)
        if not row:
            return None
        return ExternalPartyEmail(
            id=row["id"],
            tenant_id=row["tenant_id"],
            external_party_id=row["external_party_id"],
            email_normalized=row["email_normalized"],
            email_original=row["email_original"],
            is_primary=row["is_primary"],
            verified_at=row["verified_at"],
            last_seen_at=row["last_seen_at"],
            created_at=row["created_at"],
        )

    async def mark_external_party_email_seen(
        self,
        *,
        tenant_id: str,
        email_normalized: str,
        seen_at: datetime,
        verified_at: Optional[datetime] = None,
    ) -> None:
        sql = """
        UPDATE external_party_emails
        SET last_seen_at = $3,
            verified_at = COALESCE($4, verified_at)
        WHERE tenant_id = $1 AND email_normalized = $2
        """
        async with self._pool.acquire() as con:
            await con.execute(sql, tenant_id, email_normalized, seen_at, verified_at)

    async def save_external_access_grant(self, grant: ExternalAccessGrant) -> None:
        sql = """
        INSERT INTO external_access_grants (
            id, tenant_id, external_party_id, resource_type, resource_id, grant_type, permissions,
            can_download, can_print, expires_at, revoked_at, granted_by, granted_at, updated_at
        ) VALUES (
            $1, $2, $3, $4, $5, $6,
            $7, $8, $9, $10, $11, $12, $13, $14
        )
        ON CONFLICT (id) DO UPDATE
            SET permissions = EXCLUDED.permissions,
                can_download = EXCLUDED.can_download,
                can_print = EXCLUDED.can_print,
                expires_at = EXCLUDED.expires_at,
                revoked_at = EXCLUDED.revoked_at,
                updated_at = EXCLUDED.updated_at
        """
        async with self._pool.acquire() as con:
            await con.execute(
                sql,
                grant.id,
                grant.tenant_id,
                grant.external_party_id,
                grant.resource_type.value,
                grant.resource_id,
                grant.grant_type.value,
                grant.permissions,
                grant.can_download,
                grant.can_print,
                grant.expires_at,
                grant.revoked_at,
                grant.granted_by,
                grant.granted_at,
                grant.updated_at,
            )

    async def get_external_access_grant(
        self, *, tenant_id: str, grant_id: str
    ) -> Optional[ExternalAccessGrant]:
        sql = """
        SELECT id, tenant_id, external_party_id, resource_type, resource_id, grant_type,
               permissions, can_download, can_print, expires_at, revoked_at, granted_by, granted_at, updated_at
        FROM external_access_grants
        WHERE tenant_id = $1 AND id = $2
        """
        async with self._pool.acquire() as con:
            row = await con.fetchrow(sql, tenant_id, grant_id)
        return self._row_to_external_access_grant(row)

    async def revoke_external_access_grant(
        self, *, tenant_id: str, grant_id: str, revoked_at: datetime
    ) -> None:
        sql = """
        UPDATE external_access_grants
        SET revoked_at = $3,
            updated_at = $3
        WHERE tenant_id = $1 AND id = $2
        """
        async with self._pool.acquire() as con:
            await con.execute(sql, tenant_id, grant_id, revoked_at)

    async def list_external_access_grants(
        self,
        *,
        tenant_id: str,
        external_party_id: str | None = None,
        resource_type: str | None = None,
        resource_id: str | None = None,
    ) -> Iterable[ExternalAccessGrant]:
        sql = """
        SELECT id, tenant_id, external_party_id, resource_type, resource_id, grant_type,
               permissions, can_download, can_print, expires_at, revoked_at, granted_by, granted_at, updated_at
        FROM external_access_grants
        WHERE tenant_id = $1
        """
        params: list[object] = [tenant_id]
        if external_party_id is not None:
            sql += f" AND external_party_id = ${len(params) + 1}"
            params.append(external_party_id)
        if resource_type is not None:
            sql += f" AND resource_type = ${len(params) + 1}"
            params.append(resource_type)
        if resource_id is not None:
            sql += f" AND resource_id = ${len(params) + 1}"
            params.append(resource_id)
        sql += " ORDER BY granted_at DESC"
        async with self._pool.acquire() as con:
            rows = await con.fetch(sql, *params)
        return [self._row_to_external_access_grant(row) for row in rows if row]

    async def save_external_room_session(self, session: ExternalRoomSession) -> None:
        sql = """
        INSERT INTO external_room_sessions (
            id, tenant_id, external_party_id, external_access_grant_id, room_id, permissions,
            presented_email, started_at, ended_at, ip_hash, ua_hash
        ) VALUES (
            $1, $2, $3, $4, $5, $6,
            $7, $8, $9, $10, $11
        )
        ON CONFLICT (id) DO UPDATE
            SET permissions = EXCLUDED.permissions,
                ended_at = EXCLUDED.ended_at
        """
        async with self._pool.acquire() as con:
            await con.execute(
                sql,
                session.id,
                session.tenant_id,
                session.external_party_id,
                session.external_access_grant_id,
                session.room_id,
                session.permissions,
                session.presented_email,
                session.started_at,
                session.ended_at,
                session.ip_hash,
                session.ua_hash,
            )

    async def get_external_room_session(
        self, *, tenant_id: str, session_id: str
    ) -> Optional[ExternalRoomSession]:
        sql = """
        SELECT id, tenant_id, external_party_id, external_access_grant_id, room_id, permissions,
               presented_email, started_at, ended_at, ip_hash, ua_hash
        FROM external_room_sessions
        WHERE tenant_id = $1 AND id = $2
        """
        async with self._pool.acquire() as con:
            row = await con.fetchrow(sql, tenant_id, session_id)
        return self._row_to_external_room_session(row)

    async def end_external_room_session(
        self, *, tenant_id: str, session_id: str, ended_at: datetime
    ) -> None:
        sql = """
        UPDATE external_room_sessions
        SET ended_at = $3
        WHERE tenant_id = $1 AND id = $2
        """
        async with self._pool.acquire() as con:
            await con.execute(sql, tenant_id, session_id, ended_at)

    async def list_external_room_sessions(
        self, *, tenant_id: str
    ) -> Iterable[ExternalRoomSession]:
        sql = """
        SELECT id, tenant_id, external_party_id, external_access_grant_id, room_id, permissions,
               presented_email, started_at, ended_at, ip_hash, ua_hash
        FROM external_room_sessions
        WHERE tenant_id = $1
        ORDER BY started_at ASC
        """
        async with self._pool.acquire() as con:
            rows = await con.fetch(sql, tenant_id)
        return [self._row_to_external_room_session(row) for row in rows if row]

    async def save_external_room_event(self, event: ExternalRoomEvent) -> None:
        sql = """
        INSERT INTO external_room_events (
            id, tenant_id, external_room_session_id, room_id, event_type, document_id, page_number, duration_ms, timestamp
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
        """
        async with self._pool.acquire() as con:
            await con.execute(
                sql,
                event.id,
                event.tenant_id,
                event.external_room_session_id,
                event.room_id,
                event.event_type.value if isinstance(event.event_type, ExternalRoomEventType) else event.event_type,
                event.document_id,
                event.page_number,
                event.duration_ms,
                event.timestamp,
            )

    async def list_external_room_events(
        self, *, tenant_id: str, document_id: str
    ) -> Iterable[ExternalRoomEvent]:
        sql = """
        SELECT id, tenant_id, external_room_session_id, room_id, event_type, document_id, page_number, duration_ms, timestamp
        FROM external_room_events
        WHERE tenant_id = $1 AND document_id = $2
        ORDER BY timestamp ASC
        """
        async with self._pool.acquire() as con:
            rows = await con.fetch(sql, tenant_id, document_id)
        return [
            ExternalRoomEvent(
                id=row["id"],
                tenant_id=row["tenant_id"],
                external_room_session_id=row["external_room_session_id"],
                room_id=row["room_id"],
                event_type=row["event_type"],
                document_id=row["document_id"],
                page_number=row["page_number"],
                duration_ms=row["duration_ms"],
                timestamp=row["timestamp"],
            )
            for row in rows
        ]

    async def get_latest_external_room_page_view_event(
        self, *, tenant_id: str, external_room_session_id: str, document_id: str
    ) -> Optional[ExternalRoomEvent]:
        sql = """
        SELECT id, tenant_id, external_room_session_id, room_id, event_type, document_id, page_number, duration_ms, timestamp
        FROM external_room_events
        WHERE tenant_id = $1
          AND external_room_session_id = $2
          AND document_id = $3
          AND event_type = $4
        ORDER BY timestamp DESC
        LIMIT 1
        """
        async with self._pool.acquire() as con:
            row = await con.fetchrow(sql, tenant_id, external_room_session_id, document_id, ExternalRoomEventType.DOCUMENT_PAGE_VIEW.value)
        if not row:
            return None
        return ExternalRoomEvent(
            id=row["id"],
            tenant_id=row["tenant_id"],
            external_room_session_id=row["external_room_session_id"],
            room_id=row["room_id"],
            event_type=row["event_type"],
            document_id=row["document_id"],
            page_number=row["page_number"],
            duration_ms=row["duration_ms"],
            timestamp=row["timestamp"],
        )

    async def update_external_room_event_duration(
        self, *, tenant_id: str, event_id: str, duration_ms: int
    ) -> None:
        sql = """
        UPDATE external_room_events
        SET duration_ms = $3
        WHERE tenant_id = $1 AND id = $2
        """
        async with self._pool.acquire() as con:
            await con.execute(sql, tenant_id, event_id, duration_ms)


@StorageFactory.register("postgres")
def create_postgres_storage(*, pool, **_) -> StoragePort:
    return PostgresStorage(pool)
