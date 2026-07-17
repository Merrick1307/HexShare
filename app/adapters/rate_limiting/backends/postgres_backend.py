"""PostgreSQL rate limit backend."""
from __future__ import annotations

import asyncpg

from app.adapters.rate_limiting.base import RateLimitBackend


class PostgresRateLimitBackend(RateLimitBackend):
    """PostgreSQL-based rate limit backend.
    
    Uses UPSERT to atomically increment counters.
    Useful as fallback when Redis unavailable.
    """

    def __init__(self, pool: asyncpg.Pool):
        """Initialize with database pool.
        
        Parameters
        ----------
        pool:
            asyncpg connection pool.
        """
        self.pool = pool

    async def increase_with_ttl(self, key: str, ttl_seconds: int) -> int:
        """Increment counter via UPSERT.
        
        Uses PostgreSQL's INSERT...ON CONFLICT to atomically:
        - Insert new counter with TTL if doesn't exist
        - Increment existing counter
        """
        count = await self.pool.fetchval(
            """
            INSERT INTO rate_limit_counters (key, count, expires_at)
            VALUES ($1, 1, NOW() + ($2 || ' seconds')::INTERVAL)
            ON CONFLICT (key) DO UPDATE
            SET
                count = CASE
                    WHEN rate_limit_counters.expires_at <= NOW() THEN 1
                    ELSE rate_limit_counters.count + 1
                END,
                expires_at = CASE
                    WHEN rate_limit_counters.expires_at <= NOW()
                    THEN NOW() + ($2 || ' seconds')::INTERVAL
                    ELSE rate_limit_counters.expires_at
                END
            RETURNING count
            """,
            key,
            ttl_seconds,
        )

        # If the key was expired, count will be 1 (reset)
        return int(count or 1)
