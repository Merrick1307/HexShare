#!/bin/sh
set -eu

if [ "${HEXSHARE_RUN_MIGRATIONS:-0}" = "1" ]; then
  python -m run_migrations apply
fi

if [ "$#" -eq 0 ]; then
  set -- uvicorn app.main:create_app --factory --host 0.0.0.0 --port 8000 --workers "${HEXSHARE_API_WORKERS:-2}"
fi

exec "$@"
