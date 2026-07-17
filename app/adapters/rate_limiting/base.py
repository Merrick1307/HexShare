"""Rate limiting base classes and interfaces."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True, slots=True)
class RateLimitPolicy:
    """Rate limit policy configuration."""
    
    name: str
    limit: int
    window_seconds: int


@dataclass(frozen=True, slots=True)
class RateLimitResult:
    """Result of a rate limit check."""
    
    allowed: bool
    limit: int
    remaining: int
    reset_at: int
    retry_after: int
    policy: str


class RateLimitBackend(ABC):
    """Abstract base class for rate limit backends.
    
    Backends must implement atomic increment-with-TTL operation
    to avoid race conditions and unbounded memory growth.
    """

    @abstractmethod
    async def increase_with_ttl(self, key: str, ttl_seconds: int) -> int:
        """Increment counter for key and set TTL if new.
        
        Parameters
        ----------
        key:
            Unique identifier for the rate limit bucket.
        ttl_seconds:
            How many seconds until the counter expires. Only set
            if the key is new; do not overwrite existing TTL.
        
        Returns
        -------
        int
            The new counter value after incrementing.
        """
        ...
