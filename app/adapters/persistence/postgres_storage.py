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
    NdaAcceptance,
    NdaContentType,
    NdaPolicy,
    NdaScopeType,
    NdaSubjectKind,
    RoomSection,
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
            room_section_id=row["room_section_id"] if "room_section_id" in row.keys() else None,
            room_position=int(row["room_position"] or 0) if "room_position" in row.keys() else 0,
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
            invite_version=int(row["invite_version"] or 1)
            if "invite_version" in row.keys()
            else 1,
            last_invited_at=row["last_invited_at"]
            if "last_invited_at" in row.keys()
            else None,
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
        INSERT INTO documents (
            id, tenant_id, name, mime_type, size, storage_key, created_at,
            created_by, room_id, room_section_id, room_position
        )
        VALUES (
            $1, $2, $3, $4, $5, $6, $7, $8, $9::text, $10::text,
            CASE WHEN $9::text IS NULL THEN 0 ELSE (
                SELECT COALESCE(MAX(room_position) + 1, 0)
                FROM documents
                WHERE tenant_id = $2 AND room_id = $9::text
                  AND room_section_id IS NOT DISTINCT FROM $10::text
            ) END
        )
        """
        async with self._pool.acquire() as con:
            async with con.transaction():
                if document.room_id is not None:
                    await con.execute(
                        "SELECT pg_advisory_xact_lock(hashtext($1), hashtext($2))",
                        document.tenant_id,
                        f"{document.room_id}:{document.room_section_id or ''}",
                    )
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
                    document.room_section_id,
                )

    async def get_document(self, *, tenant_id: str, document_id: str) -> Optional[Document]:
        sql = """
        SELECT id, tenant_id, name, mime_type, size, storage_key, created_at,
               created_by, room_id, room_section_id, room_position
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
        SELECT id, tenant_id, name, mime_type, size, storage_key, created_at,
               created_by, room_id, room_section_id, room_position
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
               d.created_at, d.created_by, d.room_id, d.room_section_id, d.room_position
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

    async def page_ungrouped_documents_by_permission(
        self,
        *,
        tenant_id: str,
        user_id: str,
        required_permission: int,
        query: Optional[str],
        offset: int,
        limit: int,
    ) -> tuple[list[Document], int]:
        normalized = (query or "").strip()
        if query is not None and not normalized:
            return [], 0
        where_query = ""
        params: list[object] = [tenant_id, user_id, int(required_permission)]
        if query is not None:
            escaped = normalized.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            params.append(f"%{escaped}%")
            where_query = f" AND d.name ILIKE ${len(params)} ESCAPE '\\'"
        params.extend([offset, limit])
        offset_index = len(params) - 1
        limit_index = len(params)
        sql = f"""
        SELECT d.id, d.tenant_id, d.name, d.mime_type, d.size, d.storage_key,
               d.created_at, d.created_by, d.room_id, d.room_section_id, d.room_position,
               COUNT(*) OVER() AS full_count
        FROM documents d
        JOIN document_permissions p
          ON p.document_id = d.id AND p.tenant_id = d.tenant_id AND p.user_id = $2
        WHERE d.tenant_id = $1
          AND d.room_id IS NULL
          AND (p.permissions & $3) <> 0
          {where_query}
        ORDER BY d.created_at DESC, d.id
        OFFSET ${offset_index} LIMIT ${limit_index}
        """
        async with self._pool.acquire() as con:
            rows = await con.fetch(sql, *params)
            if rows:
                return [self._row_to_document(row) for row in rows], int(rows[0]["full_count"])
            count_params = params[: 4 if query is not None else 3]
            count_sql = f"""
            SELECT COUNT(*)
            FROM documents d
            JOIN document_permissions p
              ON p.document_id = d.id AND p.tenant_id = d.tenant_id AND p.user_id = $2
            WHERE d.tenant_id = $1 AND d.room_id IS NULL
              AND (p.permissions & $3) <> 0 {where_query}
            """
            total = int(await con.fetchval(count_sql, *count_params))
        return [], total

    async def list_documents_by_room(
        self, *, tenant_id: str, room_id: str
    ) -> Iterable[Document]:
        sql = """
        SELECT id, tenant_id, name, mime_type, size, storage_key, created_at,
               created_by, room_id, room_section_id, room_position
        FROM documents
        WHERE tenant_id = $1 AND room_id = $2
        ORDER BY room_section_id NULLS LAST, room_position, created_at, id
        """
        async with self._pool.acquire() as con:
            rows = await con.fetch(sql, tenant_id, room_id)
        return [self._row_to_document(row) for row in rows]

    @staticmethod
    def _row_to_room_section(row) -> RoomSection:
        return RoomSection(
            id=row["id"],
            tenant_id=row["tenant_id"],
            room_id=row["room_id"],
            name=row["name"],
            position=int(row["position"]),
            created_by=row["created_by"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    async def list_room_sections(
        self, *, tenant_id: str, room_id: str
    ) -> Iterable[RoomSection]:
        sql = """
        SELECT id, tenant_id, room_id, name, position, created_by, created_at, updated_at
        FROM room_sections
        WHERE tenant_id = $1 AND room_id = $2
        ORDER BY position, id
        """
        async with self._pool.acquire() as con:
            rows = await con.fetch(sql, tenant_id, room_id)
        return [self._row_to_room_section(row) for row in rows]

    async def create_room_section(self, section: RoomSection) -> RoomSection:
        sql = """
        INSERT INTO room_sections (
            id, tenant_id, room_id, name, position, created_by, created_at, updated_at
        )
        SELECT $1, $2, $3, $4, COALESCE(MAX(position) + 1, 0), $5, $6, $7
        FROM room_sections
        WHERE tenant_id = $2 AND room_id = $3
        RETURNING id, tenant_id, room_id, name, position, created_by, created_at, updated_at
        """
        async with self._pool.acquire() as con:
            async with con.transaction():
                await con.execute(
                    "SELECT pg_advisory_xact_lock(hashtext($1), hashtext($2))",
                    section.tenant_id,
                    section.room_id,
                )
                row = await con.fetchrow(
                    sql,
                    section.id,
                    section.tenant_id,
                    section.room_id,
                    section.name,
                    section.created_by,
                    section.created_at,
                    section.updated_at,
                )
        return self._row_to_room_section(row)

    async def update_room_section(
        self, *, tenant_id: str, room_id: str, section_id: str, name: str
    ) -> Optional[RoomSection]:
        sql = """
        UPDATE room_sections
        SET name = $4, updated_at = NOW()
        WHERE tenant_id = $1 AND room_id = $2 AND id = $3
        RETURNING id, tenant_id, room_id, name, position, created_by, created_at, updated_at
        """
        async with self._pool.acquire() as con:
            row = await con.fetchrow(sql, tenant_id, room_id, section_id, name)
        return self._row_to_room_section(row) if row else None

    async def delete_room_section(
        self, *, tenant_id: str, room_id: str, section_id: str
    ) -> bool:
        async with self._pool.acquire() as con:
            async with con.transaction():
                await con.execute(
                    "SELECT pg_advisory_xact_lock(hashtext($1), hashtext($2))",
                    tenant_id,
                    room_id,
                )
                await con.execute("SET CONSTRAINTS ALL DEFERRED")
                row = await con.fetchrow(
                    """
                    SELECT id FROM room_sections
                    WHERE tenant_id = $1 AND room_id = $2 AND id = $3
                    FOR UPDATE
                    """,
                    tenant_id,
                    room_id,
                    section_id,
                )
                if row is None:
                    return False
                start_position = int(
                    await con.fetchval(
                        """
                        SELECT COALESCE(MAX(room_position) + 1, 0)
                        FROM documents
                        WHERE tenant_id = $1 AND room_id = $2 AND room_section_id IS NULL
                        """,
                        tenant_id,
                        room_id,
                    )
                )
                await con.execute(
                    """
                    WITH moved AS (
                        SELECT id, ROW_NUMBER() OVER (ORDER BY room_position, created_at, id) - 1 AS offset
                        FROM documents
                        WHERE tenant_id = $1 AND room_id = $2 AND room_section_id = $3
                    )
                    UPDATE documents d
                    SET room_section_id = NULL, room_position = $4 + moved.offset
                    FROM moved
                    WHERE d.id = moved.id
                    """,
                    tenant_id,
                    room_id,
                    section_id,
                    start_position,
                )
                await con.execute(
                    "DELETE FROM room_sections WHERE tenant_id = $1 AND room_id = $2 AND id = $3",
                    tenant_id,
                    room_id,
                    section_id,
                )
                await con.execute(
                    """
                    WITH ordered AS (
                        SELECT id, ROW_NUMBER() OVER (ORDER BY position, id) - 1 AS new_position
                        FROM room_sections
                        WHERE tenant_id = $1 AND room_id = $2
                    )
                    UPDATE room_sections rs
                    SET position = ordered.new_position, updated_at = NOW()
                    FROM ordered WHERE rs.id = ordered.id
                    """,
                    tenant_id,
                    room_id,
                )
        return True

    async def reorder_room_sections(
        self, *, tenant_id: str, room_id: str, section_ids: list[str]
    ) -> Iterable[RoomSection]:
        if len(section_ids) != len(set(section_ids)):
            raise ValueError("invalid_section_order")
        async with self._pool.acquire() as con:
            async with con.transaction():
                await con.execute(
                    "SELECT pg_advisory_xact_lock(hashtext($1), hashtext($2))",
                    tenant_id,
                    room_id,
                )
                rows = await con.fetch(
                    """
                    SELECT id FROM room_sections
                    WHERE tenant_id = $1 AND room_id = $2
                    FOR UPDATE
                    """,
                    tenant_id,
                    room_id,
                )
                if {row["id"] for row in rows} != set(section_ids):
                    raise ValueError("invalid_section_order")
                await con.execute("SET CONSTRAINTS ALL DEFERRED")
                for position, section_id in enumerate(section_ids):
                    await con.execute(
                        """
                        UPDATE room_sections SET position = $4, updated_at = NOW()
                        WHERE tenant_id = $1 AND room_id = $2 AND id = $3
                        """,
                        tenant_id,
                        room_id,
                        section_id,
                        position,
                    )
        return await self.list_room_sections(tenant_id=tenant_id, room_id=room_id)

    async def place_room_document(
        self,
        *,
        tenant_id: str,
        document_id: str,
        room_id: str,
        section_id: Optional[str],
        position: Optional[int],
    ) -> Optional[Document]:
        async with self._pool.acquire() as con:
            async with con.transaction():
                await con.execute(
                    "SELECT pg_advisory_xact_lock(hashtext($1), hashtext($2))",
                    tenant_id,
                    room_id,
                )
                doc = await con.fetchrow(
                    """
                    SELECT id, room_id, room_section_id FROM documents
                    WHERE tenant_id = $1 AND id = $2 FOR UPDATE
                    """,
                    tenant_id,
                    document_id,
                )
                if doc is None:
                    return None
                if section_id is not None:
                    exists = await con.fetchval(
                        """
                        SELECT EXISTS(
                            SELECT 1 FROM room_sections
                            WHERE tenant_id = $1 AND room_id = $2 AND id = $3
                        )
                        """,
                        tenant_id,
                        room_id,
                        section_id,
                    )
                    if not exists:
                        raise ValueError("section_not_found")
                old_room_id, old_section_id = doc["room_id"], doc["room_section_id"]
                if old_room_id is not None:
                    await con.execute(
                        """
                        WITH ordered AS (
                            SELECT id, ROW_NUMBER() OVER (ORDER BY room_position, created_at, id) - 1 AS pos
                            FROM documents
                            WHERE tenant_id = $1 AND room_id = $2
                              AND room_section_id IS NOT DISTINCT FROM $3
                              AND id <> $4
                        )
                        UPDATE documents d SET room_position = ordered.pos
                        FROM ordered WHERE d.id = ordered.id
                        """,
                        tenant_id,
                        old_room_id,
                        old_section_id,
                        document_id,
                    )
                target_count = int(
                    await con.fetchval(
                        """
                        SELECT COUNT(*) FROM documents
                        WHERE tenant_id = $1 AND room_id = $2
                          AND room_section_id IS NOT DISTINCT FROM $3
                          AND id <> $4
                        """,
                        tenant_id,
                        room_id,
                        section_id,
                        document_id,
                    )
                )
                insert_at = target_count if position is None else max(0, min(position, target_count))
                await con.execute(
                    """
                    UPDATE documents SET room_position = room_position + 1
                    WHERE tenant_id = $1 AND room_id = $2
                      AND room_section_id IS NOT DISTINCT FROM $3
                      AND id <> $4 AND room_position >= $5
                    """,
                    tenant_id,
                    room_id,
                    section_id,
                    document_id,
                    insert_at,
                )
                row = await con.fetchrow(
                    """
                    UPDATE documents
                    SET room_id = $3, room_section_id = $4, room_position = $5
                    WHERE tenant_id = $1 AND id = $2
                    RETURNING *
                    """,
                    tenant_id,
                    document_id,
                    room_id,
                    section_id,
                    insert_at,
                )
        return self._row_to_document(row) if row else None

    async def reorder_room_documents(
        self,
        *,
        tenant_id: str,
        room_id: str,
        section_id: Optional[str],
        document_ids: list[str],
    ) -> Iterable[Document]:
        if len(document_ids) != len(set(document_ids)):
            raise ValueError("invalid_document_order")
        async with self._pool.acquire() as con:
            async with con.transaction():
                await con.execute(
                    "SELECT pg_advisory_xact_lock(hashtext($1), hashtext($2))",
                    tenant_id,
                    room_id,
                )
                rows = await con.fetch(
                    """
                    SELECT id FROM documents
                    WHERE tenant_id = $1 AND room_id = $2
                      AND room_section_id IS NOT DISTINCT FROM $3
                    FOR UPDATE
                    """,
                    tenant_id,
                    room_id,
                    section_id,
                )
                if {row["id"] for row in rows} != set(document_ids):
                    raise ValueError("invalid_document_order")
                for position, document_id in enumerate(document_ids):
                    await con.execute(
                        """
                        UPDATE documents SET room_position = $4
                        WHERE tenant_id = $1 AND room_id = $2 AND id = $3
                        """,
                        tenant_id,
                        room_id,
                        document_id,
                        position,
                    )
        docs = await self.list_documents_by_room(tenant_id=tenant_id, room_id=room_id)
        by_id = {doc.id: doc for doc in docs}
        return [by_id[document_id] for document_id in document_ids]


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

    async def page_document_groups_by_ids(
        self,
        *,
        tenant_id: str,
        group_ids: Iterable[str],
        query: Optional[str],
        offset: int,
        limit: int,
    ) -> tuple[list[DocumentGroup], int]:
        ids = list(group_ids)
        if not ids:
            return [], 0
        normalized = (query or "").strip()
        if query is not None and not normalized:
            return [], 0
        params: list[object] = [tenant_id, ids]
        query_clause = ""
        if query is not None:
            escaped = normalized.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            params.append(f"%{escaped}%")
            query_clause = (
                f" AND (name ILIKE ${len(params)} ESCAPE '\\'"
                f" OR COALESCE(description, '') ILIKE ${len(params)} ESCAPE '\\')"
            )
        params.extend([offset, limit])
        offset_index, limit_index = len(params) - 1, len(params)
        sql = f"""
        SELECT id, tenant_id, name, description, created_by, created_at,
               COUNT(*) OVER() AS full_count
        FROM document_groups
        WHERE tenant_id = $1 AND id = ANY($2::text[]) {query_clause}
        ORDER BY created_at DESC, id
        OFFSET ${offset_index} LIMIT ${limit_index}
        """
        async with self._pool.acquire() as con:
            rows = await con.fetch(sql, *params)
            if rows:
                return [self._row_to_group(row) for row in rows], int(rows[0]["full_count"])
            count_params = params[: 3 if query is not None else 2]
            total = int(
                await con.fetchval(
                    f"""
                    SELECT COUNT(*) FROM document_groups
                    WHERE tenant_id = $1 AND id = ANY($2::text[]) {query_clause}
                    """,
                    *count_params,
                )
            )
        return [], total

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
            SET room_id = $3,
                room_section_id = NULL,
                room_position = CASE
                    WHEN $3 IS NULL THEN 0
                    ELSE (
                        SELECT COUNT(*) FROM documents target
                        WHERE target.tenant_id = $1 AND target.room_id = $3
                          AND target.room_section_id IS NULL AND target.id <> $2
                    )
                END
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
            can_download, can_print, expires_at, revoked_at, granted_by, granted_at, updated_at,
            invite_version, last_invited_at
        ) VALUES (
            $1, $2, $3, $4, $5, $6,
            $7, $8, $9, $10, $11, $12, $13, $14, $15, $16
        )
        ON CONFLICT (id) DO UPDATE
            SET permissions = EXCLUDED.permissions,
                can_download = EXCLUDED.can_download,
                can_print = EXCLUDED.can_print,
                expires_at = EXCLUDED.expires_at,
                revoked_at = EXCLUDED.revoked_at,
                updated_at = EXCLUDED.updated_at,
                invite_version = EXCLUDED.invite_version,
                last_invited_at = EXCLUDED.last_invited_at
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
                grant.invite_version,
                grant.last_invited_at,
            )

    async def get_external_access_grant(
        self, *, tenant_id: str, grant_id: str
    ) -> Optional[ExternalAccessGrant]:
        sql = """
        SELECT id, tenant_id, external_party_id, resource_type, resource_id, grant_type,
               permissions, can_download, can_print, expires_at, revoked_at, granted_by, granted_at,
               updated_at, invite_version, last_invited_at
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
               permissions, can_download, can_print, expires_at, revoked_at, granted_by, granted_at,
               updated_at, invite_version, last_invited_at
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

    # -- NDA policies & acceptances -------------------------------------------------

    @staticmethod
    def _row_to_nda_policy(row) -> Optional[NdaPolicy]:
        if not row:
            return None
        return NdaPolicy(
            id=row["id"],
            tenant_id=row["tenant_id"],
            scope_type=NdaScopeType(row["scope_type"]),
            scope_id=row["scope_id"],
            version=row["version"],
            title=row["title"],
            content_type=NdaContentType(row["content_type"]),
            text_body=row["text_body"],
            text_storage_key=row["text_storage_key"],
            pdf_storage_key=row["pdf_storage_key"],
            require_scroll=row["require_scroll"],
            require_typed_signature=row["require_typed_signature"],
            active=row["active"],
            created_by=row["created_by"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _row_to_nda_acceptance(row) -> Optional[NdaAcceptance]:
        if not row:
            return None
        return NdaAcceptance(
            id=row["id"],
            tenant_id=row["tenant_id"],
            nda_policy_id=row["nda_policy_id"],
            scope_type=NdaScopeType(row["scope_type"]),
            scope_id=row["scope_id"],
            nda_version=row["nda_version"],
            subject_kind=NdaSubjectKind(row["subject_kind"]),
            subject_id=row["subject_id"],
            external_party_id=row["external_party_id"],
            presented_email=row["presented_email"],
            typed_name=row["typed_name"],
            scroll_confirmed=row["scroll_confirmed"],
            checkbox_confirmed=row["checkbox_confirmed"],
            session_id=row["session_id"],
            ip_hash=row["ip_hash"],
            ua_hash=row["ua_hash"],
            accepted_at=row["accepted_at"],
        )

    async def save_nda_policy(self, policy: NdaPolicy) -> None:
        sql = """
        INSERT INTO nda_policies (
            id, tenant_id, scope_type, scope_id, version, title, content_type,
            text_body, text_storage_key, pdf_storage_key, require_scroll,
            require_typed_signature, active, created_by, created_at, updated_at
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16)
        ON CONFLICT (tenant_id, scope_type, scope_id) DO UPDATE SET
            version = EXCLUDED.version,
            title = EXCLUDED.title,
            content_type = EXCLUDED.content_type,
            text_body = EXCLUDED.text_body,
            text_storage_key = EXCLUDED.text_storage_key,
            pdf_storage_key = EXCLUDED.pdf_storage_key,
            require_scroll = EXCLUDED.require_scroll,
            require_typed_signature = EXCLUDED.require_typed_signature,
            active = EXCLUDED.active,
            updated_at = EXCLUDED.updated_at
        """
        async with self._pool.acquire() as con:
            await con.execute(
                sql,
                policy.id,
                policy.tenant_id,
                policy.scope_type.value,
                policy.scope_id,
                policy.version,
                policy.title,
                policy.content_type.value,
                policy.text_body,
                policy.text_storage_key,
                policy.pdf_storage_key,
                policy.require_scroll,
                policy.require_typed_signature,
                policy.active,
                policy.created_by,
                policy.created_at,
                policy.updated_at,
            )

    async def get_nda_policy(
        self, *, tenant_id: str, scope_type: str, scope_id: str, active_only: bool = True
    ) -> Optional[NdaPolicy]:
        sql = """
        SELECT * FROM nda_policies
        WHERE tenant_id = $1 AND scope_type = $2 AND scope_id = $3
        """
        if active_only:
            sql += " AND active = TRUE"
        async with self._pool.acquire() as con:
            row = await con.fetchrow(sql, tenant_id, scope_type, scope_id)
        return self._row_to_nda_policy(row)

    async def deactivate_nda_policy(
        self, *, tenant_id: str, scope_type: str, scope_id: str
    ) -> None:
        sql = """
        UPDATE nda_policies SET active = FALSE, updated_at = NOW()
        WHERE tenant_id = $1 AND scope_type = $2 AND scope_id = $3
        """
        async with self._pool.acquire() as con:
            await con.execute(sql, tenant_id, scope_type, scope_id)

    async def save_nda_acceptance(self, acceptance: NdaAcceptance) -> None:
        sql = """
        INSERT INTO nda_acceptances (
            id, tenant_id, nda_policy_id, scope_type, scope_id, nda_version,
            subject_kind, subject_id, external_party_id, presented_email, typed_name,
            scroll_confirmed, checkbox_confirmed, session_id, ip_hash, ua_hash, accepted_at
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17)
        """
        async with self._pool.acquire() as con:
            await con.execute(
                sql,
                acceptance.id,
                acceptance.tenant_id,
                acceptance.nda_policy_id,
                acceptance.scope_type.value,
                acceptance.scope_id,
                acceptance.nda_version,
                acceptance.subject_kind.value,
                acceptance.subject_id,
                acceptance.external_party_id,
                acceptance.presented_email,
                acceptance.typed_name,
                acceptance.scroll_confirmed,
                acceptance.checkbox_confirmed,
                acceptance.session_id,
                acceptance.ip_hash,
                acceptance.ua_hash,
                acceptance.accepted_at,
            )

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
        sql = """
        SELECT * FROM nda_acceptances
        WHERE tenant_id = $1 AND scope_type = $2 AND scope_id = $3
          AND nda_version = $4 AND subject_kind = $5 AND subject_id = $6
        ORDER BY accepted_at DESC
        LIMIT 1
        """
        async with self._pool.acquire() as con:
            row = await con.fetchrow(
                sql, tenant_id, scope_type, scope_id, nda_version, subject_kind, subject_id
            )
        return self._row_to_nda_acceptance(row)

    async def list_nda_acceptances(
        self, *, tenant_id: str, scope_type: str, scope_id: str
    ) -> Iterable[NdaAcceptance]:
        sql = """
        SELECT * FROM nda_acceptances
        WHERE tenant_id = $1 AND scope_type = $2 AND scope_id = $3
        ORDER BY accepted_at DESC
        """
        async with self._pool.acquire() as con:
            rows = await con.fetch(sql, tenant_id, scope_type, scope_id)
        return [self._row_to_nda_acceptance(row) for row in rows if row]

    async def list_nda_policies(
        self, *, tenant_id: str, active_only: bool = True
    ) -> Iterable[NdaPolicy]:
        sql = "SELECT * FROM nda_policies WHERE tenant_id = $1"
        if active_only:
            sql += " AND active = TRUE"
        sql += " ORDER BY updated_at DESC"
        async with self._pool.acquire() as con:
            rows = await con.fetch(sql, tenant_id)
        return [self._row_to_nda_policy(row) for row in rows if row]

    async def list_rate_limit_policies(self, *, tier: str) -> Iterable[dict]:
        sql = """
        SELECT policy_name, limit_count, window_seconds
        FROM rate_limit_policies
        WHERE tier = $1 AND enabled = TRUE
        """
        async with self._pool.acquire() as con:
            rows = await con.fetch(sql, tier)
        return [dict(row) for row in rows]

    async def get_workspace_summary(self, *, tenant_id: str) -> dict:
        sql = """
        SELECT
            (SELECT COUNT(*) FROM documents WHERE tenant_id = $1) AS documents,
            (SELECT COUNT(*) FROM document_groups WHERE tenant_id = $1) AS groups,
            (SELECT COUNT(*) FROM share_links
                WHERE tenant_id = $1 AND revoked_at IS NULL AND expires_at > NOW()) AS active_links,
            (SELECT COUNT(*) FROM external_parties
                WHERE tenant_id = $1 AND status = 'active') AS external_recipients,
            (SELECT COUNT(*) FROM view_events
                WHERE tenant_id = $1 AND event_type = 'open')
            + (SELECT COUNT(*) FROM external_room_events
                WHERE tenant_id = $1 AND event_type = 'document_view_open') AS document_opens
        """
        async with self._pool.acquire() as con:
            row = await con.fetchrow(sql, tenant_id)
        return {
            "documents": int(row["documents"] or 0),
            "groups": int(row["groups"] or 0),
            "active_links": int(row["active_links"] or 0),
            "external_recipients": int(row["external_recipients"] or 0),
            "document_opens": int(row["document_opens"] or 0),
        }

    async def list_recent_view_events(
        self, *, tenant_id: str, limit: int = 100
    ) -> Iterable[ViewEvent]:
        sql = """
        SELECT id, tenant_id, document_id, share_link_id, visitor_session_id,
               event_type, page_number, duration_ms, timestamp
        FROM view_events
        WHERE tenant_id = $1
        ORDER BY timestamp DESC
        LIMIT $2
        """
        async with self._pool.acquire() as con:
            rows = await con.fetch(sql, tenant_id, limit)
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

    async def list_recent_external_room_events(
        self, *, tenant_id: str, limit: int = 100
    ) -> Iterable[ExternalRoomEvent]:
        sql = """
        SELECT id, tenant_id, external_room_session_id, room_id, event_type,
               document_id, page_number, duration_ms, timestamp
        FROM external_room_events
        WHERE tenant_id = $1
        ORDER BY timestamp DESC
        LIMIT $2
        """
        async with self._pool.acquire() as con:
            rows = await con.fetch(sql, tenant_id, limit)
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


@StorageFactory.register("postgres")
def create_postgres_storage(*, pool, **_) -> StoragePort:
    return PostgresStorage(pool)
