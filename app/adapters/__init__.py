"""
Infrastructure adapters for HexShare.

Adapters implement the port interfaces defined in :mod:`app.ports`.
They provide concrete behaviours for storage, token handling and event
publishing.  The default adapters included here are intentionally
simple: an in‑memory storage for testing and examples, a JWT token
adapter using PyJWT, and a no‑op event bus.  In a real deployment
these should be replaced with production‑ready implementations (e.g.
S3 storage, Redis Streams event bus).
"""

from .jwt_token import JWTTokenAdapter
from .noop_event_bus import NoopEventBus
from .access_control import EdgeAccessControl, HybridAccessControl, PDPAccessControl
from .auth import HEXIAMAuthenticator
from .persistence import PostgresStorage, MemoryStorage
from .authz import HexIAMAuthorizer
from .object_storage import S3ObjectStorageAdapter, CloudFlareR2ObjectStorageAdapter, CloudinaryObjectStorageAdapter


__all__ = [
    "JWTTokenAdapter",
    "NoopEventBus",
    "HEXIAMAuthenticator",
    "HybridAccessControl",
    "PostgresStorage",
    "MemoryStorage",
    "HexIAMAuthorizer",
    "EdgeAccessControl",
    "PDPAccessControl",
    "S3ObjectStorageAdapter",
    "CloudFlareR2ObjectStorageAdapter",
    "CloudinaryObjectStorageAdapter"
]
