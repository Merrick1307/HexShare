"""Add invitation rotation state to external access grants."""

from yoyo import step

__depends__ = {"0012_add_room_sections_and_document_order"}

steps = [
    step(
        """
        ALTER TABLE external_access_grants
            ADD COLUMN invite_version INTEGER NOT NULL DEFAULT 1
                CHECK (invite_version >= 1),
            ADD COLUMN last_invited_at TIMESTAMPTZ NULL;
        """,
        """
        ALTER TABLE external_access_grants
            DROP COLUMN IF EXISTS last_invited_at,
            DROP COLUMN IF EXISTS invite_version;
        """,
    )
]
