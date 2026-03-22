"""Add indexes for current HexShare query patterns."""

from yoyo import step

__depends__ = {"0001_create_hexshare_core_tables"}

steps = [
    step(
        "CREATE INDEX documents_tenant_created_at_idx ON documents (tenant_id, created_at DESC)",
        "DROP INDEX documents_tenant_created_at_idx"
    ),
    step(
        "CREATE INDEX share_links_tenant_document_created_at_idx ON share_links (tenant_id, document_id, created_at DESC)",
        "DROP INDEX share_links_tenant_document_created_at_idx"
    ),
    step(
        "CREATE INDEX share_links_tenant_created_at_idx ON share_links (tenant_id, created_at DESC)",
        "DROP INDEX share_links_tenant_created_at_idx"
    ),
    step(
        "CREATE INDEX visitor_sessions_share_link_started_at_idx ON visitor_sessions (share_link_id, started_at DESC)",
        "DROP INDEX visitor_sessions_share_link_started_at_idx"
    ),
    step(
        "CREATE INDEX view_events_tenant_document_timestamp_idx ON view_events (tenant_id, document_id, timestamp ASC)",
        "DROP INDEX view_events_tenant_document_timestamp_idx"
    ),
    step(
        "CREATE INDEX view_events_visitor_session_timestamp_idx ON view_events (visitor_session_id, timestamp ASC)",
        "DROP INDEX view_events_visitor_session_timestamp_idx"
    ),
]
