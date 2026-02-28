from typing import Any, Mapping
from app.core.authz import HEXIAMAction
from app.infra.factories import PolicyEvaluatorRegistry
from app.ports.policy_evaluator import PolicyEvaluatorPort


class HexIamBitmaskEvaluator(PolicyEvaluatorPort):
    def evaluate(self, *, policy: Mapping[str, Any], action: str, resource: str, context=None) -> bool:
        bitmask = int(policy.get(resource, 0) or 0)
        key = action.upper()

        if key not in HEXIAMAction.__members__:
            return False

        required = HEXIAMAction[key].value
        return (bitmask & required) == required


@PolicyEvaluatorRegistry.register("hexiam_bitmask")
def _build_hexiam_evaluator(**_) -> PolicyEvaluatorPort:
    return HexIamBitmaskEvaluator()