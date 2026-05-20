# Contributing to HexShare

Thanks for contributing. Keep changes narrow, reviewable, and consistent with the existing FastAPI and React structure in this repo.

## Before you open a pull request

1. Open an issue or discussion first for behavior changes, new adapters, or deployment model changes.
2. Work from a feature or fix branch off the current default branch.
3. Keep unrelated refactors out of the same branch.
4. Add or update tests when you change authentication, sharing, viewer, or document-processing behavior.
5. Update `README.md`, `ARCHITECTURE.md`, `SELF_HOST.md`, or `CHANGELOG.md` when the operational or public behavior changes.

## Local setup

1. Copy `.env.example` to `.env`.
2. Install backend dependencies with `poetry install`.
3. Install frontend dependencies with `cd frontend && npm install`.
4. Start the stack with `docker compose up --build`, or use the frontend dev server with `npm run dev` inside `frontend/`.

## Development expectations

- Follow the existing adapter and service boundaries.
- Prefer small commits with one concern each.
- Keep secrets, local `.env` files, generated bundles, and `.hexiam/` content out of commits.
- Add focused tests for new auth, token, and policy behavior.
- Document any new environment variables.

## Pull request checklist

- Code builds and relevant tests pass locally.
- New environment variables are reflected in `.env.example`.
- User-facing and operator-facing docs are updated where needed.
- Security-sensitive behavior changes include threat or tradeoff notes in the PR description.

## Reporting concerns in contributions

Do not open public issues for unpatched security vulnerabilities. Use the process in `security.md`.
