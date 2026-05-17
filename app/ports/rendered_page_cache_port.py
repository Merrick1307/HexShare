from __future__ import annotations

from abc import ABC, abstractmethod


class RenderedPageCachePort(ABC):
    @abstractmethod
    async def get(self, key: str):
        raise NotImplementedError

    @abstractmethod
    async def set(self, key: str, value) -> None:
        raise NotImplementedError
