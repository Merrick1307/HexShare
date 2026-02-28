"""
PostgreSQL storage adapter using asyncpg.

This adapter implements :class:`~app.ports.StoragePort` using the
asyncpg library and raw SQL.  It requires a connection pool and
manages tenant isolation at the application layer.  PostgreSQL Row
Level Security (RLS) could be added in future revisions to further
constrain access.  The SQL statements provided here are minimal
placeholders and should be adapted to your schema.

Example usage::

    import asyncpg
    from app.adapters.persistence.postgres_storage import PostgresStorage

    pool = await asyncpg.create_pool(dsn="postgresql://user:pass@localhost/db")
    storage = PostgresStorage(pool)
    document = await storage.get_document(tenant_id="tenant_1", document_id="doc_1")

Note: This implementation is intentionally incomplete; it is a
scaffolding to be extended.  See the ``sql`` strings in each method
for the expected structure.
"""
from __future__ import annotations

import asyncpg  # type: ignore
from datetime import datetime
from typing import Iterable, Optional

from app.domain import Document, ShareLink, VisitorSession, ViewEvent
from app.infra.factories import StorageFactory
from app.ports.storage_port import StoragePort


class PostgresStorage(StoragePort):
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    def generate_id(self, prefix: str) -> str:
        # For PostgreSQL we may use sequences instead.  Here we
        # generate a UUID-like string for demonstration.
        import uuid

        return f"{prefix}_{uuid.uuid4().hex}"

    async def save_document(self, document: Document) -> None:
        sql = """
        INSERT INTO documents (id, tenant_id, name, mime_type, size, storage_key, created_at, created_by)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
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
            )

    async def get_document(self, *, tenant_id: str, document_id: str) -> Optional[Document]:
        sql = """
        SELECT id, tenant_id, name, mime_type, size, storage_key, created_at, created_by
        FROM documents
        WHERE tenant_id = $1 AND id = $2
        """
        async with self._pool.acquire() as con:
            row = await con.fetchrow(sql, tenant_id, document_id)
            if row:
                return Document(
                    id=row["id"],
                    tenant_id=row["tenant_id"],
                    name=row["name"],
                    mime_type=row["mime_type"],
                    size=row["size"],
                    storage_key=row["storage_key"],
                    created_at=row["created_at"],
                    created_by=row["created_by"],
                )
            return None

    async def list_documents(self, *, tenant_id: str) -> Iterable[Document]:
        sql = """
        SELECT id, tenant_id, name, mime_type, size, storage_key, created_at, created_by
        FROM documents
        WHERE tenant_id = $1
        ORDER BY created_at DESC
        """
        async with self._pool.acquire() as con:
            rows = await con.fetch(sql, tenant_id)
        return [
            Document(
                id=row["id"],
                tenant_id=row["tenant_id"],
                name=row["name"],
                mime_type=row["mime_type"],
                size=row["size"],
                storage_key=row["storage_key"],
                created_at=row["created_at"],
                created_by=row["created_by"],
            )
            for row in rows
        ]

    # --- ShareLink operations -----------------------------------------
    async def save_share_link(self, link: ShareLink) -> None:
        sql = """
        INSERT INTO share_links (
            id, tenant_id, document_id, jti, expires_at,
            can_download, can_print, require_email, allowed_emails,
            revoked_at, created_at, created_by
        ) VALUES (
            $1, $2, $3, $4, $5,
            $6, $7, $8, $9,
            $10, $11, $12
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
            ip_hash, ua_hash, started_at, ended_at
        ) VALUES (
            $1, $2, $3, $4,
            $5, $6, $7, $8
        )
        """
        async with self._pool.acquire() as con:
            await con.execute(
                sql,
                session.id,
                session.tenant_id,
                session.share_link_id,
                session.visitor_id,
                session.ip_hash,
                session.ua_hash,
                session.started_at,
                session.ended_at,
            )

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


@StorageFactory.register("postgres")
def create_postgres_storage(*, pool, **_) -> StoragePort:
    return PostgresStorage(pool)