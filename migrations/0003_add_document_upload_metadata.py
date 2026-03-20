"""Add upload metadata columns to documents.

This migration is intentionally additive and backwards-compatible with the
current HexShare Postgres adapter:
- existing INSERT statements continue to work because new columns are nullable
  or have safe defaults
- current SELECT statements are unaffected because they enumerate columns
  explicitly

The new columns support the object-storage upload flow by making room for:
- upload lifecycle state
- object ETag returned by the object store
- optional SHA-256 integrity tracking
- explicit uploaded timestamp
"""

from yoyo import step

__depends__ = {"0002_add_hexshare_indexes"}

steps = [
    step(
        """
        ALTER TABLE documents
        ADD COLUMN upload_status TEXT NOT NULL DEFAULT 'ready'
        CHECK (upload_status IN ('pending', 'uploaded', 'ready', 'failed'))
        """,
        "ALTER TABLE documents DROP COLUMN upload_status",
    ),
    step(
        "ALTER TABLE documents ADD COLUMN object_etag TEXT NULL",
        "ALTER TABLE documents DROP COLUMN object_etag",
    ),
    step(
        """
        ALTER TABLE documents
        ADD COLUMN checksum_sha256 TEXT NULL
        CHECK (
            checksum_sha256 IS NULL
            OR checksum_sha256 ~ '^[A-Fa-f0-9]{64}$'
        )
        """,
        "ALTER TABLE documents DROP COLUMN checksum_sha256",
    ),
    step(
        "ALTER TABLE documents ADD COLUMN uploaded_at TIMESTAMP WITHOUT TIME ZONE NULL",
        "ALTER TABLE documents DROP COLUMN uploaded_at",
    ),
    step(
        "CREATE INDEX documents_tenant_upload_status_created_at_idx ON documents (tenant_id, upload_status, created_at DESC)",
        "DROP INDEX documents_tenant_upload_status_created_at_idx",
    ),
]
