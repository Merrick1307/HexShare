"""In-memory rate limit backend for development."""
from __future__ import annotations

import time
from typing import Dict, Tuple

from app.adapters.rate_limiting.base import RateLimitBackend


class InMemoryRateLimitBackend(RateLimitBackend):
    """Simple in-memory backend for development/testing.
    
    WARNING: Not suitable for production. Does not persist and
    will lose state on application restart.
    """

    def __init__(self):
        self._counters: Dict[str, Tuple[int, int]] = {}  # key -> (count, expires_at)

    async def increase_with_ttl(self, key: str, ttl_seconds: int) -> int:
        """Increment counter and set TTL if new."""
        now = int(time.time())
        expires_at = now + ttl_seconds

        if key not in self._counters:
            self._counters[key] = (1, expires_at)
            return 1

        count, existing_expires = self._counters[key]
        
        # Clean up expired keys
        if now >= existing_expires:
            self._counters[key] = (1, expires_at)
            return 1

        # Increment
        new_count = count + 1
        self._counters[key] = (new_count, existing_expires)
        return new_count

    def clear(self) -> None:
        """Clear all counters (for testing)."""
        self._counters.clear()
