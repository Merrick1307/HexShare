from yoyo import step

__depends__ = {"0004_add_document_groups_and_permissions"}

steps = [
    step(
        """
        CREATE TABLE local_users (
            tenant_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            email TEXT NULL,
            name TEXT NULL,
            auth_provider TEXT NOT NULL,
            provider_subject TEXT NOT NULL,
            created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
            last_login_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
            PRIMARY KEY (tenant_id, user_id)
        )
        """,
        "DROP TABLE local_users",
    ),
    step(
        "CREATE UNIQUE INDEX local_users_tenant_provider_subject_idx ON local_users (tenant_id, provider_subject)",
        "DROP INDEX local_users_tenant_provider_subject_idx",
    ),
    step(
        "CREATE INDEX local_users_tenant_email_idx ON local_users (tenant_id, email)",
        "DROP INDEX local_users_tenant_email_idx",
    ),
    step(
        """
        CREATE TABLE document_group_memberships (
            group_id TEXT NOT NULL,
            tenant_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            permissions INTEGER NOT NULL DEFAULT 0 CHECK (permissions >= 0),
            granted_by TEXT NOT NULL,
            granted_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
            PRIMARY KEY (group_id, user_id)
        )
        """,
        "DROP TABLE document_group_memberships",
    ),
    step(
        "CREATE INDEX document_group_memberships_tenant_user_idx ON document_group_memberships (tenant_id, user_id)",
        "DROP INDEX document_group_memberships_tenant_user_idx",
    ),
    step(
        "CREATE INDEX document_group_memberships_group_idx ON document_group_memberships (group_id)",
        "DROP INDEX document_group_memberships_group_idx",
    ),
]
