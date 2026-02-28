from abc import ABC, abstractmethod
from typing import Any, Mapping

class PolicyEvaluatorPort(ABC):
    @abstractmethod
    def evaluate(
        self,
        *,
        policy: Mapping[str, Any],
        action: str,
        resource: str,
        context: Mapping[str, Any] | None = None,
    ) -> bool:
        raise NotImplementedError