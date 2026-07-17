"""Rate limiting module."""
from __future__ import annotations

from app.adapters.rate_limiting.base import (
    RateLimitBackend,
    RateLimitPolicy,
    RateLimitResult,
)
from app.adapters.rate_limiting.limiter import RateLimiter
from app.adapters.rate_limiting.policy_loader import PolicyLoader
from app.adapters.rate_limiting.dependencies import rate_limit
from app.adapters.rate_limiting.backends import (
    InMemoryRateLimitBackend,
    PostgresRateLimitBackend,
    RedisRateLimitBackend,
)

__all__ = [
    "RateLimitBackend",
    "RateLimitPolicy",
    "RateLimitResult",
    "RateLimiter",
    "PolicyLoader",
    "rate_limit",
    "InMemoryRateLimitBackend",
    "PostgresRateLimitBackend",
    "RedisRateLimitBackend",
]
