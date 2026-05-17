from __future__ import annotations

import asyncio
import importlib
import io
import time
from collections import OrderedDict
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


@dataclass(frozen=True)
class PdfPreview:
    page_count: int


@dataclass(frozen=True)
class RenderedPage:
    content: bytes
    media_type: str
    page_number: int
    total_pages: int
    width: int
    height: int


@dataclass
class _CachedPdfDocument:
    document: object
    lock: asyncio.Lock


class _PdfDocumentCache:
    def __init__(self, *, maxsize: int = 20, ttl_seconds: float = 300.0) -> None:
        self._cache: OrderedDict[str, tuple[_CachedPdfDocument, float]] = OrderedDict()
        self._maxsize = maxsize
        self._ttl_seconds = ttl_seconds
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> _CachedPdfDocument | None:
        async with self._lock:
            now = time.monotonic()
            entry = self._cache.get(key)
            if entry is None:
                return None
            value, expires_at = entry
            if now >= expires_at:
                del self._cache[key]
                return None
            self._cache.move_to_end(key)
            return value

    async def set(self, key: str, value: _CachedPdfDocument) -> None:
        async with self._lock:
            self._cache[key] = (value, time.monotonic() + self._ttl_seconds)
            self._cache.move_to_end(key)
            while len(self._cache) > self._maxsize:
                self._cache.popitem(last=False)


