from .s3 import S3ObjectStorageAdapter
from .r2 import CloudFlareR2ObjectStorageAdapter, CloudflareR2ObjectStorageAdapter

__all__ = [
    "S3ObjectStorageAdapter",
    "CloudFlareR2ObjectStorageAdapter",
    "CloudflareR2ObjectStorageAdapter",
]
