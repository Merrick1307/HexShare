"""Rate limiter implementation."""
from __future__ import annotations

import logging
import time
from typing import Dict

from app.adapters.rate_limiting.base import (
    RateLimitBackend,
    RateLimitPolicy,
    RateLimitResult,
)

logger = logging.getLogger(__name__)


class RateLimiter:
    """Core rate limiter with pluggable backend and policies."""

    def __init__(
        self,
        backend: RateLimitBackend,
        policies: Dict[str, RateLimitPolicy],
        *,
        namespace: str = "hexshare:rl",
        fail_open: bool = True,
    ):
        """Initialize rate limiter.
        
        Parameters
        ----------
        backend:
            Backend implementation (Redis, Postgres, etc).
        policies:
            Mapping of policy names to configurations.
        namespace:
            Prefix for all keys to avoid collisions.
        fail_open:
            If True, allow requests if backend fails. If False, deny.
        """
        self.backend = backend
        self.policies = policies
        self.namespace = namespace
        self.fail_open = fail_open

    async def check(self, policy_name: str, subject: str) -> RateLimitResult:
        """Check if request is within rate limit.
        
        Parameters
        ----------
        policy_name:
            Name of the policy to check against.
        subject:
            Unique identifier for the subject (user, tenant, IP, etc).
        
        Returns
        -------
        RateLimitResult
            Result of the rate limit check.
            
        Raises
        ------
        KeyError
            If policy_name not found in policies.
        """
        policy = self.policies[policy_name]
        now = int(time.time())
        
        # Calculate window boundaries
        window_start = now - (now % policy.window_seconds)
        reset_at = window_start + policy.window_seconds
        ttl = max(1, reset_at - now)
        
        # Build unique key
        key = f"{self.namespace}:{policy.name}:{subject}:{window_start}"

        try:
            count = await self.backend.increase_with_ttl(key, ttl)
        except Exception as e:
            logger.exception(f"Rate limit backend error: {e}")
            
            if not self.fail_open:
                raise
            
            # Fail open: allow the request but log it
            logger.warning(
                "Rate limit backend failed, allowing request. "
                "policy=%s subject=%s",
                policy.name,
                subject,
            )
            return RateLimitResult(
                allowed=True,
                limit=policy.limit,
                remaining=policy.limit,
                reset_at=reset_at,
                retry_after=0,
                policy=policy.name,
            )

        allowed = count <= policy.limit
        remaining = max(0, policy.limit - count)
        retry_after = 0 if allowed else ttl

        return RateLimitResult(
            allowed=allowed,
            limit=policy.limit,
            remaining=remaining,
            reset_at=reset_at,
            retry_after=retry_after,
            policy=policy.name,
        )
