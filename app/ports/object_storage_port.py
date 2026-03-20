"""
Object storage port.

This port abstracts file-byte storage concerns such as generating object
keys, presigned upload/download URLs, metadata lookup, and deletion.
It deliberately sits beside ``StoragePort`` rather than replacing it:
``StoragePort`` persists HexShare metadata, while ``ObjectStoragePort``
handles raw document bytes in an object store.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Mapping, Optional


@dataclass(frozen=True)
class PresignedUpload:
    object_key: str
    url: str
    method: str = "PUT"
    headers: Mapping[str, str] | None = None
    expires_in: int = 900


@dataclass(frozen=True)
class ObjectInfo:
    object_key: str
    size: int | None = None
    etag: str | None = None
    content_type: str | None = None
    metadata: Mapping[str, str] | None = None


class ObjectStoragePort(ABC):
    """Abstract base class for object storage adapters."""

    @abstractmethod
    def build_object_key(self, *, tenant_id: str, document_id: str, filename: str) -> str:
        """Build a stable object key for a tenant-owned document."""

    @abstractmethod
    async def create_presigned_upload(
        self,
        *,
        object_key: str,
        content_type: str,
        expires_in: int = 900,
    ) -> PresignedUpload:
        """Create a presigned URL for uploading an object."""

    @abstractmethod
    async def create_presigned_download(
        self,
        *,
        object_key: str,
        expires_in: int = 900,
        filename: Optional[str] = None,
    ) -> str:
        """Create a presigned URL for downloading an object."""

    @abstractmethod
    async def head_object(self, *, object_key: str) -> ObjectInfo | None:
        """Return object metadata if the object exists."""

    @abstractmethod
    async def delete_object(self, *, object_key: str) -> None:
        """Delete an object from the backing store."""
