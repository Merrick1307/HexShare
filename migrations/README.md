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

## Run

From the project root:

```bash
yoyo apply --database "$DATABASE_URL" migrations
```

Or, if your config already points at the `migrations/` directory:

```bash
yoyo apply
```
