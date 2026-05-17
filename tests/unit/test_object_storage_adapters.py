from __future__ import annotations

import importlib
from types import SimpleNamespace
from typing import Any

import pytest

from app.adapters.object_storage.r2 import CloudFlareR2ObjectStorageAdapter
from app.adapters.object_storage.s3 import S3ObjectStorageAdapter


class FakeS3Client:
    def __init__(self, endpoint_url: str | None = None) -> None:
        self.endpoint_url = endpoint_url
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
def fake_s3_client(monkeypatch) -> tuple[dict[str | None, FakeS3Client], list[dict[str, Any]]]:
    clients: dict[str | None, FakeS3Client] = {}
    client_kwargs: list[dict[str, Any]] = []

    import app.adapters.object_storage.s3 as s3_module

    def _make_client(*args, **kwargs):
        client_kwargs.append(dict(kwargs))
        endpoint_url = kwargs.get("endpoint_url")
        client = clients.get(endpoint_url)
        if client is None:
            client = FakeS3Client(endpoint_url=endpoint_url)
            clients[endpoint_url] = client
        return client

    monkeypatch.setattr(s3_module, "boto3", SimpleNamespace(client=_make_client))
    monkeypatch.setattr(s3_module, "Config", lambda **kwargs: kwargs)
    return clients, client_kwargs


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
    clients, _ = fake_s3_client
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
    assert clients[None].calls[0][1]["Bucket"] == "hexshare-docs"


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


@pytest.mark.asyncio
async def test_s3_adapter_uses_public_endpoint_for_presigned_browser_urls(fake_s3_client):
    clients, _ = fake_s3_client
    adapter = S3ObjectStorageAdapter(
        bucket="hexshare-docs",
        endpoint_url="http://minio:9000",
        public_endpoint_url="http://localhost:9000",
        force_path_style=True,
    )

    await adapter.create_temporary_upload(
        object_key="uploads/tenants/t1/documents/d1/report.pdf",
        content_type="application/pdf",
        expires_in=300,
    )

    assert adapter.endpoint_url == "http://minio:9000"
    assert adapter.public_endpoint_url == "http://localhost:9000"
    assert clients["http://localhost:9000"].calls[0][0] == "put_object"


def test_s3_factory_prefers_s3_region_env(fake_s3_client, monkeypatch):
    _, client_kwargs = fake_s3_client
    monkeypatch.setenv("HEXSHARE_OBJECT_BUCKET", "hexshare-docs")
    monkeypatch.setenv("S3_REGION", "us-east-1")
    monkeypatch.setenv("AWS_REGION", "eu-west-1")
    monkeypatch.setenv("S3_FORCE_PATH_STYLE", "true")

    s3_module = importlib.import_module("app.adapters.object_storage.s3")
    adapter = s3_module.create_s3_object_storage()

    assert adapter.region_name == "us-east-1"
    assert adapter.force_path_style is True
    assert client_kwargs[0]["aws_session_token"] is None


def test_r2_factory_prefers_s3_region_env(fake_s3_client, monkeypatch):
    monkeypatch.setenv("HEXSHARE_OBJECT_BUCKET", "hexshare-docs")
    monkeypatch.setenv("CLOUDFLARE_R2_ACCOUNT_ID", "acc_123")
    monkeypatch.setenv("S3_REGION", "auto")
    monkeypatch.setenv("AWS_REGION", "eu-west-1")

    r2_module = importlib.import_module("app.adapters.object_storage.r2")
    adapter = r2_module.create_cloudflare_r2_object_storage()

    assert adapter.region_name == "auto"


def test_s3_factory_omits_blank_session_token(fake_s3_client, monkeypatch):
    _, client_kwargs = fake_s3_client
    monkeypatch.setenv("HEXSHARE_OBJECT_BUCKET", "hexshare-docs")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "minioadmin")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "minioadmin")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "")

    s3_module = importlib.import_module("app.adapters.object_storage.s3")
    adapter = s3_module.create_s3_object_storage()

    assert adapter is not None
    assert client_kwargs[0]["aws_session_token"] is None
