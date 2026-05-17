from __future__ import annotations

import asyncio
import time
from collections import OrderedDict

from app.infra.factories import RenderedPageCacheFactory
from app.ports.rendered_page_cache_port import RenderedPageCachePort
from app.services.document_processor import RenderedPage


class InMemoryRenderedPageCache(RenderedPageCachePort):
    def __init__(self, *, maxsize: int = 200, ttl_seconds: float = 120.0) -> None:
        self._cache: OrderedDict[str, tuple[RenderedPage, float]] = OrderedDict()
        self._maxsize = maxsize
        self._ttl_seconds = ttl_seconds
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> RenderedPage | None:
        async with self._lock:
            now = time.monotonic()
            entry = self._cache.get(key)
            if entry is None:
                return None
            value, expires_at = entry
            if now >= expires_at:
                del self._cache[key]
                return None
            self._cache.move_to_end(key)
            return value

    async def set(self, key: str, value: RenderedPage) -> None:
        async with self._lock:
            self._cache[key] = (value, time.monotonic() + self._ttl_seconds)
            self._cache.move_to_end(key)
            while len(self._cache) > self._maxsize:
                self._cache.popitem(last=False)


@RenderedPageCacheFactory.register("inmemory")
@RenderedPageCacheFactory.register("memory")
def create_in_memory_rendered_page_cache(**kwargs) -> RenderedPageCachePort:
    return InMemoryRenderedPageCache(**kwargs)

