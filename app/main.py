"""
Application entry point for HexShare.

This module exposes a ``create_app`` function that returns a configured
FastAPI application.  It wires together the API routers, dependency
injection, and middleware necessary to run HexShare.  The function
accepts optional parameters to inject custom implementations of ports or
override settings at runtime, which makes it easier to test and to
adapt for different deployment environments.

Usage example::

    from app.main import create_app
    import uvicorn

    app = create_app()
    uvicorn.run(app, host="0.0.0.0", port=8000)

If run directly (e.g. ``python -m app.main``), the app will be
served using Uvicorn on the default host and port.
"""
from __future__ import annotations

from fastapi import FastAPI

from app.api.router import api_router
from app.auth.tenant_auth import TenantAuthDependency
from app.auth.share_token_auth import ShareTokenDependency
from app.ports.storage_port import StoragePort
from app.ports.token_port import TokenPort
from app.ports import EventBusPort
from app.services import DocumentService
from app.services import LinkService
from app.services import AnalyticsService


def create_app(
    *,
    storage: StoragePort | None = None,
    token_port: TokenPort | None = None,
    event_bus: EventBusPort | None = None,
) -> FastAPI:
    """Create and configure the FastAPI application.

    Parameters
    ----------
    storage:
        Optional custom implementation of :class:`~app.ports.StoragePort`.
        If not provided, a default in‑memory storage will be used.  In a
        production deployment this should be replaced with a persistent
        storage adapter such as an S3 implementation.

    token_port:
        Optional custom implementation of :class:`~app.ports.TokenPort`.
        The default implementation uses PyJWT and symmetrical keys for
        demonstration; a real deployment should use asymmetric keys and
        integrate with HexIAM for tenant user authentication.

    event_bus:
        Optional implementation of :class:`~app.ports.EventBusPort`.
        This port is used to publish analytics and audit events.  The
        default implementation is a no‑op; a production system would
        likely use Redis Streams or Kafka.

    Returns
    -------
    FastAPI
        A configured application ready to run.
    """
    app = FastAPI(title="HexShare", version="0.1.0")

    # Dependency injection for ports.  If none provided, defaults
    # instantiate simple in‑memory versions.  The event bus defaults
    # to a no‑op stub.
    from app.adapters import MemoryStorage
    from app.adapters import JWTTokenAdapter
    from app.adapters import NoopEventBus

    storage_impl = storage or MemoryStorage()
    token_impl = token_port or JWTTokenAdapter()
    event_bus_impl = event_bus or NoopEventBus()

    # Instantiate domain services
    document_service = DocumentService(storage_impl, event_bus_impl)
    link_service = LinkService(storage_impl, token_impl, event_bus_impl)
    analytics_service = AnalyticsService(storage_impl)

    # Inject dependencies into the API router
    app.include_router(
        api_router(
            document_service=document_service,
            link_service=link_service,
            analytics_service=analytics_service,
            tenant_auth=TenantAuthDependency(token_impl),
            share_auth=ShareTokenDependency(token_impl),
        ),
        prefix="/api/v1",
    )

    return app


if __name__ == "__main__":
    import uvicorn  # type: ignore[import]

    app = create_app()
    uvicorn.run(app, host="0.0.0.0", port=8000)
