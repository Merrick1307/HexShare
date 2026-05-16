from __future__ import annotations

from types import SimpleNamespace

import pytest

import app.adapters.object_storage.cloudinary_adapter as cloudinary_module
from app.adapters.object_storage.cloudinary_adapter import CloudinaryObjectStorageAdapter
from app.ports.object_storage_port import ObjectInfo


@pytest.fixture(autouse=True)
def fake_cloudinary_sdk(monkeypatch):
    monkeypatch.setattr(
        cloudinary_module,
        "cloudinary",
        SimpleNamespace(config=lambda **kwargs: kwargs),
    )
    monkeypatch.setattr(
        cloudinary_module,
        "cloudinary_utils",
        SimpleNamespace(
            api_sign_request=lambda params, secret: "signed123",
            private_download_url=lambda *args, **kwargs: "https://download.test/file.pdf",
        ),
    )
    monkeypatch.setattr(
        cloudinary_module,
        "cloudinary_api",
        SimpleNamespace(resource=lambda *args, **kwargs: {}),
    )
    monkeypatch.setattr(
        cloudinary_module,
        "cloudinary_uploader",
        SimpleNamespace(
            upload=lambda *args, **kwargs: {"bytes": 0, "etag": None},
            destroy=lambda *args, **kwargs: {"result": "ok"},
        ),
    )


@pytest.mark.asyncio
async def test_build_object_key_keeps_extension_for_raw_assets():
    adapter = CloudinaryObjectStorageAdapter(
        cloud_name="demo",
        api_key="key",
        api_secret="secret",
        prefix="documents",
    )

    key = adapter.build_object_key(
        tenant_id="tenant-1",
        document_id="doc-1",
        filename="Quarterly Report.pdf",
    )

    assert key == "documents/tenants/tenant-1/documents/doc-1/Quarterly_Report.pdf"


@pytest.mark.asyncio
async def test_create_presigned_upload_returns_signed_form(monkeypatch):
    adapter = CloudinaryObjectStorageAdapter(
        cloud_name="demo",
        api_key="key123",
        api_secret="secret123",
        prefix="documents",
    )

    upload = await adapter.create_temporary_upload(
        object_key="documents/tenants/t1/documents/d1/file.pdf",
        content_type="application/pdf",
        expires_in=600,
    )

    assert upload.method == "POST"
    assert upload.url.endswith("/v1_1/demo/raw/upload")
    assert upload.form_fields["api_key"] == "key123"
    assert upload.form_fields["signature"] == "signed123"
    assert upload.form_fields["public_id"] == "documents/tenants/t1/documents/d1/file.pdf"
    assert upload.form_fields["type"] == "private"


@pytest.mark.asyncio
async def test_head_object_maps_cloudinary_resource(monkeypatch):
    monkeypatch.setattr(
        cloudinary_module.cloudinary_api,
        "resource",
        lambda *args, **kwargs: {
            "public_id": "documents/tenants/t1/documents/d1/file.pdf",
            "bytes": 12345,
            "format": "pdf",
            "resource_type": "raw",
            "type": "private",
            "version": 7,
            "asset_id": "asset-1",
            "secure_url": "https://res.cloudinary.com/demo/raw/private/file.pdf",
        },
    )

    adapter = CloudinaryObjectStorageAdapter(
        cloud_name="demo",
        api_key="key",
        api_secret="secret",
    )

    info = await adapter.head_object(object_key="documents/tenants/t1/documents/d1/file.pdf")

    assert isinstance(info, ObjectInfo)
    assert info.size == 12345
    assert info.metadata["resource_type"] == "raw"
    assert info.metadata["type"] == "private"
    assert info.metadata["asset_id"] == "asset-1"


@pytest.mark.asyncio
async def test_delete_object_calls_destroy(monkeypatch):
    called = {}

    def fake_destroy(public_id, **kwargs):
        called["public_id"] = public_id
        called["kwargs"] = kwargs
        return {"result": "ok"}

    monkeypatch.setattr(
        cloudinary_module.cloudinary_uploader,
        "destroy",
        fake_destroy,
    )

    adapter = CloudinaryObjectStorageAdapter(
        cloud_name="demo",
        api_key="key",
        api_secret="secret",
    )

    await adapter.delete_object(object_key="documents/tenants/t1/documents/d1/file.pdf")

    assert called["public_id"] == "documents/tenants/t1/documents/d1/file.pdf"
    assert called["kwargs"]["resource_type"] == "raw"
    assert called["kwargs"]["type"] == "private"