class DocumentProcessor:
    """
    Processes documents for delivery without changing source-of-truth storage.

    Inline PDF viewing is handled as rendered page images so the watermark is
    baked into the delivered content instead of being separable client-side.
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
    _WATERMARK_MAX_LENGTH = 96
    _PDF_RENDER_WIDTH_DEFAULT = 1400
    _PDF_RENDER_WIDTH_MIN = 400
    _PDF_RENDER_WIDTH_MAX = 2200
    _IMAGE_MIME_PREFIX = "image/"
    _IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}

    def __init__(self, *, pdf_cache_size: int = 20, pdf_cache_ttl: float = 300.0) -> None:
        self._pdf_cache = _PdfDocumentCache(maxsize=pdf_cache_size, ttl_seconds=pdf_cache_ttl)

    def _load_pdf_document_class(self):
        try:
            module = importlib.import_module("pdf_oxide")
        except ImportError:
            return None
        return getattr(module, "PdfDocument", None)

    def _load_pillow_modules(self):
        try:
            from PIL import Image, ImageDraw, ImageFont
        except ImportError:
            return None
        return Image, ImageDraw, ImageFont

    def _supports_pdf_inline(self) -> bool:
        return self._load_pdf_document_class() is not None and self._load_pillow_modules() is not None

    def _supports_image_inline(self) -> bool:
        return self._load_pillow_modules() is not None

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
                if self._supports_pdf_inline():
                    return ViewPolicy(inline_view_supported=True, view_kind="pdf")
                return ViewPolicy(
                    inline_view_supported=False,
                    reason="inline_view_backend_unavailable",
                    view_kind="pdf",
                )
            case "text":
                return ViewPolicy(inline_view_supported=True, view_kind="text")
            case "markdown":
                return ViewPolicy(inline_view_supported=True, view_kind="markdown")
            case "code":
                return ViewPolicy(inline_view_supported=True, view_kind="code")
            case "image":
                if self._supports_image_inline():
                    return ViewPolicy(inline_view_supported=True, view_kind="image")
                return ViewPolicy(
                    inline_view_supported=False,
                    reason="inline_view_backend_unavailable",
                    view_kind="image",
                )
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
            case "image":
                return await self._process_image(context=context, content=content)
            case "docx":
                return await self._process_docx_view(context=context, content=content)
            case _:
                return await self._process_unsupported_view(context=context, content=content)

    async def describe_pdf_preview(self, *, content: bytes, cache_key: str | None = None) -> PdfPreview:
        PdfDocument = self._load_pdf_document_class()
        if PdfDocument is None:
            raise DocumentProcessingError("inline_view_backend_unavailable")

        cached_document = await self._get_pdf_document(content=content, cache_key=cache_key, PdfDocument=PdfDocument)
        async with cached_document.lock:
            page_count = await asyncio.to_thread(self._get_pdf_page_count_sync, document=cached_document.document)
        return PdfPreview(page_count=page_count)

    async def render_pdf_page(
        self,
        *,
        context: ProcessingContext,
        content: bytes,
        page_number: int,
        render_width: int | None = None,
        cache_key: str | None = None,
    ) -> RenderedPage:
        if page_number < 1:
            raise DocumentProcessingError("invalid_page_number")

        PdfDocument = self._load_pdf_document_class()
        pillow_modules = self._load_pillow_modules()
        if PdfDocument is None or pillow_modules is None:
            raise DocumentProcessingError("inline_view_backend_unavailable")

        Image, ImageDraw, ImageFont = pillow_modules
        cached_document = await self._get_pdf_document(content=content, cache_key=cache_key, PdfDocument=PdfDocument)

        target_width = self._clamp_render_width(render_width)
        async with cached_document.lock:
            return await asyncio.to_thread(
                self._render_pdf_page_sync,
                document=cached_document.document,
                page_number=page_number,
                target_width=target_width,
                watermark_text=context.watermark_text,
                Image=Image,
                ImageDraw=ImageDraw,
                ImageFont=ImageFont,
            )

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
        if media_type.startswith(self._IMAGE_MIME_PREFIX) or suffix in self._IMAGE_EXTENSIONS:
            return "image"
        if media_type.startswith("text/") or media_type in self._TEXT_MIME_TYPES or suffix in self._TEXT_EXTENSIONS:
            return "text"
        return "unsupported"

    async def _process_pdf(
        self,
        *,
        context: ProcessingContext,
        content: bytes,
    ) -> ProcessedDocument:
        raise DocumentProcessingError("page_image_view_required")

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

    async def _process_image(
        self,
        *,
        context: ProcessingContext,
        content: bytes,
    ) -> ProcessedDocument:
        pillow_modules = self._load_pillow_modules()
        if pillow_modules is None:
            raise DocumentProcessingError("inline_view_backend_unavailable")

        Image, ImageDraw, ImageFont = pillow_modules
        image = Image.open(io.BytesIO(content)).convert("RGBA")
        watermarked = self._apply_pdf_image_watermark(
            image=image,
            watermark_text=context.watermark_text,
            Image=Image,
            ImageDraw=ImageDraw,
            ImageFont=ImageFont,
        )
        output = io.BytesIO()
        watermarked.save(output, format="PNG", optimize=True)
        return ProcessedDocument(
            content=output.getvalue(),
            media_type="image/png",
            filename=context.filename,
            source_media_type=context.source_media_type or "application/octet-stream",
            processing_applied=True,
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

    def _normalize_watermark_text(self, watermark_text: str) -> str:
        compact = " ".join(watermark_text.split())
        if len(compact) <= self._WATERMARK_MAX_LENGTH:
            return compact
        return f"{compact[: self._WATERMARK_MAX_LENGTH - 3].rstrip()}..."

    async def _get_pdf_document(self, *, content: bytes, cache_key: str | None, PdfDocument):
        if cache_key:
            cached = await self._pdf_cache.get(cache_key)
            if cached is not None:
                return cached
        document = await asyncio.to_thread(PdfDocument.from_bytes, content)
        cached_document = _CachedPdfDocument(document=document, lock=asyncio.Lock())
        if cache_key:
            await self._pdf_cache.set(cache_key, cached_document)
        return cached_document

    def _get_pdf_page_count_sync(self, *, document) -> int:
        return int(document.page_count())

    def _render_pdf_page_sync(
        self,
        *,
        document,
        page_number: int,
        target_width: int,
        watermark_text: str | None,
        Image,
        ImageDraw,
        ImageFont,
    ) -> RenderedPage:
        total_pages = int(document.page_count())
        if page_number > total_pages:
            raise DocumentProcessingError("page_out_of_range")
        zero_based_page = page_number - 1
        page = document.page(zero_based_page)
        target_height = self._calculate_target_height(
            page_width=float(page.width),
            page_height=float(page.height),
            target_width=target_width,
        )
        rendered_bytes = document.render_page_fit(
            zero_based_page,
            target_width,
            target_height,
            format="png",
            background=(1.0, 1.0, 1.0, 1.0),
            transparent=False,
        )
        image = Image.open(io.BytesIO(rendered_bytes)).convert("RGBA")
        watermarked = self._apply_pdf_image_watermark(
            image=image,
            watermark_text=watermark_text,
            Image=Image,
            ImageDraw=ImageDraw,
            ImageFont=ImageFont,
        )
        output = io.BytesIO()
        watermarked.save(output, format="PNG", optimize=True)
        return RenderedPage(
            content=output.getvalue(),
            media_type="image/png",
            page_number=page_number,
            total_pages=total_pages,
            width=watermarked.width,
            height=watermarked.height,
        )

    def _clamp_render_width(self, render_width: int | None) -> int:
        requested = render_width or self._PDF_RENDER_WIDTH_DEFAULT
        return max(self._PDF_RENDER_WIDTH_MIN, min(int(requested), self._PDF_RENDER_WIDTH_MAX))

    def _calculate_target_height(self, *, page_width: float, page_height: float, target_width: int) -> int:
        if page_width <= 0 or page_height <= 0:
            return target_width
        ratio = page_height / page_width
        return max(1, int(round(target_width * ratio)))

    def _apply_pdf_image_watermark(self, *, image, watermark_text: str | None, Image, ImageDraw, ImageFont):
        if not watermark_text:
            return image

        overlay = self._build_diagonal_watermark_overlay(
            width=image.width,
            height=image.height,
            watermark_text=self._normalize_watermark_text(watermark_text),
            Image=Image,
            ImageDraw=ImageDraw,
            ImageFont=ImageFont,
        )
        return Image.alpha_composite(image, overlay)

    def _build_diagonal_watermark_overlay(self, *, width: int, height: int, watermark_text: str, Image, ImageDraw, ImageFont):
        pattern_width = max(width * 2, 1)
        pattern_height = max(height * 2, 1)
        pattern = Image.new("RGBA", (pattern_width, pattern_height), (255, 255, 255, 0))
        draw = ImageDraw.Draw(pattern)
        font_size = self._watermark_font_size(width=width, height=height)
        font = self._load_watermark_font(ImageFont=ImageFont, font_size=font_size)
        text_bbox = draw.textbbox((0, 0), watermark_text, font=font)
        text_width = max(1, text_bbox[2] - text_bbox[0])
        text_height = max(1, text_bbox[3] - text_bbox[1])
        spacing_x = int(text_width + (font_size * 1.1))
        spacing_y = int(text_height + (font_size * 1.8))
        fill = (75, 75, 75, 46)

        start_y = -pattern_height // 3
        end_y = pattern_height + (pattern_height // 3)
        start_x = -pattern_width // 3
        end_x = pattern_width + (pattern_width // 3)
        for y in range(start_y, end_y, spacing_y):
            for x in range(start_x, end_x, spacing_x):
                draw.text((x, y), watermark_text, font=font, fill=fill)

        rotated = pattern.rotate(-32, expand=True, resample=Image.Resampling.BICUBIC)
        left = max(0, (rotated.width - width) // 2)
        top = max(0, (rotated.height - height) // 2)
        cropped = rotated.crop((left, top, left + width, top + height))
        if cropped.size != (width, height):
            return cropped.resize((width, height), resample=Image.Resampling.BICUBIC)
        return cropped

    def _watermark_font_size(self, *, width: int, height: int) -> int:
        return max(42, min(110, int(min(width, height) * 0.085)))

    def _load_watermark_font(self, *, ImageFont, font_size: int):
        font_candidates = (
            "arial.ttf",
            "DejaVuSans.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
            "C:\\Windows\\Fonts\\arial.ttf",
        )
        for candidate in font_candidates:
            try:
                return ImageFont.truetype(candidate, font_size)
            except OSError:
                continue
        return ImageFont.load_default()

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
