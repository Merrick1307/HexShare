# HexShare

HexShare is a self-hostable document sharing application for teams that need tighter control over sensitive files. It combines document uploads, group-based organization, protected share links, a session-aware viewer, and view analytics in a FastAPI + React stack.

## What is in the project today

- Document uploads with S3-compatible object storage targets
- Document groups with IAM-backed membership and policy assignment
- Protected share links with expiry, download/print controls, email gates, and JTI revocation
- Viewer sessions for protected delivery, page views, and activity inspection
- Analytics for document engagement
- OIDC login flow with HexIAM and Google client adapters
- Local session issuance mode backed by OIDC user info
- Redis-backed rendered page cache, ARQ worker support, and Redis-backed share-token revocation

## Stack

- Backend: FastAPI, asyncpg, PyJWT
- Frontend: React, TypeScript, Vite, Tailwind CSS
- Metadata store: PostgreSQL
- Object storage: S3-compatible storage, Cloudflare R2, or Cloudinary
- Cache/queue: Redis
- Optional IAM / OIDC provider: HexIAM

## Authentication and access modes

HexShare is wired around ports and adapter selection through environment variables.

- `HEXSHARE_AUTHENTICATOR=hexiam`: verify and trust HexIAM-issued tokens directly
- `HEXSHARE_AUTHENTICATOR=local`: mint local HexShare session tokens after an upstream OIDC login
- `HEXSHARE_DEFAULT_OIDC_IDP=hexiam|google`: choose the default browser login provider
- `HEXSHARE_ACCESS_CONTROL=edge|hybrid|pdp`: choose where authorization decisions are enforced
- `HEXSHARE_SHARE_TOKEN_REVOCATION_STORE=memory|redis`: choose how share-link JTIs are revoked

## Local development

1. Copy `.env.example` to `.env` and fill in the values you need.
2. Install backend dependencies:

```bash
poetry install
```

3. Start the default local stack:

```bash
docker compose up --build
```

4. Start the frontend dev server when you want hot reload instead of the built frontend image:

```bash
cd frontend
npm install
npm run dev
```

Default local endpoints:

- HexShare API: `http://localhost:8099`
- HexShare frontend container: `http://localhost:3000`
- HexShare frontend dev server: `http://localhost:3003`
- MinIO API: `http://localhost:9000`
- MinIO console: `http://localhost:9001`

## Self-hosting

Use the bundled guide in [SELF_HOST.md](SELF_HOST.md). The repo now includes:

- `docker-compose.with-hexiam.yaml`: compose overlay for running HexShare and HexIAM together
- `scripts/prepare_hexiam.py`: clone or refresh HexIAM into `.hexiam/hexalgon-iam-system`
- `hexiam.env.bundle.example`: bundle env template copied into the local HexIAM checkout

Typical bundle flow:

```bash
python scripts/prepare_hexiam.py
docker compose -f docker-compose.yaml -f docker-compose.with-hexiam.yaml up -d --build
```

## Project references

- Architecture and runtime layout: [ARCHITECTURE.md](ARCHITECTURE.md)
- Self-hosting steps: [SELF_HOST.md](SELF_HOST.md)
- Change history: [CHANGELOG.md](CHANGELOG.md)
- License: [LICENSE.md](LICENSE.md)
- Contributing guide: [CONTRIBUTING.md](CONTRIBUTING.md)
- Security policy: [SECURITY.md](SECURITY.md)

## Notes

- The protected page viewer is centered on the document-processing pipeline and rendered-page cache.
- Share-link revocation is in-memory by default outside Docker, and Redis-backed in the Docker deployment profiles.
- HexIAM client bootstrap is still manual; the new bundle flow prepares the repo and runtime wiring, but it does not create OIDC clients for you.
