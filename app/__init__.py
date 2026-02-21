"""
HexShare package initialization.

This package contains the core modules for the HexShare document sharing
platform.  HexShare is designed as an API‑first document sharing service
built on top of HexIAM for tenant and user authentication.  It
provides multi‑tenant document storage, secure link generation with
fine‑grained permissions, instant revocation, and audit logging.

The modules are organised following a ports‑and‑adapters (hexagonal)
architecture.  Domain models live in :mod:`app.domain`, use cases
live in :mod:`app.services`, interfaces (ports) are defined in
``app.ports`` and concrete infrastructure implementations live in
``app.adapters``.  The API layer and application wiring can be
found under :mod:`app.api` and :mod:`app.main`.

Note: this package intentionally omits dependency management files like
``pyproject.toml`` because it is meant to be used within an existing
Poetry environment as requested.
"""

__all__ = [
    "create_app",
]

from app.main import create_app  # noqa: E402,F401
