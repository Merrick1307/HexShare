from __future__ import annotations

import pytest

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
async def test_process_for_view_passes_pdf_through():
    processor = DocumentProcessor()

    result = await processor.process_for_view(
        context=_context(filename="report.pdf", source_media_type="application/pdf"),
        content=b"%PDF-1.7",
    )

    assert result.content == b"%PDF-1.7"
    assert result.media_type == "application/pdf"
    assert result.processing_applied is False


@pytest.mark.asyncio
async def test_process_for_view_watermarks_pdf_when_backend_is_available(monkeypatch):
    processor = DocumentProcessor()

    class FakePage:
        def __init__(self) -> None:
            self.width = 600.0
            self.height = 800.0
            self.calls: list[tuple[str, float, float, float]] = []

        def add_text(self, text: str, x: float, y: float, font_size: float = 12.0) -> None:
            self.calls.append((text, x, y, font_size))

    class FakePdfDocument:
        saved_pages: list[FakePage] = []

        def __init__(self, content: bytes) -> None:
            self.content = content
            self.pages = [FakePage(), FakePage()]

        @classmethod
        def from_bytes(cls, content: bytes):
            return cls(content)

        def page_count(self) -> int:
            return len(self.pages)

        def page(self, index: int) -> FakePage:
            return self.pages[index]

        def save_page(self, page: FakePage) -> None:
            self.saved_pages.append(page)

        def to_bytes(self) -> bytes:
            return b"%PDF-watermarked"

    monkeypatch.setattr(processor, "_load_pdf_document_class", lambda: FakePdfDocument)

    result = await processor.process_for_view(
        context=_context(filename="report.pdf", source_media_type="application/pdf"),
        content=b"%PDF-1.7",
    )

    assert result.content == b"%PDF-watermarked"
    assert result.media_type == "application/pdf"
    assert result.processing_applied is True
    assert len(FakePdfDocument.saved_pages) == 2
    for page in FakePdfDocument.saved_pages:
        assert page.calls
        assert page.calls[0][0] == "HexShare - viewer@example.com"


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
