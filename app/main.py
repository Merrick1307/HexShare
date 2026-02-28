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

import os
from contextlib import asynccontextmanager

import asyncpg
from fastapi import FastAPI

from app.adapters import NoopEventBus, JWTTokenAdapter
from app.adapters.authz.claims import ClaimsAuthorizer
from app.api.router import api_router
from app.auth.tenant_auth import TenantAuthDependency
from app.auth.share_token_auth import ShareTokenDependency
from app.infra.factories import StorageFactory, AccessControlFactory, PolicyEvaluatorRegistry, AuthenticatorFactory
from app.services import DocumentService
from app.services import LinkService
from app.services import AnalyticsService


@asynccontextmanager
async def lifespan(app: FastAPI):
    dp_pool = await asyncpg.create_pool(dsn=os.getenv("DATABASE_URL"))

    evaluator_name = os.getenv("HEXSHARE_POLICY_EVAL", "hexiam_bitmask")
    preferred_storage = os.getenv("HEXSHARE_STORAGE", "postgres")
    preferred_access_control = os.getenv("HEXSHARE_ACCESS_CONTROL", "hybrid")
    preferred_authenticator = os.getenv("HEXSHARE_AUTHENTICATOR", "hexiam")

    evaluator = PolicyEvaluatorRegistry.create(evaluator_name)
    authorizer = ClaimsAuthorizer(evaluator=evaluator)
    authenticator = AuthenticatorFactory.create(preferred_authenticator)

    persistence_layer = StorageFactory.create(preferred_storage, pool=dp_pool)

    access_control = AccessControlFactory.create(
        preferred_access_control,
        authorizer=authorizer,
        authenticator=authenticator,
        iam_url=os.getenv("HEXIAM_URL", "http://localhost:8000"),
        client_id=os.getenv("HEXSHARE_PDP_CLIENT_ID", ""),
        client_secret=os.getenv("HEXSHARE_PDP_CLIENT_SECRET", ""),
    )

    token_adapter = JWTTokenAdapter()
    event_bus = NoopEventBus()

    app.state.pool = dp_pool
    app.state.storage = persistence_layer
    app.state.token_adapter = token_adapter
    app.state.event_bus = event_bus
    app.state.document_service = DocumentService(persistence_layer, event_bus)
    app.state.link_service = LinkService(persistence_layer, token_adapter, event_bus)
    app.state.analytics_service = AnalyticsService(persistence_layer)
    app.state.access_control = access_control
    app.state.tenant_auth = TenantAuthDependency(authenticator=app.state.access_control)
    app.state.share_auth = ShareTokenDependency(token_port=token_adapter)

    yield

    await dp_pool.close()


def create_app(
    *args,
    **kwargs
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
    app = FastAPI(title="HexShare", version="0.1.0", lifespan=lifespan)

    # Inject dependencies into the API router
    app.include_router(
        api_router(),
        prefix="/api/v1",
    )

    return app


if __name__ == "__main__":
    import uvicorn  # type: ignore[import]

    app = create_app()
    uvicorn.run(app, host="0.0.0.0", port=8000)
