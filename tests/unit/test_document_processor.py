from __future__ import annotations

import io

import pytest
from PIL import Image

from app.services.document_processor import DocumentProcessingError, DocumentProcessor, ProcessingContext


def _context(*, filename: str, source_media_type: str, watermark_text: str | None = "HexShare - viewer@example.com") -> ProcessingContext:
    return ProcessingContext(
        document_id="doc-1",
        session_id="vs-1",
        filename=filename,
        source_media_type=source_media_type,
        watermark_text=watermark_text,
        download=False,
    )


@pytest.mark.asyncio
async def test_process_for_view_requires_page_image_mode_for_pdf():
    processor = DocumentProcessor()

    with pytest.raises(DocumentProcessingError, match="page_image_view_required"):
        await processor.process_for_view(
            context=_context(filename="report.pdf", source_media_type="application/pdf"),
            content=b"%PDF-1.7",
        )


@pytest.mark.asyncio
async def test_describe_pdf_preview_reports_page_count(monkeypatch):
    processor = DocumentProcessor()

    class FakePdfDocument:
        @classmethod
        def from_bytes(cls, content: bytes):
            return cls()

        def page_count(self) -> int:
            return 3

    monkeypatch.setattr(processor, "_load_pdf_document_class", lambda: FakePdfDocument)

    preview = await processor.describe_pdf_preview(content=b"%PDF-1.7")

    assert preview.page_count == 3


@pytest.mark.asyncio
async def test_process_for_view_renders_image_as_png():
    processor = DocumentProcessor()
    image = Image.new("RGB", (120, 80), (255, 255, 255))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")

    result = await processor.process_for_view(
        context=_context(filename="diagram.png", source_media_type="image/png"),
        content=buffer.getvalue(),
    )

    assert result.media_type == "image/png"
    assert result.processing_applied is True
    output = Image.open(io.BytesIO(result.content))
    assert output.size == (120, 80)


@pytest.mark.asyncio
async def test_render_pdf_page_returns_watermarked_png(monkeypatch):
    processor = DocumentProcessor()

    class FakePage:
        width = 612.0
        height = 792.0

    class FakePdfDocument:
        @classmethod
        def from_bytes(cls, content: bytes):
            return cls()

        def page_count(self) -> int:
            return 2

        def page(self, index: int) -> FakePage:
            return FakePage()

        def render_page_fit(self, page: int, width: int, height: int, **kwargs) -> bytes:
            image = Image.new("RGBA", (width, height), (255, 255, 255, 255))
            buffer = io.BytesIO()
            image.save(buffer, format="PNG")
            return buffer.getvalue()

    monkeypatch.setattr(processor, "_load_pdf_document_class", lambda: FakePdfDocument)

    result = await processor.render_pdf_page(
        context=_context(filename="report.pdf", source_media_type="application/pdf"),
        content=b"%PDF-1.7",
        page_number=1,
        render_width=1000,
    )

    assert result.media_type == "image/png"
    assert result.page_number == 1
    assert result.total_pages == 2
    assert result.width == 1000
    assert result.height > 1000
    output = Image.open(io.BytesIO(result.content)).convert("RGBA")
    assert output.size == (result.width, result.height)
    assert output.getbbox() is not None


@pytest.mark.asyncio
async def test_render_pdf_page_rejects_out_of_range_pages(monkeypatch):
    processor = DocumentProcessor()

    class FakePage:
        width = 612.0
        height = 792.0

    class FakePdfDocument:
        @classmethod
        def from_bytes(cls, content: bytes):
            return cls()

        def page_count(self) -> int:
            return 1

        def page(self, index: int) -> FakePage:
            return FakePage()

    monkeypatch.setattr(processor, "_load_pdf_document_class", lambda: FakePdfDocument)

    with pytest.raises(DocumentProcessingError, match="page_out_of_range"):
        await processor.render_pdf_page(
            context=_context(filename="report.pdf", source_media_type="application/pdf"),
            content=b"%PDF-1.7",
            page_number=2,
        )


def test_build_diagonal_watermark_overlay_matches_page_dimensions():
    processor = DocumentProcessor()
    ImageModule, ImageDraw, ImageFont = processor._load_pillow_modules()

    overlay = processor._build_diagonal_watermark_overlay(
        width=1200,
        height=1600,
        watermark_text="HexShare - viewer@example.com",
        Image=ImageModule,
        ImageDraw=ImageDraw,
        ImageFont=ImageFont,
    )

    assert overlay.size == (1200, 1600)


@pytest.mark.asyncio
async def test_process_for_view_renders_text_like_as_html():
    processor = DocumentProcessor()

    result = await processor.process_for_view(
        context=_context(filename="notes.txt", source_media_type="text/plain"),
        content=b"hello <team>",
    )

    assert result.media_type == "text/html; charset=utf-8"
    assert result.processing_applied is True
    assert b"hello &lt;team&gt;" in result.content
    assert b"HexShare - viewer@example.com" in result.content


@pytest.mark.asyncio
async def test_process_for_view_renders_code_as_html():
    processor = DocumentProcessor()

    result = await processor.process_for_view(
        context=_context(filename="main.py", source_media_type="text/x-python"),
        content=b"print('hello')",
    )

    assert result.media_type == "text/html; charset=utf-8"
    assert b"Code Preview" in result.content


@pytest.mark.asyncio
async def test_process_for_view_rejects_docx_for_inline_viewing():
    processor = DocumentProcessor()

    with pytest.raises(DocumentProcessingError, match="inline_view_not_supported"):
        await processor.process_for_view(
            context=_context(
                filename="report.docx",
                source_media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ),
            content=b"docx-bytes",
        )


@pytest.mark.asyncio
async def test_process_for_download_keeps_original_docx_bytes():
    processor = DocumentProcessor()
    context = _context(
        filename="report.docx",
        source_media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )

    result = await processor.process_for_download(
        context=context,
        content=b"docx-bytes",
    )

    assert result.content == b"docx-bytes"
    assert result.media_type == context.source_media_type
    assert result.processing_applied is False


def test_describe_view_policy_marks_docx_as_not_inline_viewable():
    processor = DocumentProcessor()

    policy = processor.describe_view_policy(
        filename="report.docx",
        source_media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )

    assert policy.inline_view_supported is False
    assert policy.view_kind == "docx"
    assert policy.reason == "inline_view_not_supported"


def test_describe_view_policy_marks_code_as_inline_viewable():
    processor = DocumentProcessor()

    policy = processor.describe_view_policy(
        filename="main.py",
        source_media_type="text/x-python",
    )

    assert policy.inline_view_supported is True
    assert policy.view_kind == "code"


def test_describe_view_policy_marks_images_as_inline_viewable():
    processor = DocumentProcessor()

    policy = processor.describe_view_policy(
        filename="diagram.png",
        source_media_type="image/png",
    )

    assert policy.inline_view_supported is True
    assert policy.view_kind == "image"
