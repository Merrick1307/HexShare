from __future__ import annotations

import importlib
from dataclasses import dataclass
from html import escape
from pathlib import Path


@dataclass(frozen=True)
class DocumentProcessingError(Exception):
    code: str

    def __str__(self) -> str:
        return self.code


@dataclass(frozen=True)
class ProcessedDocument:
    content: bytes
    media_type: str
    filename: str
    source_media_type: str
    processing_applied: bool = False


@dataclass(frozen=True)
class ProcessingContext:
    document_id: str
    session_id: str
    filename: str
    source_media_type: str
    watermark_text: str | None = None
    download: bool = False


@dataclass(frozen=True)
class ViewPolicy:
    inline_view_supported: bool
    reason: str | None = None
    view_kind: str = "unsupported"


class DocumentProcessor:
    """
    Processes documents for delivery without changing source-of-truth storage.

    For now this is intentionally conservative: it preserves original bytes and
    defines the service seam where watermarking, rendering, and worker-backed
    transforms will be added later.
    """

    _PDF_MIME_TYPES = {"application/pdf"}
    _TEXT_MIME_TYPES = {
        "text/plain",
        "application/json",
        "application/xml",
        "text/xml",
        "text/csv",
    }
    _MARKDOWN_MIME_TYPES = {"text/markdown"}
    _CODE_MIME_TYPES = {
        "application/javascript",
        "text/javascript",
        "application/x-python-code",
        "text/x-python",
    }
    _TEXT_EXTENSIONS = {".txt", ".log", ".json", ".xml", ".csv"}
    _MARKDOWN_EXTENSIONS = {".md", ".markdown"}
    _CODE_EXTENSIONS = {
        ".py",
        ".js",
        ".ts",
        ".tsx",
        ".jsx",
        ".java",
        ".go",
        ".rs",
        ".c",
        ".cpp",
        ".h",
        ".hpp",
        ".sh",
        ".yaml",
        ".yml",
        ".toml",
        ".ini",
        ".sql",
    }
    _DOCX_EXTENSIONS = {".docx"}
    _DOCX_MIME_TYPES = {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }

    def _load_pdf_document_class(self):
        try:
            module = importlib.import_module("pdf_oxide")
        except ImportError:
            return None
        return getattr(module, "PdfDocument", None)

    def describe_view_policy(self, *, filename: str, source_media_type: str | None) -> ViewPolicy:
        context = ProcessingContext(
            document_id="",
            session_id="",
            filename=filename,
            source_media_type=source_media_type or "application/octet-stream",
        )
        kind = self._classify_kind(context=context)
        match kind:
            case "pdf":
                return ViewPolicy(inline_view_supported=True, view_kind="pdf")
            case "text":
                return ViewPolicy(inline_view_supported=True, view_kind="text")
            case "markdown":
                return ViewPolicy(inline_view_supported=True, view_kind="markdown")
            case "code":
                return ViewPolicy(inline_view_supported=True, view_kind="code")
            case "docx":
                return ViewPolicy(
                    inline_view_supported=False,
                    reason="inline_view_not_supported",
                    view_kind="docx",
                )
            case _:
                return ViewPolicy(
                    inline_view_supported=False,
                    reason="inline_view_not_supported",
                    view_kind="unsupported",
                )

    async def process_for_view(
        self,
        *,
        context: ProcessingContext,
        content: bytes,
    ) -> ProcessedDocument:
        kind = self._classify_kind(context=context)
        match kind:
            case "pdf":
                return await self._process_pdf(context=context, content=content)
            case "text":
                return await self._process_text_like(context=context, content=content)
            case "markdown":
                return await self._process_markdown(context=context, content=content)
            case "code":
                return await self._process_code(context=context, content=content)
            case "docx":
                return await self._process_docx_view(context=context, content=content)
            case _:
                return await self._process_unsupported_view(context=context, content=content)

    async def process_for_download(
        self,
        *,
        context: ProcessingContext,
        content: bytes,
    ) -> ProcessedDocument:
        kind = self._classify_kind(context=context)
        match kind:
            case "pdf":
                return await self._process_download_passthrough(context=context, content=content)
            case "text":
                return await self._process_download_passthrough(context=context, content=content)
            case "markdown":
                return await self._process_download_passthrough(context=context, content=content)
            case "code":
                return await self._process_download_passthrough(context=context, content=content)
            case "docx":
                return await self._process_download_passthrough(context=context, content=content)
            case _:
                return await self._process_download_passthrough(context=context, content=content)

    def _classify_kind(self, *, context: ProcessingContext) -> str:
        media_type = (context.source_media_type or "").split(";", 1)[0].strip().lower()
        suffix = Path(context.filename).suffix.lower()

        if media_type in self._PDF_MIME_TYPES or suffix == ".pdf":
            return "pdf"
        if media_type in self._DOCX_MIME_TYPES or suffix in self._DOCX_EXTENSIONS:
            return "docx"
        if media_type in self._MARKDOWN_MIME_TYPES or suffix in self._MARKDOWN_EXTENSIONS:
            return "markdown"
        if media_type in self._CODE_MIME_TYPES or suffix in self._CODE_EXTENSIONS:
            return "code"
        if media_type.startswith("text/") or media_type in self._TEXT_MIME_TYPES or suffix in self._TEXT_EXTENSIONS:
            return "text"
        return "unsupported"

    async def _process_pdf(
        self,
        *,
        context: ProcessingContext,
        content: bytes,
    ) -> ProcessedDocument:
        if not context.watermark_text:
            return self._build_passthrough_document(context=context, content=content)

        PdfDocument = self._load_pdf_document_class()
        if PdfDocument is None:
            return self._build_passthrough_document(context=context, content=content)

        document = PdfDocument.from_bytes(content)
        total_pages = document.page_count()

        for index in range(total_pages):
            page = document.page(index)
            x = max(24.0, float(page.width) * 0.08)
            y = max(24.0, float(page.height) * 0.05)
            page.add_text(context.watermark_text, x, y, 10.0)
            document.save_page(page)

        return ProcessedDocument(
            content=document.to_bytes(),
            media_type="application/pdf",
            filename=context.filename,
            source_media_type=context.source_media_type or "application/pdf",
            processing_applied=True,
        )

    async def _process_text_like(
        self,
        *,
        context: ProcessingContext,
        content: bytes,
    ) -> ProcessedDocument:
        return self._build_html_document(
            context=context,
            content=content,
            title=context.filename,
            heading=context.filename,
        )

    async def _process_markdown(
        self,
        *,
        context: ProcessingContext,
        content: bytes,
    ) -> ProcessedDocument:
        return self._build_html_document(
            context=context,
            content=content,
            title=context.filename,
            heading=f"{context.filename} (Markdown Preview)",
        )

    async def _process_code(
        self,
        *,
        context: ProcessingContext,
        content: bytes,
    ) -> ProcessedDocument:
        return self._build_html_document(
            context=context,
            content=content,
            title=context.filename,
            heading=f"{context.filename} (Code Preview)",
        )

    async def _process_docx_view(
        self,
        *,
        context: ProcessingContext,
        content: bytes,
    ) -> ProcessedDocument:
        raise DocumentProcessingError("inline_view_not_supported")

    async def _process_unsupported_view(
        self,
        *,
        context: ProcessingContext,
        content: bytes,
    ) -> ProcessedDocument:
        raise DocumentProcessingError("inline_view_not_supported")

    async def _process_download_passthrough(
        self,
        *,
        context: ProcessingContext,
        content: bytes,
    ) -> ProcessedDocument:
        return self._build_passthrough_document(context=context, content=content)

    def _build_passthrough_document(
        self,
        *,
        context: ProcessingContext,
        content: bytes,
    ) -> ProcessedDocument:
        return ProcessedDocument(
            content=content,
            media_type=context.source_media_type or "application/octet-stream",
            filename=context.filename,
            source_media_type=context.source_media_type or "application/octet-stream",
            processing_applied=False,
        )

    def _build_html_document(
        self,
        *,
        context: ProcessingContext,
        content: bytes,
        title: str,
        heading: str,
    ) -> ProcessedDocument:
        decoded = content.decode("utf-8", errors="replace")
        safe_text = escape(decoded)
        safe_title = escape(title)
        safe_heading = escape(heading)
        watermark = (
            f'<p class="watermark">{escape(context.watermark_text)}</p>'
            if context.watermark_text
            else ""
        )
        html = (
            "<!doctype html>"
            "<html><head>"
            f"<title>{safe_title}</title>"
            "<meta charset=\"utf-8\">"
            "<style>"
            "body{font-family:system-ui,sans-serif;margin:0;background:#fff;color:#111827;}"
            ".wrap{max-width:960px;margin:0 auto;padding:24px;}"
            ".watermark{font-size:12px;color:#6b7280;margin:0 0 16px;}"
            "h1{font-size:18px;margin:0 0 16px;}"
            "pre{white-space:pre-wrap;word-break:break-word;background:#f9fafb;border:1px solid #e5e7eb;padding:16px;margin:0;}"
            "</style></head><body>"
            f"<main class=\"wrap\">{watermark}<h1>{safe_heading}</h1><pre>{safe_text}</pre></main>"
            "</body></html>"
        ).encode("utf-8")
        return ProcessedDocument(
            content=html,
            media_type="text/html; charset=utf-8",
            filename=context.filename,
            source_media_type=context.source_media_type or "application/octet-stream",
            processing_applied=True,
        )
