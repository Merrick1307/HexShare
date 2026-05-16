from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from app.adapters.object_storage.r2 import CloudFlareR2ObjectStorageAdapter
from app.adapters.object_storage.s3 import S3ObjectStorageAdapter


class FakeS3Client:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any], int, str]] = []
        self.head_response: dict[str, Any] = {
            "ContentLength": 1024,
            "ETag": '"etag-123"',
            "ContentType": "application/pdf",
            "Metadata": {"x-meta": "1"},
        }

    def generate_presigned_url(self, ClientMethod: str, Params: dict[str, Any], ExpiresIn: int, HttpMethod: str):
        self.calls.append((ClientMethod, Params, ExpiresIn, HttpMethod))
        return f"https://storage.test/{Params['Key']}?method={ClientMethod}"

    def head_object(self, Bucket: str, Key: str):
        return self.head_response

    def delete_object(self, Bucket: str, Key: str):
        return {"Deleted": [{"Key": Key}]}


@pytest.fixture
def fake_s3_client(monkeypatch) -> FakeS3Client:
    client = FakeS3Client()

    import app.adapters.object_storage.s3 as s3_module

    monkeypatch.setattr(s3_module, "boto3", SimpleNamespace(client=lambda *args, **kwargs: client))
    monkeypatch.setattr(s3_module, "Config", lambda **kwargs: kwargs)
    return client


@pytest.mark.asyncio
async def test_s3_adapter_builds_sanitized_object_key(fake_s3_client):
    adapter = S3ObjectStorageAdapter(bucket="hexshare-docs", prefix="uploads")

    object_key = adapter.build_object_key(
        tenant_id="tenant_123",
        document_id="doc_456",
        filename="../../Quarterly Report (Final).pdf",
    )

    assert object_key == "uploads/tenants/tenant_123/documents/doc_456/Quarterly_Report_Final_.pdf"


@pytest.mark.asyncio
async def test_s3_adapter_returns_presigned_upload(fake_s3_client):
    adapter = S3ObjectStorageAdapter(bucket="hexshare-docs", prefix="uploads")

    upload = await adapter.create_temporary_upload(
        object_key="uploads/tenants/t1/documents/d1/report.pdf",
        content_type="application/pdf",
        expires_in=300,
    )

    assert upload.method == "PUT"
    assert upload.headers == {"Content-Type": "application/pdf"}
    assert upload.expires_in == 300
    assert "method=put_object" in upload.url
    assert fake_s3_client.calls[0][1]["Bucket"] == "hexshare-docs"


@pytest.mark.asyncio
async def test_s3_adapter_head_object_normalizes_etag(fake_s3_client):
    adapter = S3ObjectStorageAdapter(bucket="hexshare-docs", prefix="uploads")

    info = await adapter.head_object(object_key="uploads/tenants/t1/documents/d1/report.pdf")

    assert info is not None
    assert info.etag == "etag-123"
    assert info.size == 1024
    assert info.content_type == "application/pdf"
    assert info.metadata == {"x-meta": "1"}


def test_r2_adapter_uses_account_endpoint(fake_s3_client):
    adapter = CloudFlareR2ObjectStorageAdapter(
        account_id="acc_123",
        bucket="hexshare-docs",
        access_key_id="key",
        secret_access_key="secret",
    )

    assert adapter.endpoint_url == "https://acc_123.r2.cloudflarestorage.com"
    assert adapter.bucket == "hexshare-docs"
