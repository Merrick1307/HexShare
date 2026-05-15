from __future__ import annotations

from typing import Any, Callable, Dict

from app.ports import ObjectStoragePort, StoragePort
from app.ports.access_control import AccessControlPort
from app.ports.authn import AuthenticatorPort
from app.ports.iam_policy import IAMPolicyPort
from app.ports.oidc_client import OIDCClientPort


class AccessControlFactory:
    _registry: Dict[str, Callable[..., AccessControlPort]] = {}

    @classmethod
    def register(cls, name: str):
        def deco(builder: Callable[..., AccessControlPort]):
            cls._registry[name] = builder
            return builder
        return deco

    @classmethod
    def create(cls, name: str, **kwargs: Any) -> AccessControlPort:
        try:
            return cls._registry[name](**kwargs)
        except KeyError as exc:
            raise ValueError(f"Unknown access control adapter: {name}") from exc


class AuthenticatorFactory:
    _registry: Dict[str, Callable[..., AuthenticatorPort]] = {}

    @classmethod
    def register(cls, name: str):
        def deco(builder: Callable[..., AuthenticatorPort]):
            cls._registry[name] = builder
            return builder
        return deco

    @classmethod
    def create(cls, name: str, **kwargs: Any) -> AuthenticatorPort:
        try:
            return cls._registry[name](**kwargs)
        except KeyError as exc:
            raise ValueError(f"Unknown authenticator adapter: {name}") from exc


class ObjectStorageFactory:
    _registry: Dict[str, Callable[..., ObjectStoragePort]] = {}

    @classmethod
    def register(cls, name: str):
        def deco(builder: Callable[..., ObjectStoragePort]):
            cls._registry[name] = builder
            return builder
        return deco

    @classmethod
    def create(cls, name: str, **kwargs: Any) -> ObjectStoragePort:
        try:
            return cls._registry[name](**kwargs)
        except KeyError as exc:
            raise ValueError(f"Unknown object storage adapter: {name}") from exc


class OIDCClientFactory:
    _registry: Dict[str, Callable[..., OIDCClientPort]] = {}

    @classmethod
    def register(cls, name: str):
        def deco(builder: Callable[..., OIDCClientPort]):
            cls._registry[name] = builder
            return builder
        return deco

    @classmethod
    def create(cls, name: str, **kwargs) -> OIDCClientPort:
        try:
            return cls._registry[name](**kwargs)
        except KeyError as exc:
            raise ValueError(f"Unknown OIDC client: {name}") from exc


class IAMPolicyFactory:
    _registry: Dict[str, Callable[..., IAMPolicyPort]] = {}

    @classmethod
    def register(cls, name: str):
        def deco(builder: Callable[..., IAMPolicyPort]):
            cls._registry[name] = builder
            return builder
        return deco

    @classmethod
    def create(cls, name: str, **kwargs: Any) -> IAMPolicyPort:
        try:
            return cls._registry[name](**kwargs)
        except KeyError as exc:
            raise ValueError(f"Unknown IAM policy adapter: {name}") from exc


class StorageFactory:
    _registry: Dict[str, Callable[..., StoragePort]] = {}

    @classmethod
    def register(cls, name: str):
        def deco(builder: Callable[..., StoragePort]):
            cls._registry[name] = builder
            return builder
        return deco

    @classmethod
    def create(cls, name: str, **kwargs: Any) -> StoragePort:
        try:
            return cls._registry[name](**kwargs)
        except KeyError as exc:
            raise ValueError(f"Unknown storage adapter: {name}") from exc
