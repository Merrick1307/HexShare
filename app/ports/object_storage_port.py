from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import AsyncIterator, Mapping


@dataclass(frozen=True)
class TemporaryObjectAccess:
    object_key: str
    url: str
    method: str = "PUT"
    headers: Mapping[str, str] = field(default_factory=dict)
    fields: Mapping[str, str] = field(default_factory=dict)
    expires_in: int = 900

    @property
    def form_fields(self) -> Mapping[str, str]:
        return self.fields


@dataclass(frozen=True)
class ObjectDescriptor:
    object_key: str
    size: int | None = None
    etag: str | None = None
    content_type: str | None = None
    metadata: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ObjectWriteRequest:
    object_key: str
    content: bytes
    content_type: str
    metadata: Mapping[str, str] = field(default_factory=dict)


PresignedUpload = TemporaryObjectAccess
ObjectInfo = ObjectDescriptor


class ObjectStoragePort(ABC):
    @abstractmethod
    def build_object_key(self, *, tenant_id: str, document_id: str, filename: str) -> str:
        raise NotImplementedError

    @abstractmethod
    async def read_object(self, *, object_key: str) -> bytes:
        raise NotImplementedError

    @abstractmethod
    async def write_object(self, request: ObjectWriteRequest) -> ObjectDescriptor:
        raise NotImplementedError

    async def stream_object(self, *, object_key: str) -> AsyncIterator[bytes]:
        yield await self.read_object(object_key=object_key)

    @abstractmethod
    async def create_temporary_upload(
        self,
        *,
        object_key: str,
        content_type: str,
        expires_in: int = 900,
    ) -> TemporaryObjectAccess:
        raise NotImplementedError

    async def create_presigned_upload(
        self,
        *,
        object_key: str,
        content_type: str,
        expires_in: int = 900,
    ) -> PresignedUpload:
        return await self.create_temporary_upload(
            object_key=object_key,
            content_type=content_type,
            expires_in=expires_in,
        )

    @abstractmethod
    async def create_temporary_download(
        self,
        *,
        object_key: str,
        expires_in: int = 900,
        filename: str | None = None,
    ) -> TemporaryObjectAccess:
        raise NotImplementedError

    async def create_presigned_download(
        self,
        *,
        object_key: str,
        expires_in: int = 900,
        filename: str | None = None,
    ) -> str:
        access = await self.create_temporary_download(
            object_key=object_key,
            expires_in=expires_in,
            filename=filename,
        )
        return access.url

    @abstractmethod
    async def head_object(self, *, object_key: str) -> ObjectDescriptor | None:
        raise NotImplementedError

    @abstractmethod
    async def delete_object(self, *, object_key: str) -> None:
        raise NotImplementedError
