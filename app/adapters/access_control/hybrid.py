from __future__ import annotations
from typing import Mapping, Optional

from app.adapters.access_control.edge import EdgeAccessControl
from app.adapters.access_control.pdp import create_pdp_access_control
from app.infra.factories import AccessControlFactory
from app.ports.access_control import AccessControlPort, AccessDenied, ResourceCtx
from app.ports.authn import Principal, AuthenticatorPort
from app.ports.authz import AuthorizerPort


class HybridAccessControl(AccessControlPort):
    """
    Strategy:
    - Try EDGE
    - If token missing embedded policy OR edge fails -> fallback PDP
    """

    def __init__(self, *, edge: AccessControlPort, pdp: AccessControlPort) -> None:
        self.edge = edge
        self.pdp = pdp

    async def authorize(self, *, bearer_token: str, action: str, resource: Optional[ResourceCtx] = None,
                        context: Optional[Mapping[str, object]] = None) -> Principal:
        try:
            principal = await self.edge.authorize(bearer_token=bearer_token, action=action, resource=resource,
                                                  context=context)
            if not principal.policy:
                raise AccessDenied("edge_missing_policy")
            return principal
        except Exception:
            return await self.pdp.authorize(bearer_token=bearer_token, action=action, resource=resource,
                                            context=context)


@AccessControlFactory.register("hybrid")
def create_hybrid_access_control(*, authenticator: AuthenticatorPort, authorizer: AuthorizerPort, **_) -> AccessControlPort:
    edge = EdgeAccessControl(authenticator, authorizer)
    pdp = create_pdp_access_control(**_)  # ignores extras
    return HybridAccessControl(edge=edge, pdp=pdp)
