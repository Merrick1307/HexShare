"""Add document groups and instance-level document permissions.

Two-gate authorization model:
- Grouped documents (``documents.room_id`` set) inherit access from the
  IAM provider's room policy carried in the JWT.
- Ungrouped documents (``documents.room_id IS NULL``) are gated by the
  per-document ACL stored in ``document_permissions``.
"""

from yoyo import step

__depends__ = {"0003_add_document_upload_metadata"}

steps = [
    step(
        """
        CREATE TABLE document_groups (
            id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL,
            name TEXT NOT NULL,
            description TEXT NULL,
            created_by TEXT NOT NULL,
            created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL
        )
        """,
        "DROP TABLE document_groups",
    ),
    step(
        "CREATE INDEX document_groups_tenant_idx ON document_groups (tenant_id)",
        "DROP INDEX document_groups_tenant_idx",
    ),
    step(
        """
        ALTER TABLE documents
        ADD COLUMN room_id TEXT NULL
        REFERENCES document_groups(id) ON DELETE SET NULL
        """,
        "ALTER TABLE documents DROP COLUMN room_id",
    ),
    step(
        """
        CREATE INDEX documents_room_id_idx
        ON documents (room_id)
        WHERE room_id IS NOT NULL
        """,
        "DROP INDEX documents_room_id_idx",
    ),
    step(
        """
        CREATE TABLE document_permissions (
            document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
            tenant_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            permissions INTEGER NOT NULL DEFAULT 0 CHECK (permissions >= 0),
            granted_by TEXT NOT NULL,
            granted_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
            PRIMARY KEY (document_id, user_id)
        )
        """,
        "DROP TABLE document_permissions",
    ),
    step(
        "CREATE INDEX document_permissions_tenant_user_idx ON document_permissions (tenant_id, user_id)",
        "DROP INDEX document_permissions_tenant_user_idx",
    ),
]
