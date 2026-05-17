#!/usr/bin/env python3
"""
Run Yoyo migrations.

Supports both styles of DATABASE_URL:

1) Full DSN
   DATABASE_URL=postgresql://postgres:postgres@db:5432/postgres

2) Host-style value + component vars
   DATABASE_URL=postgres:5432/hexalgon-iam
   DATABASE_USER=app_user
   DATABASE_PASSWORD=secret
   DATABASE_NAME=hexalgon-iam

Examples:
    python run_migrations.py apply
    python run_migrations.py rollback -n 1
    python run_migrations.py list
    python run_migrations.py status

Optional:
    python run_migrations.py apply --migrations-path ./migrations
    python run_migrations.py apply --database-url postgresql://user:pass@host:5432/db
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from urllib.parse import quote_plus, urlsplit, urlunsplit

from yoyo import get_backend, read_migrations

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None


def load_env() -> None:
    if load_dotenv:
        load_dotenv()


def mask_database_url(db_url: str) -> str:
    """
    Hide password in printed DB URL.
    """
    try:
        parts = urlsplit(db_url)
        hostname = parts.hostname or ""
        port = f":{parts.port}" if parts.port else ""
        username = parts.username or ""
        if username:
            netloc = f"{username}:***@{hostname}{port}"
        else:
            netloc = f"{hostname}{port}"
        return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))
    except Exception:
        return "<unprintable database url>"


def build_database_url_from_components(raw_database_url: str) -> str:
    """
    Build a full PostgreSQL DSN from env vars when DATABASE_URL is not already a full DSN.

    Supported raw values:
        postgres:5432/hexalgon-iam
        db:5432/postgres
        postgres:5432
    """
    user = os.getenv("DATABASE_USER")
    password = os.getenv("DATABASE_PASSWORD", "")
    database_name = os.getenv("DATABASE_NAME")

    if not user:
        raise RuntimeError("DATABASE_USER is required when DATABASE_URL is not a full DSN")

    raw = raw_database_url.strip()

    if "/" in raw:
        host_port, db_from_url = raw.split("/", 1)
        db_name = db_from_url or database_name
    else:
        host_port = raw
        db_name = database_name

    if not db_name:
        raise RuntimeError(
            "DATABASE_NAME is required when DATABASE_URL does not include a database name"
        )

    if password:
        return f"postgresql://{user}:{quote_plus(password)}@{host_port}/{db_name}"
    return f"postgresql://{user}@{host_port}/{db_name}"


def get_database_url(override: str | None = None) -> str:
    """
    Resolve the final DB URL.
    """
    load_env()

    if override:
        return override.strip()

    database_url = (os.getenv("DATABASE_URL") or "").strip()
    if not database_url:
        raise RuntimeError("DATABASE_URL is required")

    if database_url.startswith(("postgresql://", "postgres://")):
        return database_url

    return build_database_url_from_components(database_url)


def get_default_migrations_path() -> Path:
    """
    Expect migrations/ at project root beside this script.
    """
    return Path(__file__).resolve().parent / "migrations"


def get_migrations_path(override: str | None = None) -> Path:
    path = Path(override).resolve() if override else get_default_migrations_path()
    if not path.exists():
        raise RuntimeError(f"Migrations path does not exist: {path}")
    if not path.is_dir():
        raise RuntimeError(f"Migrations path is not a directory: {path}")
    return path


def init_backend_and_migrations(db_url: str, migrations_path: Path):
    backend = get_backend(db_url)
    migrations = read_migrations(str(migrations_path))
    return backend, migrations


def apply_migrations(backend, migrations) -> int:
    pending = backend.to_apply(migrations)
    pending_list = list(pending)
    if not pending_list:
        print("No pending migrations.")
        return 0

    print(f"Applying {len(pending_list)} migration(s):")
    for migration in pending_list:
        print(f"  -> {migration.id}")

    with backend.lock():
        backend.apply_migrations(pending)

    print("Migrations applied successfully.")
    return 0


def rollback_migrations(backend, migrations, count: int) -> int:
    if count < 1:
        raise RuntimeError("--count must be at least 1")

    applied = backend.to_rollback(migrations)
    applied_list = list(applied)
    if not applied_list:
        print("No applied migrations to roll back.")
        return 0

    to_rollback = applied_list[:count]

    print(f"Rolling back {len(to_rollback)} migration(s):")
    for migration in to_rollback:
        print(f"  <- {migration.id}")

    with backend.lock():
        backend.rollback_migrations(to_rollback)

    print("Rollback completed successfully.")
    return 0


def list_migrations(backend, migrations) -> int:
    applied_ids = {m.id for m in backend.to_rollback(migrations)}
    pending_ids = {m.id for m in backend.to_apply(migrations)}

    print("Migrations")
    print("-" * 80)

    all_migrations = sorted(migrations, key=lambda m: m.id)
    for migration in all_migrations:
        if migration.id in applied_ids:
            status = "applied"
        elif migration.id in pending_ids:
            status = "pending"
        else:
            status = "unknown"
        print(f"{status:10} {migration.id}")

    print("-" * 80)
    print(
        f"Total: {len(all_migrations)} | "
        f"Applied: {len(applied_ids)} | "
        f"Pending: {len(pending_ids)}"
    )
    return 0


def show_status(backend, migrations) -> int:
    pending = backend.to_apply(migrations)  # not list(...)
    applied = backend.to_rollback(migrations)  # not list(...)

    print(f"Applied migrations: {len(applied)}")
    print(f"Pending migrations: {len(pending)}")

    if pending:
        print("\nNext pending migrations:")
        for migration in pending[:10]:
            print(f"  - {migration.id}")

    if applied:
        print("\nMost recently applied migrations:")
        for migration in applied[:10]:
            print(f"  - {migration.id}")

    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Yoyo migration runner")
    parser.add_argument(
        "command",
        choices=["apply", "rollback", "list", "status"],
        help="Migration command to run",
    )
    parser.add_argument(
        "-n",
        "--count",
        type=int,
        default=1,
        help="Number of migrations to rollback",
    )
    parser.add_argument(
        "--database-url",
        help="Override DATABASE_URL with a full DSN or raw host-style value",
    )
    parser.add_argument(
        "--migrations-path",
        help="Override migrations directory path",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    try:
        db_url = get_database_url(args.database_url)
        migrations_path = get_migrations_path(args.migrations_path)

        print(f"Database: {mask_database_url(db_url)}")
        print(f"Migrations path: {migrations_path}")

        backend, migrations = init_backend_and_migrations(db_url, migrations_path)

        match args.command:
            case "apply":
                return apply_migrations(backend, migrations)

            case "rollback":
                return rollback_migrations(backend, migrations, args.count)

            case "list":
                return list_migrations(backend, migrations)

            case "status":
                return show_status(backend, migrations)

            case _:
                print(f"Unknown command: {args.command}", file=sys.stderr)
                return 1

    except Exception as exc:
        print(f"Migration runner failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
