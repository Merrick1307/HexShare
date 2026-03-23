#!/bin/sh
set -e

poetry run python -m run_migrations apply

poetry run python -m app.main

