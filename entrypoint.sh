#!/bin/sh
set -e

poetry run python -m run_migrations apply

poetry run uvicorn app.main:create_app --factory --host 0.0.0.0 --port 8000 --workers "${HEXSHARE_API_WORKERS:-2}"

