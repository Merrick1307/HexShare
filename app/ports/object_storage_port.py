from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Mapping


@dataclass(frozen=True)
class PresignedUpload:
    object_key: str
    url: str
    method: str = "PUT"
    headers: Mapping[str, str] = field(default_factory=dict)
    form_fields: Mapping[str, str] = field(default_factory=dict)
    expires_in: int = 900


@dataclass(frozen=True)
class ObjectInfo:
    object_key: str
    size: int | None = None
    etag: str | None = None
    content_type: str | None = None
    metadata: Mapping[str, str] = field(default_factory=dict)


class ObjectStoragePort(ABC):
    @abstractmethod
    def build_object_key(self, *, tenant_id: str, document_id: str, filename: str) -> str:
        raise NotImplementedError

    @abstractmethod
    async def create_presigned_upload(
        self,
        *,
        object_key: str,
        content_type: str,
        expires_in: int = 900,
    ) -> PresignedUpload:
        raise NotImplementedError

    @abstractmethod
    async def create_presigned_download(
        self,
        *,
        object_key: str,
        expires_in: int = 900,
        filename: str | None = None,
    ) -> str:
        raise NotImplementedError

    @abstractmethod
    async def head_object(self, *, object_key: str) -> ObjectInfo | None:
        raise NotImplementedError

    @abstractmethod
    async def delete_object(self, *, object_key: str) -> None:
        raise NotImplementedError
