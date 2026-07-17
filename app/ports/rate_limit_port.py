"""Rate limiting port interface.

Defines the abstract interface for rate limiting implementations.
Allows swapping different rate limiting strategies without affecting
domain logic.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class RateLimitCheckResult:
    """Result of a rate limit check."""
    
    allowed: bool
    remaining: int
    reset_at: int
    retry_after: int


class RateLimitPort(ABC):
    """Abstract interface for rate limiting services."""

    @abstractmethod
    async def check_rate_limit(
        self,
        policy_name: str,
        subject: str,
        tier: str = "free",
    ) -> RateLimitCheckResult:
        """Check if request is within rate limit.

        Parameters
        ----------
        policy_name:
            Name of the policy (e.g., "api_general").
        subject:
            Unique identifier (user ID, tenant:user, IP, etc).
        tier:
            Subscription tier for looking up policies.

        Returns
        -------
        RateLimitCheckResult
            Whether request is allowed and reset information.
        """
        ...
