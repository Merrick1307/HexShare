from __future__ import annotations

import asyncio
import os
import re
from pathlib import PurePosixPath
from typing import Any, Mapping, Optional

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from app.infra.factories import ObjectStorageFactory
from app.ports.object_storage_port import ObjectInfo, ObjectStoragePort, PresignedUpload


_FILENAME_SANITIZER = re.compile(r"[^A-Za-z0-9._-]+")


class S3ObjectStorageAdapter(ObjectStoragePort):
    def __init__(
        self,
        *,
        bucket: str,
        region_name: str | None = None,
        endpoint_url: str | None = None,
        access_key_id: str | None = None,
        secret_access_key: str | None = None,
        session_token: str | None = None,
        prefix: str = "documents",
        force_path_style: bool = False,
        signature_version: str = "s3v4",
    ) -> None:
        self.bucket = bucket
        self.region_name = region_name
        self.endpoint_url = endpoint_url
        self.prefix = prefix.strip("/")
        self.force_path_style = force_path_style
        self.signature_version = signature_version

        config = Config(
            region_name=region_name,
            signature_version=signature_version,
            s3={"addressing_style": "path" if force_path_style else "virtual"},
        )

        self._client = boto3.client(
            "s3",
            region_name=region_name,
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            aws_session_token=session_token,
            config=config,
        )

    def _safe_filename(self, filename: str) -> str:
        raw = PurePosixPath(filename).name.strip() or "file"
        return _FILENAME_SANITIZER.sub("_", raw)

    def build_object_key(self, *, tenant_id: str, document_id: str, filename: str) -> str:
        safe_name = self._safe_filename(filename)
        parts = [part for part in (self.prefix, "tenants", tenant_id, "documents", document_id, safe_name) if part]
        return "/".join(parts)

    async def create_presigned_upload(
        self,
        *,
        object_key: str,
        content_type: str,
        expires_in: int = 900,
    ) -> PresignedUpload:
        def _generate() -> str:
            return self._client.generate_presigned_url(
                ClientMethod="put_object",
                Params={
                    "Bucket": self.bucket,
                    "Key": object_key,
                    "ContentType": content_type,
                },
                ExpiresIn=expires_in,
                HttpMethod="PUT",
            )

        url = await asyncio.to_thread(_generate)
        return PresignedUpload(
            object_key=object_key,
            url=url,
            method="PUT",
            headers={"Content-Type": content_type},
            expires_in=expires_in,
        )

    async def create_presigned_download(
        self,
        *,
        object_key: str,
        expires_in: int = 900,
        filename: Optional[str] = None,
    ) -> str:
        def _generate() -> str:
            params: dict[str, Any] = {
                "Bucket": self.bucket,
                "Key": object_key,
            }
            if filename:
                params["ResponseContentDisposition"] = f'attachment; filename="{filename}"'
            return self._client.generate_presigned_url(
                ClientMethod="get_object",
                Params=params,
                ExpiresIn=expires_in,
                HttpMethod="GET",
            )

        return await asyncio.to_thread(_generate)

    async def head_object(self, *, object_key: str) -> ObjectInfo | None:
        def _head() -> ObjectInfo | None:
            try:
                resp = self._client.head_object(Bucket=self.bucket, Key=object_key)
            except ClientError as exc:
                status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
                code = exc.response.get("Error", {}).get("Code")
                if status == 404 or code in {"404", "NoSuchKey", "NotFound"}:
                    return None
                raise
            return ObjectInfo(
                object_key=object_key,
                size=resp.get("ContentLength"),
                etag=(resp.get("ETag") or "").strip('"') or None,
                content_type=resp.get("ContentType"),
                metadata=resp.get("Metadata") or {},
            )

        return await asyncio.to_thread(_head)

    async def delete_object(self, *, object_key: str) -> None:
        await asyncio.to_thread(
            self._client.delete_object,
            Bucket=self.bucket,
            Key=object_key,
        )


def _to_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _load_s3_config() -> dict[str, Any]:
    return {
        "bucket": os.getenv("HEXSHARE_OBJECT_BUCKET", ""),
        "region_name": os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION"),
        "endpoint_url": os.getenv("S3_ENDPOINT_URL"),
        "access_key_id": os.getenv("AWS_ACCESS_KEY_ID"),
        "secret_access_key": os.getenv("AWS_SECRET_ACCESS_KEY"),
        "session_token": os.getenv("AWS_SESSION_TOKEN"),
        "prefix": os.getenv("HEXSHARE_OBJECT_PREFIX", "documents"),
        "force_path_style": _to_bool(os.getenv("S3_FORCE_PATH_STYLE"), default=False),
        "signature_version": os.getenv("S3_SIGNATURE_VERSION", "s3v4"),
    }


@ObjectStorageFactory.register("s3")
def create_s3_object_storage(**kwargs) -> ObjectStoragePort:
    config = _load_s3_config()
    config.update({k: v for k, v in kwargs.items() if v is not None})
    if not config.get("bucket"):
        raise RuntimeError("Missing HEXSHARE_OBJECT_BUCKET for S3 object storage")
    return S3ObjectStorageAdapter(**config)
