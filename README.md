# HexShare

HexShare is a self-hostable document sharing application for teams that need tighter control over sensitive files. It combines document uploads, group-based organization, protected share links, identified external data rooms, a session-aware viewer, and view analytics in a FastAPI + React stack.

## What is in the project today

- Document uploads with S3-compatible object storage targets
- Document groups with IAM-backed membership and policy assignment
- Protected share links with expiry, download/print controls, email gates, and JTI revocation
- Identified share links and external data rooms: named, revocable, audited access for external recipients
- Viewer sessions for protected delivery, page views, and activity inspection
- Analytics for document engagement, including per-recipient external-room activity
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

## External rooms and identified access

Beyond anonymous, email-gated links, HexShare supports a first-class identity layer for external recipients. A document or an entire document group can be shared with a *named external party* whose access is provisioned, tracked per page, and revocable at any time — turning group sharing into a lightweight virtual data room.

- **External parties**: recipients are modeled as first-class records keyed by normalized email, with active/revoked/archived/blocked status.
- **Access grants**: scoped to a document or a room (group), carrying download/print permissions and optional expiry, revocable independently of the recipient.
- **Identified share links**: a link can be bound to a single recipient email, which auto-provisions the external party and access grant behind it.
- **Invite-to-session flow**: an invite token is exchanged for short-lived access and refresh session tokens (JWT), re-validated against live grant state on every request, with refresh, logout, and revocation support.
- **Room viewer**: external recipients open documents through watermarked, session-bound page streaming, with every room and document interaction recorded as an audit event.
- **Analytics**: external-room views and page-views are folded into the existing document engagement metrics, with per-recipient attribution.

Relevant environment variables:

- `HEXSHARE_JWT_SECRET`: secret used to sign external-room invite and session tokens (required for external rooms)
- `HEXSHARE_PUBLIC_URL`: public base URL used as the token issuer and for invite links
- `HEXSHARE_AUTH_AUDIENCE`: audience claim for external-room tokens (defaults to `hexshare-external`)
- `HEXSHARE_EXTERNAL_ROOM_ACCESS_TTL_SECONDS`: external-room access-token lifetime (default `3600`)
- `HEXSHARE_EXTERNAL_ROOM_REFRESH_TTL_SECONDS`: external-room refresh-token lifetime (default 7 days)
- `HEXSHARE_EXTERNAL_ROOM_INVITE_TTL_SECONDS`: invite-token lifetime (default 7 days)

External recipients reach their rooms through the frontend invitation and viewer routes (`/external-room/invitations/:token` and `/external-room/viewer/:sessionId`), backed by the `/external-room/*` API surface.

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
