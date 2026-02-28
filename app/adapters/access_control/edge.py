from __future__ import annotations
from typing import Any, Mapping, Optional

from app.infra.factories import AccessControlFactory
from app.ports.access_control import AccessControlPort, AccessDenied, ResourceCtx
from app.ports.authn import AuthenticatorPort, Principal
from app.ports.authz import AuthorizerPort


class EdgeAccessControl(AccessControlPort):
    def __init__(self, authenticator: AuthenticatorPort, authorizer: AuthorizerPort) -> None:
        self.authenticator = authenticator
        self.authorizer = authorizer

    async def authorize(self, *, bearer_token: str, action: str, resource: Optional[ResourceCtx] = None,
                        context: Optional[Mapping[str, Any]] = None) -> Principal:
        principal = await self.authenticator.authenticate(bearer_token)
        await self.authorizer.authorize(
            principal,
            action=action,
            resource_id=resource.id,
            context=context,
        )
        return principal


@AccessControlFactory.register("edge")
def create_edge_access_control(authenticator: AuthenticatorPort, authorizer: AuthorizerPort) -> AccessControlPort:
    return EdgeAccessControl(authenticator, authorizer)