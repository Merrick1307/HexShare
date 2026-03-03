from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Mapping, Any


class FlowStatePort(ABC):
    @abstractmethod
    def seal(self, payload: Mapping[str, Any], *, ttl_seconds: int) -> str: ...

    @abstractmethod
    def unseal(self, token: str) -> dict[str, Any]: ...