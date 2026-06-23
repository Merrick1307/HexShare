# Changelog

All notable changes to HexShare will be documented in this file.

The project is currently best versioned as `0.2.0`: the core document-sharing workflow is real and usable and now includes a first-class external-recipient identity layer, but there are still clear pre-1.0 gaps around operator automation, broader identity workflows, and release hardening.

## [0.2.0] - 2026-06-23

### Added

- External-party identity model: named external recipients keyed by normalized email, with active/revoked/archived/blocked status
- External access grants scoped to a document or a document group (room), carrying download/print permissions and optional expiry, revocable independently of the recipient
- External data rooms: provision, list, and revoke room access for named recipients over a document group
- Invite-to-session flow for external recipients: invite token exchanged for short-lived access and refresh session tokens (JWT), re-validated against live grant state on every request
- Identified share links: a link can be bound to a single recipient email, auto-provisioning the external party and access grant behind it
- Room viewer with watermarked, session-bound page streaming and per-interaction audit events (room open/close, document list/open/page-view/close/download)
- Per-recipient external-room activity folded into document engagement analytics
- External-room invitation and viewer frontend pages, plus room-access management in the group and document views
- `/external-room/*` API surface and `external_room_auth` bearer/cookie authentication for external principals
- Storage adapters (in-memory and Postgres) for external parties, emails, grants, room sessions, and room events
- Migrations 0006–0009 for external-party identity, room sessions, expanded event types, and page-view fields

### Configuration

- `HEXSHARE_JWT_SECRET` is now required to enable external rooms (signs invite and session tokens)
- New optional token-lifetime variables: `HEXSHARE_EXTERNAL_ROOM_ACCESS_TTL_SECONDS`, `HEXSHARE_EXTERNAL_ROOM_REFRESH_TTL_SECONDS`, `HEXSHARE_EXTERNAL_ROOM_INVITE_TTL_SECONDS`

## [0.1.0] - 2026-05-20

### Added

- OIDC browser login flow with PKCE-based callback handling
- Local HexShare session mode derived from upstream OIDC user info
- Document upload initiation and completion flow with presigned object-storage uploads
- Document groups and membership management
- IAM-backed document-group policy coordination
- Protected share links with expiry, download/print flags, and optional email gating
- Secure viewer sessions, page-view tracking, and session close handling
- PDF page rendering with watermarking
- Rendered-page caching and background prerender worker support
- Redis-backed share-token JTI revocation support
- Docker Compose support for the main HexShare stack
- Bundled HexIAM self-hosting overlay and bootstrap script
- Initial architecture, self-hosting, and operator documentation
