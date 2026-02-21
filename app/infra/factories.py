from typing import Callable, Dict

from app.ports import StoragePort


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