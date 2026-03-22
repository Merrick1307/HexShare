# HexShare Yoyo migrations

These migrations were derived from the current `PostgresStorage` adapter and service layer in the uploaded HexShare codebase.

## What is included

- `0001_create_hexshare_core_tables.py`
  - `documents`
  - `share_links`
  - `visitor_sessions`
  - `view_events`
- `0002_add_hexshare_indexes.py`
  - indexes aligned to the adapter's current read patterns

## Important compatibility note

The current application code does **not** use database-generated UUID primary keys yet.

It currently creates IDs in application code such as:
- `doc_<uuid4hex>`
- `link_<uuid4hex>`

Because of that, these migrations keep resource primary keys as `TEXT` so they work with the code as-is.

## About UUIDv7

You asked for UUIDv7 on UUID-related fields.

In the current HexShare codebase, there are no database-generated UUID primary keys in the Postgres adapter path yet. Adding `DEFAULT uuidv7()` to core table PKs right now would break compatibility with the existing service layer unless you also change:

- `PostgresStorage.generate_id()`
- any service code that assumes prefixed string IDs
- any domain/API expectations that currently treat these IDs as arbitrary strings

If you want, the next step should be a **follow-up refactor migration plan** that converts:

- `documents.id`
- `share_links.id`
- `visitor_sessions.id`
- `view_events.id`

from text IDs to real UUIDv7-backed IDs.

## Run

From the project root:

```bash
yoyo apply --database "$DATABASE_URL" migrations
```

Or, if your config already points at the `migrations/` directory:

```bash
yoyo apply
```
