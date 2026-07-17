"""Add rate limiting policies and counters."""

from yoyo import step

__depends__ = {"0010_add_nda_policies_and_acceptances"}

steps = [
    step(
        """
        CREATE TABLE rate_limit_policies (
            id TEXT PRIMARY KEY DEFAULT ('rlp_' || gen_random_uuid()::text),
            tier TEXT NOT NULL,
            policy_name TEXT NOT NULL,
            limit_count INTEGER NOT NULL CHECK (limit_count >= 0),
            window_seconds INTEGER NOT NULL CHECK (window_seconds > 0),
            enabled BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (tier, policy_name)
        );

        CREATE INDEX idx_rate_limit_policies_tier
            ON rate_limit_policies (tier);
        CREATE INDEX idx_rate_limit_policies_enabled
            ON rate_limit_policies (enabled);

        CREATE TABLE rate_limit_policy_changes (
            id TEXT PRIMARY KEY DEFAULT ('rlpc_' || gen_random_uuid()::text),
            policy_id TEXT REFERENCES rate_limit_policies(id) ON DELETE SET NULL,
            old_limit_count INTEGER,
            new_limit_count INTEGER,
            old_window_seconds INTEGER,
            new_window_seconds INTEGER,
            changed_by TEXT,
            changed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );

        CREATE INDEX idx_rate_limit_policy_changes_policy_id
            ON rate_limit_policy_changes (policy_id);
        CREATE INDEX idx_rate_limit_policy_changes_changed_at
            ON rate_limit_policy_changes (changed_at);

        CREATE TABLE rate_limit_counters (
            key TEXT PRIMARY KEY,
            count INTEGER NOT NULL DEFAULT 0,
            expires_at TIMESTAMPTZ NOT NULL
        );

        CREATE INDEX idx_rate_limit_counters_expires_at
            ON rate_limit_counters (expires_at);

        INSERT INTO rate_limit_policies (tier, policy_name, limit_count, window_seconds, enabled)
        VALUES
            ('free', 'api_general', 100, 3600, TRUE),
            ('free', 'document_upload', 5, 3600, TRUE),
            ('free', 'share_link', 10, 3600, TRUE),
            ('free', 'nda_create', 3, 3600, TRUE),
            ('pro', 'api_general', 1000, 3600, TRUE),
            ('pro', 'document_upload', 100, 3600, TRUE),
            ('pro', 'share_link', 500, 3600, TRUE),
            ('pro', 'nda_create', 50, 3600, TRUE),
            ('enterprise', 'api_general', 1000000, 3600, TRUE),
            ('enterprise', 'document_upload', 1000000, 3600, TRUE),
            ('enterprise', 'share_link', 1000000, 3600, TRUE),
            ('enterprise', 'nda_create', 1000000, 3600, TRUE)
        ON CONFLICT (tier, policy_name) DO NOTHING;
        """,
        """
        DROP TABLE IF EXISTS rate_limit_counters;
        DROP TABLE IF EXISTS rate_limit_policy_changes;
        DROP TABLE IF EXISTS rate_limit_policies;
        """,
    )
]
