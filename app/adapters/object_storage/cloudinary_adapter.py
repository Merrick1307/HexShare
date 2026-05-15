from __future__ import annotations

import os
import re
import time
from pathlib import PurePosixPath
from typing import Any, Optional

try:
    import cloudinary
    from cloudinary import api as cloudinary_api
    from cloudinary import uploader as cloudinary_uploader
    from cloudinary import utils as cloudinary_utils
except ImportError:
    cloudinary = None  # type: ignore
    cloudinary_api = None  # type: ignore
    cloudinary_uploader = None  # type: ignore
    cloudinary_utils = None  # type: ignore

from app.infra.factories import ObjectStorageFactory
from app.ports.object_storage_port import ObjectInfo, ObjectStoragePort, PresignedUpload


_FILENAME_SANITIZER = re.compile(r"[^A-Za-z0-9._-]+")


class CloudinaryObjectStorageAdapter(ObjectStoragePort):
    """
    Cloudinary-backed object storage adapter.

    Important behavior differences versus S3/R2:
    - direct browser uploads are signed POST form uploads, not presigned PUT URLs
    - this adapter is best suited to document/file storage with resource_type='raw'
    - time-limited downloads are generated using Cloudinary's private download URLs
    """

    def __init__(
        self,
        *,
        cloud_name: str,
        api_key: str,
        api_secret: str,
        upload_prefix: str | None = None,
        secure: bool = True,
        prefix: str = "documents",
        resource_type: str = "raw",
        delivery_type: str = "private",
    ) -> None:
        self.cloud_name = cloud_name
        self.api_key = api_key
        self.api_secret = api_secret
        self.upload_prefix = upload_prefix
        self.secure = secure
        self.prefix = prefix.strip("/")
        self.resource_type = resource_type
        self.delivery_type = delivery_type

        cloudinary.config(
            cloud_name=cloud_name,
            api_key=api_key,
            api_secret=api_secret,
            secure=secure,
            upload_prefix=upload_prefix,
        )

    def _safe_filename(self, filename: str) -> str:
        raw = PurePosixPath(filename).name.strip() or "file"
        return _FILENAME_SANITIZER.sub("_", raw)

    def build_object_key(self, *, tenant_id: str, document_id: str, filename: str) -> str:
        safe_name = self._safe_filename(filename)
        # For Cloudinary raw assets, the public_id should include the file extension.
        parts = [
            part
            for part in (
                self.prefix,
                "tenants",
                tenant_id,
                "documents",
                document_id,
                safe_name,
            )
            if part
        ]
        return "/".join(parts)

    def _upload_endpoint(self) -> str:
        base = (self.upload_prefix or "https://api.cloudinary.com").rstrip("/")
        return f"{base}/v1_1/{self.cloud_name}/{self.resource_type}/upload"

    async def create_presigned_upload(
        self,
        *,
        object_key: str,
        content_type: str,
        expires_in: int = 900,
    ) -> PresignedUpload:
        timestamp = int(time.time())
        params_to_sign = {
            "public_id": object_key,
            "timestamp": timestamp,
            "type": self.delivery_type,
        }
        signature = cloudinary_utils.api_sign_request(params_to_sign, self.api_secret)

        form_fields = {
            "api_key": self.api_key,
            "timestamp": str(timestamp),
            "signature": signature,
            "public_id": object_key,
            "type": self.delivery_type,
        }

        return PresignedUpload(
            object_key=object_key,
            url=self._upload_endpoint(),
            method="POST",
            headers={},
            form_fields=form_fields,
            expires_in=expires_in,
        )

    async def create_presigned_download(
        self,
        *,
        object_key: str,
        expires_in: int = 900,
        filename: Optional[str] = None,
    ) -> str:
        expires_at = int(time.time()) + int(expires_in)
        suffix = PurePosixPath(object_key).suffix.lstrip(".")
        if not suffix:
            raise ValueError("Cloudinary raw downloads require a file extension in object_key")

        return cloudinary_utils.private_download_url(
            object_key,
            suffix,
            resource_type=self.resource_type,
            type=self.delivery_type,
            expires_at=expires_at,
            attachment=bool(filename),
        )

    async def head_object(self, *, object_key: str) -> ObjectInfo | None:
        try:
            resp = cloudinary_api.resource(
                object_key,
                resource_type=self.resource_type,
                type=self.delivery_type,
            )
        except Exception as exc:
            message = str(exc).lower()
            if "not found" in message or "404" in message:
                return None
            raise

        metadata = {
            "asset_id": resp.get("asset_id"),
            "public_id": resp.get("public_id"),
            "version": resp.get("version"),
            "format": resp.get("format"),
            "resource_type": resp.get("resource_type"),
            "type": resp.get("type"),
            "secure_url": resp.get("secure_url"),
            "url": resp.get("url"),
        }
        metadata = {k: v for k, v in metadata.items() if v is not None}

        return ObjectInfo(
            object_key=object_key,
            size=resp.get("bytes"),
            etag=resp.get("etag"),
            content_type=resp.get("format"),
            metadata=metadata,
        )

    async def delete_object(self, *, object_key: str) -> None:
        cloudinary_uploader.destroy(
            object_key,
            resource_type=self.resource_type,
            type=self.delivery_type,
            invalidate=True,
        )


def _load_cloudinary_config() -> dict[str, Any]:
    return {
        "cloud_name": os.getenv("CLOUDINARY_CLOUD_NAME", ""),
        "api_key": os.getenv("CLOUDINARY_API_KEY") or os.getenv("CLOUDINARY_KEY") or "",
        "api_secret": os.getenv("CLOUDINARY_API_SECRET") or os.getenv("CLOUDINARY_SECRET") or "",
        "upload_prefix": os.getenv("CLOUDINARY_UPLOAD_PREFIX"),
        "secure": (os.getenv("CLOUDINARY_SECURE", "true").strip().lower() not in {"0", "false", "no", "off"}),
        "prefix": os.getenv("HEXSHARE_OBJECT_PREFIX", "documents"),
        "resource_type": os.getenv("CLOUDINARY_RESOURCE_TYPE", "raw"),
        "delivery_type": os.getenv("CLOUDINARY_DELIVERY_TYPE", "private"),
    }


@ObjectStorageFactory.register("cloudinary")
def create_cloudinary_object_storage(**kwargs) -> ObjectStoragePort:
    config = _load_cloudinary_config()
    config.update({k: v for k, v in kwargs.items() if v is not None})
    if not config.get("cloud_name"):
        raise RuntimeError("Missing CLOUDINARY_CLOUD_NAME for Cloudinary object storage")
    if not config.get("api_key"):
        raise RuntimeError("Missing CLOUDINARY_API_KEY for Cloudinary object storage")
    if not config.get("api_secret"):
        raise RuntimeError("Missing CLOUDINARY_API_SECRET for Cloudinary object storage")
    return CloudinaryObjectStorageAdapter(**config)
