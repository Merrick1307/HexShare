# Changelog

All notable changes to HexShare will be documented in this file.

The project is currently best versioned as `0.1.0`: the core document-sharing workflow is real and usable, but there are still clear pre-1.0 gaps around operator automation, broader identity workflows, and release hardening.

## [0.1.0] - 2026-05-19

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
