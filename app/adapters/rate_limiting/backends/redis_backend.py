"""Redis rate limit backend."""
from __future__ import annotations

from redis.asyncio import Redis

from app.adapters.rate_limiting.base import RateLimitBackend


class RedisRateLimitBackend(RateLimitBackend):
    """Redis-based rate limit backend using Lua scripting.
    
    Uses atomic Lua script to increment counter and set TTL in one operation.
    High performance and suitable for distributed systems.
    """

    def __init__(self, redis: Redis):
        """Initialize with Redis connection.
        
        Parameters
        ----------
        redis:
            redis-py async client.
        """
        self.redis = redis
        self._sha: str | None = None
        self._lua = (
            "local v = redis.call('INCR', KEYS[1])\n"
            "if v == 1 then\n"
            "  redis.call('EXPIRE', KEYS[1], ARGV[1])\n"
            "end\n"
            "return v"
        )

    async def _script_sha(self) -> str:
        """Load Lua script and cache SHA."""
        if self._sha is None:
            self._sha = await self.redis.script_load(self._lua)
        return self._sha

    async def increase_with_ttl(self, key: str, ttl_seconds: int) -> int:
        """Increment counter and set TTL if new.
        
        Uses Lua script to ensure atomicity:
        1. INCR the counter
        2. If counter was 1 (new key), EXPIRE it
        """
        sha = await self._script_sha()
        try:
            # Try evalsha first (faster if script cached)
            return int(await self.redis.evalsha(sha, 1, key, ttl_seconds))
        except Exception:
            # Fallback to eval if script not cached
            return int(await self.redis.eval(self._lua, 1, key, ttl_seconds))
