from typing import Callable, Dict

from app.ports import StoragePort
from app.ports.access_control import AccessControlPort
from app.ports.authn import AuthenticatorPort
from app.ports.policy_evaluator import PolicyEvaluatorPort


class StorageFactory:
    _registry: Dict[str, Callable[..., StoragePort]] = {}

    @classmethod
    def register(cls, name: str):
        def deco(builder: Callable[..., StoragePort]):
            cls._registry[name] = builder
            return builder
        return deco

    @classmethod
    def create(cls, name: str, **kwargs) -> StoragePort:
        try:
            return cls._registry[name](**kwargs)
        except KeyError:
            raise ValueError(f"Unknown storage adapter: {name}")


class PolicyEvaluatorRegistry:
    _registry: Dict[str, Callable[..., PolicyEvaluatorPort]] = {}

    @classmethod
    def register(cls, name: str):
        def deco(builder: Callable[..., PolicyEvaluatorPort]):
            cls._registry[name] = builder
            return builder
        return deco

    @classmethod
    def create(cls, name: str, **kwargs) -> PolicyEvaluatorPort:
        try:
            return cls._registry[name](**kwargs)
        except KeyError:
            raise ValueError(f"Unknown policy evaluator: {name}")


class AccessControlFactory:
    _registry: Dict[str, Callable[..., AccessControlPort]] = {}

    @classmethod
    def register(cls, name: str):
        def deco(builder: Callable[..., AccessControlPort]):
            cls._registry[name] = builder
            return builder
        return deco

    @classmethod
    def create(cls, name: str, **kwargs) -> AccessControlPort:
        try:
            return cls._registry[name](**kwargs)
        except KeyError:
            raise ValueError(f"Unknown access control adapter: {name}")


class AuthenticatorFactory:
    _registry: Dict[str, Callable[..., AuthenticatorPort]] = {}

    @classmethod
    def register(cls, name: str):
        def deco(builder: Callable[..., AuthenticatorPort]):
            cls._registry[name] = builder
            return builder
        return deco

    @classmethod
    def create(cls, name: str, **kwargs) -> AuthenticatorPort:
        try:
            return cls._registry[name](**kwargs)
        except KeyError:
            raise ValueError(f"Unknown authenticator adapter: {name}")