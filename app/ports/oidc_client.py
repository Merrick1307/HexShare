from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, Mapping, Any


@dataclass(frozen=True)
class OIDCTokens:
    access_token: str
    token_type: str = "Bearer"
    expires_in: int = 3600
    refresh_token: Optional[str] = None
    id_token: Optional[str] = None
    scope: Optional[str] = None
    raw: Optional[Mapping[str, Any]] = None


class OIDCClientPort(ABC):
    @abstractmethod
    def build_authorize_url(
        self,
        *,
        redirect_uri: str,
        state: str,
        nonce: str,
        code_challenge: str,
        scope: str,
    ) -> str: ...

    @abstractmethod
    def build_signup_url(self, *, redirect_uri: str) -> str: ...

    @abstractmethod
    async def exchange_code(
        self,
        *,
        code: str,
        redirect_uri: str,
        code_verifier: str,
    ) -> OIDCTokens: ...

    @abstractmethod
    async def refresh(self, *, refresh_token: str) -> OIDCTokens: ...