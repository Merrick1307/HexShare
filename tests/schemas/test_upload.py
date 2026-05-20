from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.upload import CompleteUploadRequest, InitiateUploadRequest


class TestInitiateUploadRequest:

    def test_valid_minimal_payload(self):
        req = InitiateUploadRequest(filename="doc.pdf", content_type="application/pdf", size=1)
        assert req.filename == "doc.pdf"
        assert req.size == 1
        assert req.expires_in == 900

    def test_size_must_be_at_least_1(self):
        with pytest.raises(ValidationError) as exc:
            InitiateUploadRequest(filename="doc.pdf", content_type="application/pdf", size=0)
        errors = exc.value.errors()
        assert any(e["loc"] == ("size",) for e in errors)

    def test_size_must_not_be_negative(self):
        with pytest.raises(ValidationError) as exc:
            InitiateUploadRequest(filename="doc.pdf", content_type="application/pdf", size=-1)
        errors = exc.value.errors()
        assert any(e["loc"] == ("size",) for e in errors)

    def test_expires_in_defaults_to_900(self):
        req = InitiateUploadRequest(filename="doc.pdf", content_type="application/pdf", size=100)
        assert req.expires_in == 900

    def test_expires_in_custom_value(self):
        req = InitiateUploadRequest(filename="doc.pdf", content_type="application/pdf", size=100, expires_in=600)
        assert req.expires_in == 600

    def test_expires_in_below_minimum(self):
        with pytest.raises(ValidationError) as exc:
            InitiateUploadRequest(filename="doc.pdf", content_type="application/pdf", size=100, expires_in=30)
        errors = exc.value.errors()
        assert any(e["loc"] == ("expires_in",) for e in errors)

    def test_expires_in_above_maximum(self):
        with pytest.raises(ValidationError) as exc:
            InitiateUploadRequest(filename="doc.pdf", content_type="application/pdf", size=100, expires_in=7200)
        errors = exc.value.errors()
        assert any(e["loc"] == ("expires_in",) for e in errors)

    def test_filename_required(self):
        with pytest.raises(ValidationError):
            InitiateUploadRequest(content_type="application/pdf", size=100)

    def test_content_type_required(self):
        with pytest.raises(ValidationError):
            InitiateUploadRequest(filename="doc.pdf", size=100)

    def test_large_size_accepted_by_schema(self):
        """Schema itself does not enforce a max — that's the service layer's job."""
        req = InitiateUploadRequest(filename="big.pdf", content_type="application/pdf", size=10 * 1024 * 1024 * 1024)
        assert req.size == 10 * 1024 * 1024 * 1024


class TestCompleteUploadRequest:

    def test_valid_payload(self):
        req = CompleteUploadRequest(
            document_id="doc_1",
            object_key="documents/tenants/t1/documents/doc_1/report.pdf",
            name="report.pdf",
            mime_type="application/pdf",
            size=1024,
        )
        assert req.document_id == "doc_1"
        assert req.size == 1024
        assert req.etag is None

    def test_etag_optional(self):
        req = CompleteUploadRequest(
            document_id="doc_1",
            object_key="documents/tenants/t1/documents/doc_1/report.pdf",
            name="report.pdf",
            mime_type="application/pdf",
            size=1024,
            etag="abc123",
        )
        assert req.etag == "abc123"

    def test_size_must_be_at_least_1(self):
        with pytest.raises(ValidationError) as exc:
            CompleteUploadRequest(
                document_id="doc_1",
                object_key="key",
                name="f",
                mime_type="text/plain",
                size=0,
            )
        errors = exc.value.errors()
        assert any(e["loc"] == ("size",) for e in errors)

    def test_document_id_required(self):
        with pytest.raises(ValidationError):
            CompleteUploadRequest(
                object_key="key",
                name="f",
                mime_type="text/plain",
                size=1,
            )

    def test_object_key_required(self):
        with pytest.raises(ValidationError):
            CompleteUploadRequest(
                document_id="doc_1",
                name="f",
                mime_type="text/plain",
                size=1,
            )

    def test_name_required(self):
        with pytest.raises(ValidationError):
            CompleteUploadRequest(
                document_id="doc_1",
                object_key="key",
                mime_type="text/plain",
                size=1,
            )

    def test_mime_type_required(self):
        with pytest.raises(ValidationError):
            CompleteUploadRequest(
                document_id="doc_1",
                object_key="key",
                name="f",
                size=1,
            )
