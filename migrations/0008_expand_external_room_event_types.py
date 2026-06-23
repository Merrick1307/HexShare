from yoyo import step

__depends__ = {"0007_add_external_room_sessions"}

steps = [
    step(
        """
        DO $$
        DECLARE
            constraint_name text;
        BEGIN
            SELECT con.conname
            INTO constraint_name
            FROM pg_constraint con
            JOIN pg_class rel ON rel.oid = con.conrelid
            WHERE rel.relname = 'external_room_events'
              AND con.contype = 'c'
              AND pg_get_constraintdef(con.oid) LIKE '%event_type%';

            IF constraint_name IS NOT NULL THEN
                EXECUTE format(
                    'ALTER TABLE external_room_events DROP CONSTRAINT %I',
                    constraint_name
                );
            END IF;

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
            );
        END $$;
        """,
        """
        ALTER TABLE external_room_events
        DROP CONSTRAINT IF EXISTS external_room_events_event_type_check;

        ALTER TABLE external_room_events
        ADD CONSTRAINT external_room_events_event_type_check
        CHECK (
            event_type IN (
                'room_open',
                'document_list',
                'document_download',
                'room_close'
            )
        );
        """,
    ),
]
