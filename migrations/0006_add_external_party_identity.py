from yoyo import step

__depends__ = {"0005_add_local_auth_and_group_memberships"}

steps = [
    step(
        """
        CREATE TABLE external_parties (
            id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL,
            display_name TEXT NULL,
            status TEXT NOT NULL CHECK (status IN ('active', 'revoked', 'archived', 'blocked')),
            created_by TEXT NOT NULL,
            created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
            updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
            archived_at TIMESTAMP WITHOUT TIME ZONE NULL
        )
        """,
        "DROP TABLE external_parties",
    ),
    step(
        "CREATE INDEX external_parties_tenant_status_idx ON external_parties (tenant_id, status)",
        "DROP INDEX external_parties_tenant_status_idx",
    ),
    step(
        """
        CREATE TABLE external_party_emails (
            id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL,
            external_party_id TEXT NOT NULL REFERENCES external_parties(id) ON DELETE CASCADE,
            email_normalized TEXT NOT NULL,
            email_original TEXT NOT NULL,
            is_primary BOOLEAN NOT NULL DEFAULT TRUE,
            verified_at TIMESTAMP WITHOUT TIME ZONE NULL,
            last_seen_at TIMESTAMP WITHOUT TIME ZONE NULL,
            created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL
        )
        """,
        "DROP TABLE external_party_emails",
    ),
    step(
        "CREATE UNIQUE INDEX external_party_emails_tenant_email_uidx ON external_party_emails (tenant_id, email_normalized)",
        "DROP INDEX external_party_emails_tenant_email_uidx",
    ),
    step(
        "CREATE INDEX external_party_emails_party_idx ON external_party_emails (external_party_id)",
        "DROP INDEX external_party_emails_party_idx",
    ),
    step(
        """
        CREATE TABLE external_access_grants (
            id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL,
            external_party_id TEXT NOT NULL REFERENCES external_parties(id) ON DELETE CASCADE,
            resource_type TEXT NOT NULL CHECK (resource_type IN ('document', 'room')),
            resource_id TEXT NOT NULL,
            grant_type TEXT NOT NULL CHECK (grant_type IN ('link', 'provisioned')),
            permissions INTEGER NOT NULL DEFAULT 0 CHECK (permissions >= 0),
            can_download BOOLEAN NOT NULL DEFAULT FALSE,
            can_print BOOLEAN NOT NULL DEFAULT FALSE,
            expires_at TIMESTAMP WITHOUT TIME ZONE NULL,
            revoked_at TIMESTAMP WITHOUT TIME ZONE NULL,
            granted_by TEXT NOT NULL,
            granted_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
            updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL
        )
        """,
        "DROP TABLE external_access_grants",
    ),
    step(
        "CREATE INDEX external_access_grants_tenant_party_idx ON external_access_grants (tenant_id, external_party_id)",
        "DROP INDEX external_access_grants_tenant_party_idx",
    ),
    step(
        "CREATE INDEX external_access_grants_resource_idx ON external_access_grants (tenant_id, resource_type, resource_id)",
        "DROP INDEX external_access_grants_resource_idx",
    ),
    step(
        """
        ALTER TABLE share_links
        ADD COLUMN external_access_grant_id TEXT NULL REFERENCES external_access_grants(id) ON DELETE SET NULL
        """,
        "ALTER TABLE share_links DROP COLUMN external_access_grant_id",
    ),
    step(
        """
        ALTER TABLE share_links
        ADD COLUMN access_mode TEXT NOT NULL DEFAULT 'anonymous'
        CHECK (access_mode IN ('anonymous', 'identified'))
        """,
        "ALTER TABLE share_links DROP COLUMN access_mode",
    ),
    step(
        """
        ALTER TABLE share_links
        ADD COLUMN bound_email_normalized TEXT NULL
        """,
        "ALTER TABLE share_links DROP COLUMN bound_email_normalized",
    ),
    step(
        """
        ALTER TABLE visitor_sessions
        ADD COLUMN external_party_id TEXT NULL REFERENCES external_parties(id) ON DELETE SET NULL
        """,
        "ALTER TABLE visitor_sessions DROP COLUMN external_party_id",
    ),
    step(
        """
        ALTER TABLE visitor_sessions
        ADD COLUMN external_access_grant_id TEXT NULL REFERENCES external_access_grants(id) ON DELETE SET NULL
        """,
        "ALTER TABLE visitor_sessions DROP COLUMN external_access_grant_id",
    ),
    step(
        """
        ALTER TABLE visitor_sessions
        ADD COLUMN presented_email TEXT NULL
        """,
        "ALTER TABLE visitor_sessions DROP COLUMN presented_email",
    ),
    step(
        """
        ALTER TABLE visitor_sessions
        ADD COLUMN identity_source TEXT NULL
        CHECK (identity_source IN ('link_email', 'manual_entry', 'bound_party_email'))
        """,
        "ALTER TABLE visitor_sessions DROP COLUMN identity_source",
    ),
]
