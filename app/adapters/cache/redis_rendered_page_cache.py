from __future__ import annotations

import os
import pickle

try:
    from redis.asyncio import Redis
except ImportError:
    Redis = None  # type: ignore

from app.infra.factories import RenderedPageCacheFactory
from app.ports.rendered_page_cache_port import RenderedPageCachePort
from app.services.document_processor import RenderedPage


class RedisRenderedPageCache(RenderedPageCachePort):
    def __init__(self, *, redis_url: str, ttl_seconds: int = 120, key_prefix: str = "hexshare:rendered-page:") -> None:
        if Redis is None:
            raise RuntimeError("redis is required for RedisRenderedPageCache")
        self._redis = Redis.from_url(redis_url, decode_responses=False)
        self._ttl_seconds = int(ttl_seconds)
        self._key_prefix = key_prefix

    def _key(self, key: str) -> str:
        return f"{self._key_prefix}{key}"

    async def get(self, key: str) -> RenderedPage | None:
        payload = await self._redis.get(self._key(key))
        if not payload:
            return None
        try:
            obj = pickle.loads(payload)
            return RenderedPage(**obj)
        except Exception:
            return None

    async def set(self, key: str, value: RenderedPage) -> None:
        payload = pickle.dumps(
            {
                "content": value.content,
                "media_type": value.media_type,
                "page_number": value.page_number,
                "total_pages": value.total_pages,
                "width": value.width,
                "height": value.height,
            }
        )
        await self._redis.set(self._key(key), payload, ex=self._ttl_seconds)


@RenderedPageCacheFactory.register("redis")
def create_redis_rendered_page_cache(**kwargs) -> RenderedPageCachePort:
    redis_url = kwargs.get("redis_url") or os.getenv("REDIS_URL")
    if not redis_url:
        raise RuntimeError("REDIS_URL is required for redis rendered page cache")
    ttl_seconds = int(kwargs.get("ttl_seconds") or os.getenv("HEXSHARE_RENDERED_PAGE_CACHE_TTL", "120"))
    key_prefix = kwargs.get("key_prefix") or os.getenv("HEXSHARE_RENDERED_PAGE_CACHE_PREFIX", "hexshare:rendered-page:")
    return RedisRenderedPageCache(redis_url=redis_url, ttl_seconds=ttl_seconds, key_prefix=key_prefix)

