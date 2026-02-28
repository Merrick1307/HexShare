from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Mapping, Optional

from app.ports.authn import Principal


class AccessDenied(Exception):
    pass


@dataclass(frozen=True)
class ResourceCtx:
    type: str
    id: Optional[str] = None
    attrs: Mapping[str, Any] = None


class AccessControlPort(ABC):
    @abstractmethod
    async def authorize(
        self,
        *,
        bearer_token: str,
        action: str,
        resource: Optional[ResourceCtx] = None,
        context: Optional[Mapping[str, Any]] = None,
    ) -> Principal:
        """
        Returns Principal if allowed, raises AccessDenied otherwise.
        Encapsulates authn/authz strategy (edge vs pdp).
        """
        raise NotImplementedError