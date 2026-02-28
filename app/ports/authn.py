from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Optional, Mapping


@dataclass(frozen=True)
class Principal:
    # Identity
    tenant_id: str
    subject: str
    user_id: Optional[str]
    client_id: Optional[str]
    token_use: Optional[str]

    # Authorization
    roles: tuple[str, ...]
    scopes: tuple[str, ...]
    policy: Mapping[str, Any]

    # Token metadata (for audit + caching + revocation)
    jti: Optional[str]
    issued_at: Optional[int]  # iat (unix seconds)
    expires_at: Optional[int] # exp (unix seconds)
    issuer: Optional[str]
    audience: Optional[str]

    claims: Optional[Mapping[str, Any]]

class AuthenticatorPort(ABC):
    @abstractmethod
    async def authenticate(self, bearer_token: str) -> Principal:
        raise NotImplementedError