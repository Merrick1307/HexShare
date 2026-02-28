from abc import ABC, abstractmethod
from typing import Any

from app.ports.authn import Principal


class AuthorizationError(Exception): ...

class AuthorizerPort(ABC):
    @abstractmethod
    async def authorize(
        self,
        principal: Principal,
        action: str,
        *,
        resource_id: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> None: ...