"""Add audit_logs table for link creation and access tracking."""

from yoyo import step

steps = [
    step(
        """
        CREATE TABLE audit_logs (
            id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL,
            event_type TEXT NOT NULL CHECK (
                event_type IN ('link.created', 'link.accessed')
            ),
            link_id TEXT NOT NULL REFERENCES share_links(id) ON DELETE CASCADE,
            document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
            actor TEXT NOT NULL,
            ip_address TEXT NULL,
            device TEXT NULL,
            location TEXT NULL,
            timestamp TIMESTAMP WITHOUT TIME ZONE NOT NULL
        )
        """,
        "DROP TABLE audit_logs"
    ),
]