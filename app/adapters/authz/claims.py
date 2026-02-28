from app.ports.authn import Principal
from app.ports.authz import AuthorizerPort, AuthorizationError
from app.ports.policy_evaluator import PolicyEvaluatorPort


class ClaimsAuthorizer(AuthorizerPort):
    def __init__(self, evaluator: PolicyEvaluatorPort) -> None:
        self.evaluator = evaluator

    async def authorize(
            self, principal: Principal, action: str, *,
            resource_id: str | None = None, context=None
    ) -> None:
        ok = self.evaluator.evaluate(
            policy=principal.policy or {},
            action=action,
            resource=resource_id,
            context=context,
        )
        if not ok:
            raise AuthorizationError("forbidden")


# class ClaimsAuthorizer(AuthorizerPort):
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
