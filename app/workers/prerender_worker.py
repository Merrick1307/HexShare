from __future__ import annotations

import logging
import os
from typing import Any

import asyncpg
from arq.connections import RedisSettings

from app.adapters import JWTTokenAdapter, NoopEventBus
from app.infra.factories import (
    ObjectStorageFactory,
    RenderedPageCacheFactory,
    StorageFactory,
    TaskQueueFactory,
)
from app.services import (
    DocumentProcessor,
    DocumentProcessingError,
    DocumentService,
    LinkService,
    ViewerService,
)


logger = logging.getLogger(__name__)


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    return value if value > 0 else default


async def _build_worker_viewer_service(ctx: dict[str, Any]) -> None:
    import app.infra.bootstrap  # noqa: F401

    pool = await asyncpg.create_pool(dsn=os.getenv("DATABASE_URL"))

    preferred_storage = os.getenv("HEXSHARE_STORAGE", "postgres")
    preferred_object_storage = os.getenv("HEXSHARE_OBJECT_STORAGE", "s3")
    preferred_rendered_page_cache = os.getenv("HEXSHARE_RENDERED_PAGE_CACHE", "inmemory")
    preferred_task_queue = os.getenv("HEXSHARE_TASK_QUEUE", "noop")

    storage = StorageFactory.create(preferred_storage, pool=pool)
    object_storage = ObjectStorageFactory.create(preferred_object_storage)
    rendered_page_cache = RenderedPageCacheFactory.create(preferred_rendered_page_cache)
    task_queue = TaskQueueFactory.create(preferred_task_queue)

    event_bus = NoopEventBus()
    token_adapter = JWTTokenAdapter()
    document_service = DocumentService(storage, event_bus)
    link_service = LinkService(storage, token_adapter, event_bus)
    document_processor = DocumentProcessor()
    viewer_service = ViewerService(
        storage=storage,
        object_storage=object_storage,
        rendered_page_cache=rendered_page_cache,
        task_queue=task_queue,
        document_processor=document_processor,
        document_service=document_service,
        link_service=link_service,
    )

    ctx["pool"] = pool
    ctx["storage"] = storage
    ctx["viewer_service"] = viewer_service


async def _close_worker_resources(ctx: dict[str, Any]) -> None:
    pool = ctx.get("pool")
    if pool is not None:
        await pool.close()


async def prerender_page(
    ctx: dict[str, Any],
    *,
    session_id: str,
    page_number: int,
    render_width: int | None,
) -> None:
    storage = ctx["storage"]
    viewer_service: ViewerService = ctx["viewer_service"]
    session = await storage.get_visitor_session_by_id(session_id=session_id)
    if session is None:
        logger.info(
            "Skipping prerender for missing session",
            extra={"session_id": session_id, "page_number": page_number, "render_width": render_width},
        )
        return None
    if session.ended_at is not None:
        logger.info(
            "Skipping prerender for closed session",
            extra={"session_id": session_id, "page_number": page_number, "render_width": render_width},
        )
        return None

    try:
        await viewer_service.render_document_page(
            session_id=session_id,
            page_number=page_number,
            render_width=render_width,
        )
    except ValueError as exc:
        if str(exc) in {"session_closed", "session_not_found", "revoked", "expired"}:
            logger.info(
                "Skipping prerender for inactive session state",
                extra={
                    "session_id": session_id,
                    "page_number": page_number,
                    "render_width": render_width,
                    "reason": str(exc),
                },
            )
            return None
        logger.exception(
            "Unexpected prerender value error",
            extra={"session_id": session_id, "page_number": page_number, "render_width": render_width},
        )
        raise
    except DocumentProcessingError as exc:
        if exc.code in {"page_out_of_range", "invalid_page_number", "page_image_view_not_supported"}:
            logger.info(
                "Skipping prerender for non-renderable page",
                extra={
                    "session_id": session_id,
                    "page_number": page_number,
                    "render_width": render_width,
                    "reason": exc.code,
                },
            )
            return None
        logger.exception(
            "Prerender document processing failed",
            extra={
                "session_id": session_id,
                "page_number": page_number,
                "render_width": render_width,
                "reason": exc.code,
            },
        )
        raise
    except Exception:
        logger.exception(
            "Prerender job failed",
            extra={"session_id": session_id, "page_number": page_number, "render_width": render_width},
        )
        raise


class WorkerSettings:
    functions = [prerender_page]
    on_startup = _build_worker_viewer_service
    on_shutdown = _close_worker_resources
    max_jobs = _env_int("HEXSHARE_ARQ_MAX_JOBS", max(1, min(4, os.cpu_count() or 1)))
    job_timeout = _env_float("HEXSHARE_ARQ_JOB_TIMEOUT_SECONDS", 300.0)
    redis_settings = RedisSettings.from_dsn(
        os.getenv("REDIS_URL", "redis://localhost:6379/0")
    )
