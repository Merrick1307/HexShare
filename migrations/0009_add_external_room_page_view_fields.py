from yoyo import step

__depends__ = {"0008_expand_external_room_event_types"}

steps = [
    step(
        """
        ALTER TABLE external_room_events
        ADD COLUMN page_number INTEGER NULL
        """,
        "ALTER TABLE external_room_events DROP COLUMN page_number",
    ),
    step(
        """
        ALTER TABLE external_room_events
        ADD COLUMN duration_ms INTEGER NULL
        """,
        "ALTER TABLE external_room_events DROP COLUMN duration_ms",
    ),
    step(
        """
        ALTER TABLE external_room_events
        DROP CONSTRAINT IF EXISTS external_room_events_event_type_check
        """,
        """
        ALTER TABLE external_room_events
        DROP CONSTRAINT IF EXISTS external_room_events_event_type_check
        """,
    ),
    step(
        """
        ALTER TABLE external_room_events
        ADD CONSTRAINT external_room_events_event_type_check
        CHECK (
            event_type IN (
                'room_open',
                'document_list',
                'document_view_open',
                'document_page_view',
                'document_view_close',
                'document_download',
                'room_close'
            )
        )
        """,
        """
        ALTER TABLE external_room_events
        ADD CONSTRAINT external_room_events_event_type_check
        CHECK (
            event_type IN (
                'room_open',
                'document_list',
                'document_view_open',
                'document_view_close',
                'document_download',
                'room_close'
            )
        )
        """,
    ),
]
