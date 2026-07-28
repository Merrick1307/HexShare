"""Add ordered single-level room sections and document positions."""

from yoyo import step

__depends__ = {"0011_add_rate_limit_policies"}

steps = [
    step(
        """
        ALTER TABLE document_groups
            ADD CONSTRAINT document_groups_tenant_id_id_unique UNIQUE (tenant_id, id);

        CREATE TABLE room_sections (
            id TEXT NOT NULL,
            tenant_id TEXT NOT NULL,
            room_id TEXT NOT NULL REFERENCES document_groups(id) ON DELETE CASCADE,
            name TEXT NOT NULL CHECK (length(btrim(name)) BETWEEN 1 AND 120),
            position INTEGER NOT NULL CHECK (position >= 0),
            created_by TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (id),
            UNIQUE (tenant_id, room_id, id),
            CONSTRAINT room_sections_tenant_room_position_unique
                UNIQUE (tenant_id, room_id, position)
                DEFERRABLE INITIALLY DEFERRED,
            FOREIGN KEY (tenant_id, room_id)
                REFERENCES document_groups(tenant_id, id) ON DELETE CASCADE
                DEFERRABLE INITIALLY DEFERRED
        );

        CREATE INDEX room_sections_tenant_room_position_idx
            ON room_sections (tenant_id, room_id, position);

        ALTER TABLE documents
            ADD COLUMN room_section_id TEXT NULL,
            ADD COLUMN room_position INTEGER NOT NULL DEFAULT 0;

        ALTER TABLE documents
            ADD CONSTRAINT documents_room_section_fk
            FOREIGN KEY (tenant_id, room_id, room_section_id)
            REFERENCES room_sections(tenant_id, room_id, id)
            DEFERRABLE INITIALLY DEFERRED;

        WITH ranked AS (
            SELECT id,
                   ROW_NUMBER() OVER (
                       PARTITION BY tenant_id, room_id
                       ORDER BY created_at, id
                   ) - 1 AS position
            FROM documents
            WHERE room_id IS NOT NULL
        )
        UPDATE documents d
        SET room_position = ranked.position
        FROM ranked
        WHERE d.id = ranked.id;

        CREATE INDEX documents_tenant_room_section_position_idx
            ON documents (tenant_id, room_id, room_section_id, room_position);
        """,
        """
        DROP INDEX IF EXISTS documents_tenant_room_section_position_idx;
        ALTER TABLE documents DROP CONSTRAINT IF EXISTS documents_room_section_fk;
        ALTER TABLE documents DROP COLUMN IF EXISTS room_position;
        ALTER TABLE documents DROP COLUMN IF EXISTS room_section_id;
        DROP TABLE IF EXISTS room_sections;
        ALTER TABLE document_groups
            DROP CONSTRAINT IF EXISTS document_groups_tenant_id_id_unique;
        """,
    )
]
