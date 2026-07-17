"""Policy loader that loads rate limit policies from database."""
from __future__ import annotations

import logging
from typing import Dict

from app.adapters.rate_limiting.base import RateLimitPolicy
from app.ports.storage_port import StoragePort

logger = logging.getLogger(__name__)


class PolicyLoader:
    """Load rate limit policies from database with caching."""

    def __init__(
        self,
        storage: StoragePort,
        cache_ttl_seconds: int = 300,
    ):
        """Initialize policy loader.
        
        Parameters
        ----------
        storage:
            Storage adapter for fetching policies.
        cache_ttl_seconds:
            How long to cache policies (seconds). Default 5 minutes.
        """
        self.storage = storage
        self.cache_ttl_seconds = cache_ttl_seconds
        self._cache: Dict[str, tuple[Dict[str, RateLimitPolicy], int]] = {}

    async def get_policies(self, tier: str) -> Dict[str, RateLimitPolicy]:
        """Get rate limit policies for a tier.
        
        Loads from cache if available, otherwise fetches from database.
        
        Parameters
        ----------
        tier:
            Subscription tier (free, pro, enterprise, etc).
        
        Returns
        -------
        Dict[str, RateLimitPolicy]
            Mapping of policy names to configurations.
        """
        import time
        now = int(time.time())
        
        # Check cache
        if tier in self._cache:
            policies, cached_at = self._cache[tier]
            if now - cached_at < self.cache_ttl_seconds:
                return policies

        # Load from database
        try:
            policies_rows = await self.storage.list_rate_limit_policies(tier=tier)
        except Exception as e:
            logger.error(f"Failed to load rate limit policies for tier {tier}: {e}")
            # Return default permissive policies on error
            return {
                "api_general": RateLimitPolicy("api_general", 10000, 3600),
                "document_upload": RateLimitPolicy("document_upload", 1000, 3600),
                "share_link": RateLimitPolicy("share_link", 1000, 3600),
                "nda_create": RateLimitPolicy("nda_create", 1000, 3600),
            }

        policies = {
            row["policy_name"]: RateLimitPolicy(
                name=row["policy_name"],
                limit=row["limit_count"],
                window_seconds=row["window_seconds"],
            )
            for row in policies_rows
        }

        # Cache the policies
        self._cache[tier] = (policies, now)

        logger.debug(f"Loaded {len(policies)} rate limit policies for tier {tier}")
        return policies

    async def invalidate_cache(self, tier: str = None) -> None:
        """Invalidate policy cache.
        
        Parameters
        ----------
        tier:
            Specific tier to invalidate. If None, clear all cache.
        """
        if tier:
            self._cache.pop(tier, None)
            logger.debug(f"Invalidated cache for tier {tier}")
        else:
            self._cache.clear()
            logger.debug("Cleared all policy cache")
