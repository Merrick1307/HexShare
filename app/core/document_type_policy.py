"""Authoritative accepted-document and protection-profile policy."""
from __future__ import annotations

import importlib
from dataclasses import dataclass
from pathlib import Path


UNSUPPORTED_DOCUMENT_TYPE = "unsupported_document_type"
CORRUPT_PDF = "corrupt_pdf"
PASSWORD_PROTECTED_PDF = "password_protected_pdf"


@dataclass(frozen=True)
class AcceptedDocumentType:
    extensions: tuple[str, ...]
    mime_types: tuple[str, ...]
    profile: str


@dataclass(frozen=True)
class ProtectionDescriptor:
    profile: str
    label: str
    inline_view_supported: bool
    watermark_mode: str | None
    page_activity: bool
    download_required: bool
    reason: str | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "profile": self.profile,
            "label": self.label,
            "inline_view_supported": self.inline_view_supported,
            "watermark_mode": self.watermark_mode,
            "page_activity": self.page_activity,
            "download_required": self.download_required,
            "reason": self.reason,
        }


ACCEPTED_DOCUMENT_TYPES: tuple[AcceptedDocumentType, ...] = (
    AcceptedDocumentType((".pdf",), ("application/pdf",), "strongest"),
    AcceptedDocumentType((".doc",), ("application/msword",), "download_only"),
    AcceptedDocumentType(
        (".docx",),
        ("application/vnd.openxmlformats-officedocument.wordprocessingml.document",),
        "download_only",
    ),
    AcceptedDocumentType((".xls",), ("application/vnd.ms-excel",), "download_only"),
    AcceptedDocumentType(
        (".xlsx",),
        ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",),
        "download_only",
    ),
    AcceptedDocumentType((".ppt",), ("application/vnd.ms-powerpoint",), "download_only"),
    AcceptedDocumentType(
        (".pptx",),
        ("application/vnd.openxmlformats-officedocument.presentationml.presentation",),
        "download_only",
    ),
    AcceptedDocumentType((".txt",), ("text/plain",), "protected_preview"),
    AcceptedDocumentType((".csv",), ("text/csv", "application/csv"), "protected_preview"),
    AcceptedDocumentType((".md",), ("text/markdown", "text/plain"), "protected_preview"),
    AcceptedDocumentType((".png",), ("image/png",), "protected_preview"),
    AcceptedDocumentType((".jpg", ".jpeg"), ("image/jpeg",), "protected_preview"),
    AcceptedDocumentType((".webp",), ("image/webp",), "protected_preview"),
)

ACCEPTED_EXTENSIONS = tuple(
    extension for item in ACCEPTED_DOCUMENT_TYPES for extension in item.extensions
)
ACCEPT_ATTRIBUTE = ",".join(ACCEPTED_EXTENSIONS)


def _normalized_mime_type(content_type: str | None) -> str:
    return (content_type or "").split(";", 1)[0].strip().lower()


def accepted_type_for(filename: str, content_type: str | None) -> AcceptedDocumentType:
    extension = Path((filename or "").strip()).suffix.lower()
    declared = _normalized_mime_type(content_type)
    item = next(
        (candidate for candidate in ACCEPTED_DOCUMENT_TYPES if extension in candidate.extensions),
        None,
    )
    if item is None:
        raise ValueError(UNSUPPORTED_DOCUMENT_TYPE)
    # Browsers legitimately omit a MIME type for some business documents.
    if declared and declared != "application/octet-stream" and declared not in item.mime_types:
        raise ValueError(UNSUPPORTED_DOCUMENT_TYPE)
    return item


def normalized_content_type(filename: str, content_type: str | None) -> str:
    item = accepted_type_for(filename, content_type)
    declared = _normalized_mime_type(content_type)
    return declared if declared and declared != "application/octet-stream" else item.mime_types[0]


def _pdf_inline_available() -> bool:
    try:
        pdf_module = importlib.import_module("pdf_oxide")
        pillow_module = importlib.import_module("PIL")
    except ImportError:
        return False
    return bool(getattr(pdf_module, "PdfDocument", None) and pillow_module)


def _image_inline_available() -> bool:
    try:
        importlib.import_module("PIL")
    except ImportError:
        return False
    return True


def describe_document_protection(
    filename: str,
    content_type: str | None,
) -> ProtectionDescriptor:
    try:
        item = accepted_type_for(filename, content_type)
    except ValueError:
        return ProtectionDescriptor(
            profile="download_only",
            label="Download only",
            inline_view_supported=False,
            watermark_mode=None,
            page_activity=False,
            download_required=True,
            reason=UNSUPPORTED_DOCUMENT_TYPE,
        )

    extension = Path(filename).suffix.lower()
    if item.profile == "strongest":
        available = _pdf_inline_available()
        return ProtectionDescriptor(
            profile="strongest" if available else "download_only",
            label="Strongest protection" if available else "Download only",
            inline_view_supported=available,
            watermark_mode="pixel_baked" if available else None,
            page_activity=available,
            download_required=not available,
            reason=None if available else "inline_view_backend_unavailable",
        )
    if item.profile == "protected_preview":
        available = extension not in {".png", ".jpg", ".jpeg", ".webp"} or _image_inline_available()
        return ProtectionDescriptor(
            profile="protected_preview" if available else "download_only",
            label="Protected preview" if available else "Download only",
            inline_view_supported=available,
            watermark_mode="rendered" if available else None,
            page_activity=False,
            download_required=not available,
            reason=None if available else "inline_view_backend_unavailable",
        )
    return ProtectionDescriptor(
        profile="download_only",
        label="Download only",
        inline_view_supported=False,
        watermark_mode=None,
        page_activity=False,
        download_required=True,
        reason="inline_view_not_supported",
    )


def validate_pdf_bytes(content: bytes) -> None:
    if not content.startswith(b"%PDF"):
        raise ValueError(CORRUPT_PDF)
    try:
        module = importlib.import_module("pdf_oxide")
    except ImportError:
        # The deployment cannot claim strongest protection, but the signature
        # check still prevents arbitrary content being mislabeled as a PDF.
        return
    pdf_document = getattr(module, "PdfDocument", None)
    if pdf_document is None:
        return
    try:
        document = pdf_document.from_bytes(content)
        page_count = int(document.page_count())
        if page_count < 1:
            raise ValueError(CORRUPT_PDF)
    except Exception as exc:
        if isinstance(exc, ValueError) and str(exc) == CORRUPT_PDF:
            raise
        message = str(exc).lower()
        if "password" in message or "encrypted" in message:
            raise ValueError(PASSWORD_PROTECTED_PDF) from exc
        raise ValueError(CORRUPT_PDF) from exc
