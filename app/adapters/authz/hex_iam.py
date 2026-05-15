from app.core.authz import ResourceAction
from app.ports.authn import Principal
from app.ports.authz import AuthorizerPort, AuthorizationError


class HexIAMAuthorizer(AuthorizerPort):
    def __init__(self) -> None:
        pass

    async def authorize(
            self, principal: Principal, action: str, *,
            resource_id: str | None = None, context=None
    ) -> None:
        if not resource_id:
            raise AuthorizationError("Missing resource ID")
        bitmask = int(principal.policy.get(resource_id, 0) or 0)
        key = action.upper()

        if key not in ResourceAction.__members__:
            raise AuthorizationError("unknown action")

        required = ResourceAction[key].value
        if not (bitmask & required):
            raise AuthorizationError("forbidden")
        return None

# class HexIAMAuthorizer(AuthorizerPort):
#
#     def __init__(self) -> None:
#         pass
#
#     def authorize(self, principal: Principal, permission: str, *, resource_id: str | None = None,
#                   context: dict[str, Any] | None = None) -> None:
#         try:
#             if not principal.policy:
#                 raise AuthorizationError("Missing policy in principal")
#
#             user_policy: Mapping[str, Any] = principal.policy
#
#             def check_permission(policy: Mapping[str, Any], permission_needed: str, resource: str):
#                 user_perm = policy.get(resource, 0)
#                 needed_perm = hex_iam_permission_map.get(permission_needed.lower(), 0)
#                 return bool(user_perm & needed_perm)
#
#             permitted: bool = check_permission(
#                 policy=user_policy, permission_needed=permission,
#                 resource=resource_id
#             )
#
#             resp = {
#                 "allow": permitted,
#                 "permitted": permitted,
#                 "resource": resource_id,
#                 "action": permission,
#                 "principal": principal,
#             }
#
#             # noinspection PyTypeChecker
#             return resp
#         except Exception as e:
#             raise AuthorizationError(str(e))
