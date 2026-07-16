"""Add NDA policies and acceptance records.

An NDA policy gates a room (document group) or an individual document; recipients
must accept the current version before any content is served. Acceptances are
immutable audit rows. Also extends the external_room_events event_type check to
allow the ``nda_accepted`` audit event.
"""

from yoyo import step

__depends__ = {"0009_add_external_room_page_view_fields"}

steps = [
    step(
        """
        CREATE TABLE nda_policies (
            id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL,
            scope_type TEXT NOT NULL CHECK (scope_type IN ('room', 'document')),
            scope_id TEXT NOT NULL,
            version INTEGER NOT NULL DEFAULT 1 CHECK (version >= 1),
            title TEXT NULL,
            content_type TEXT NOT NULL CHECK (content_type IN ('text', 'pdf')),
            text_body TEXT NULL,
            text_storage_key TEXT NULL,
            pdf_storage_key TEXT NULL,
            require_scroll BOOLEAN NOT NULL DEFAULT TRUE,
            require_typed_signature BOOLEAN NOT NULL DEFAULT TRUE,
            active BOOLEAN NOT NULL DEFAULT TRUE,
            created_by TEXT NOT NULL,
            created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
            updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
            UNIQUE (tenant_id, scope_type, scope_id)
        )
        """,
        "DROP TABLE nda_policies",
    ),
    step(
        "CREATE INDEX nda_policies_scope_idx ON nda_policies (tenant_id, scope_type, scope_id, active)",
        "DROP INDEX nda_policies_scope_idx",
    ),
    step(
        """
        CREATE TABLE nda_acceptances (
            id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL,
            nda_policy_id TEXT NOT NULL,
            scope_type TEXT NOT NULL,
            scope_id TEXT NOT NULL,
            nda_version INTEGER NOT NULL,
            subject_kind TEXT NOT NULL CHECK (
                subject_kind IN ('external_party', 'visitor_email', 'visitor_session')
            ),
            subject_id TEXT NOT NULL,
            external_party_id TEXT NULL,
            presented_email TEXT NULL,
            typed_name TEXT NOT NULL,
            scroll_confirmed BOOLEAN NOT NULL DEFAULT FALSE,
            checkbox_confirmed BOOLEAN NOT NULL DEFAULT FALSE,
            session_id TEXT NULL,
            ip_hash TEXT NULL,
            ua_hash TEXT NULL,
            accepted_at TIMESTAMP WITHOUT TIME ZONE NOT NULL
        )
        """,
        "DROP TABLE nda_acceptances",
    ),
    step(
        """
        CREATE INDEX nda_acceptances_lookup_idx
        ON nda_acceptances (tenant_id, scope_type, scope_id, nda_version, subject_kind, subject_id)
        """,
        "DROP INDEX nda_acceptances_lookup_idx",
    ),
    step(
        """
        ALTER TABLE external_room_events
        DROP CONSTRAINT IF EXISTS external_room_events_event_type_check;

        ALTER TABLE external_room_events
        ADD CONSTRAINT external_room_events_event_type_check
        CHECK (
            event_type IN (
                'room_open',
                'document_list',
                'document_view_open',
                'document_page_view',
                'document_view_close',
                'document_download',
                'nda_accepted',
                'room_close'
            )
        );
        """,
        """
        ALTER TABLE external_room_events
        DROP CONSTRAINT IF EXISTS external_room_events_event_type_check;

        ALTER TABLE external_room_events
        ADD CONSTRAINT external_room_events_event_type_check
        CHECK (
            event_type IN (
                'room_open',
                'document_list',
                'document_view_open',
                'document_page_view',
                'document_view_close',
                'document_download',
                'room_close'
            )
        );
        """,
    ),
]
