from yoyo import step

__depends__ = {"0006_add_external_party_identity"}

steps = [
    step(
        """
        CREATE TABLE external_room_sessions (
            id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL,
            external_party_id TEXT NOT NULL REFERENCES external_parties(id) ON DELETE CASCADE,
            external_access_grant_id TEXT NOT NULL REFERENCES external_access_grants(id) ON DELETE CASCADE,
            room_id TEXT NOT NULL REFERENCES document_groups(id) ON DELETE CASCADE,
            permissions INTEGER NOT NULL DEFAULT 0 CHECK (permissions >= 0),
            presented_email TEXT NOT NULL,
            started_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
            ended_at TIMESTAMP WITHOUT TIME ZONE NULL,
            ip_hash TEXT NULL,
            ua_hash TEXT NULL
        )
        """,
        "DROP TABLE external_room_sessions",
    ),
    step(
        "CREATE INDEX external_room_sessions_tenant_party_idx ON external_room_sessions (tenant_id, external_party_id)",
        "DROP INDEX external_room_sessions_tenant_party_idx",
    ),
    step(
        "CREATE INDEX external_room_sessions_tenant_room_idx ON external_room_sessions (tenant_id, room_id)",
        "DROP INDEX external_room_sessions_tenant_room_idx",
    ),
    step(
        """
        CREATE TABLE external_room_events (
            id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL,
            external_room_session_id TEXT NOT NULL REFERENCES external_room_sessions(id) ON DELETE CASCADE,
            room_id TEXT NOT NULL REFERENCES document_groups(id) ON DELETE CASCADE,
            event_type TEXT NOT NULL CHECK (event_type IN ('room_open', 'document_list', 'document_download', 'room_close')),
            document_id TEXT NULL REFERENCES documents(id) ON DELETE SET NULL,
            timestamp TIMESTAMP WITHOUT TIME ZONE NOT NULL
        )
        """,
        "DROP TABLE external_room_events",
    ),
    step(
        "CREATE INDEX external_room_events_session_idx ON external_room_events (external_room_session_id, timestamp)",
        "DROP INDEX external_room_events_session_idx",
    ),
]
