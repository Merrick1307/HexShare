"""Create HexShare core tables.

Notes:
- This migration mirrors the current PostgresStorage adapter and service layer.
- Primary resource IDs remain TEXT because the current app generates values like
  `doc_<uuid4hex>` and `link_<uuid4hex>` in application code.
- External identity fields such as `tenant_id` and `created_by` also remain TEXT
  so the migration stays compatible with the current FastAPI/asyncpg codepath.
- If you want UUIDv7-backed primary keys later, update the service/storage layer
  first, then add a follow-up migration.
"""

from yoyo import step

steps = [
    step(
        """
        CREATE TABLE documents (
            id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL,
            name TEXT NOT NULL,
            mime_type TEXT NOT NULL,
            size BIGINT NOT NULL CHECK (size >= 0),
            storage_key TEXT NOT NULL,
            created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
            created_by TEXT NOT NULL
        )
        """,
        "DROP TABLE documents"
    ),
    step(
        """
        CREATE TABLE share_links (
            id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL,
            document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
            jti TEXT NOT NULL UNIQUE,
            expires_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
            can_download BOOLEAN NOT NULL DEFAULT FALSE,
            can_print BOOLEAN NOT NULL DEFAULT FALSE,
            require_email BOOLEAN NOT NULL DEFAULT FALSE,
            allowed_emails TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
            revoked_at TIMESTAMP WITHOUT TIME ZONE NULL,
            created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
            created_by TEXT NOT NULL
        )
        """,
        "DROP TABLE share_links"
    ),
    step(
        """
        CREATE TABLE visitor_sessions (
            id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL,
            share_link_id TEXT NOT NULL REFERENCES share_links(id) ON DELETE CASCADE,
            visitor_id TEXT NULL,
            ip_hash TEXT NULL,
            ua_hash TEXT NULL,
            started_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
            ended_at TIMESTAMP WITHOUT TIME ZONE NULL
        )
        """,
        "DROP TABLE visitor_sessions"
    ),
    step(
        """
        CREATE TABLE view_events (
            id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL,
            document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
            share_link_id TEXT NOT NULL REFERENCES share_links(id) ON DELETE CASCADE,
            visitor_session_id TEXT NOT NULL REFERENCES visitor_sessions(id) ON DELETE CASCADE,
            event_type TEXT NOT NULL CHECK (
                event_type IN (
                    'open',
                    'page_view',
                    'heartbeat',
                    'close',
                    'download_attempt',
                    'blocked'
                )
            ),
            page_number INTEGER NULL CHECK (page_number IS NULL OR page_number >= 1),
            duration_ms INTEGER NULL CHECK (duration_ms IS NULL OR duration_ms >= 0),
            timestamp TIMESTAMP WITHOUT TIME ZONE NOT NULL,
            CHECK (event_type <> 'page_view' OR page_number IS NOT NULL)
        )
        """,
        "DROP TABLE view_events"
    ),
]
