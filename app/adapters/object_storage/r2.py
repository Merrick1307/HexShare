from __future__ import annotations

import os
from typing import Any

from app.infra.factories import ObjectStorageFactory
from app.ports.object_storage_port import ObjectStoragePort
from app.adapters.object_storage.s3 import S3ObjectStorageAdapter


class CloudFlareR2ObjectStorageAdapter(S3ObjectStorageAdapter):
    """
    Cloudflare R2 adapter.

    R2 exposes an S3-compatible API, so this adapter reuses the S3
    implementation and only specialises configuration defaults.
    """

    def __init__(
        self,
        *,
        account_id: str | None = None,
        endpoint_url: str | None = None,
        **kwargs,
    ) -> None:
        resolved_endpoint = endpoint_url or (
            f"https://{account_id}.r2.cloudflarestorage.com" if account_id else None
        )
        super().__init__(endpoint_url=resolved_endpoint, force_path_style=False, **kwargs)
        self.account_id = account_id


CloudflareR2ObjectStorageAdapter = CloudFlareR2ObjectStorageAdapter


def _load_r2_config() -> dict[str, Any]:
    account_id = os.getenv("CLOUDFLARE_R2_ACCOUNT_ID")
    return {
        "account_id": account_id,
        "bucket": os.getenv("HEXSHARE_OBJECT_BUCKET", ""),
        "region_name": os.getenv("AWS_REGION", "auto"),
        "endpoint_url": os.getenv("S3_ENDPOINT_URL") or (
            f"https://{account_id}.r2.cloudflarestorage.com" if account_id else None
        ),
        "access_key_id": os.getenv("AWS_ACCESS_KEY_ID"),
        "secret_access_key": os.getenv("AWS_SECRET_ACCESS_KEY"),
        "session_token": os.getenv("AWS_SESSION_TOKEN"),
        "prefix": os.getenv("HEXSHARE_OBJECT_PREFIX", "documents"),
        "signature_version": os.getenv("S3_SIGNATURE_VERSION", "s3v4"),
    }


@ObjectStorageFactory.register("r2")
@ObjectStorageFactory.register("cloudflare_r2")
def create_cloudflare_r2_object_storage(**kwargs) -> ObjectStoragePort:
    config = _load_r2_config()
    config.update({k: v for k, v in kwargs.items() if v is not None})
    if not config.get("bucket"):
        raise RuntimeError("Missing HEXSHARE_OBJECT_BUCKET for Cloudflare R2 object storage")
    if not config.get("endpoint_url"):
        raise RuntimeError("Missing CLOUDFLARE_R2_ACCOUNT_ID or S3_ENDPOINT_URL for Cloudflare R2 object storage")
    return CloudFlareR2ObjectStorageAdapter(**config)
