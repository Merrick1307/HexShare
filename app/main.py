"""
Application entry point for HexShare.
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager

import asyncpg
from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware

from app.adapters import NoopEventBus, JWTTokenAdapter
from app.adapters.authz.hex_iam import HexIAMAuthorizer
from app.adapters.oidc.hexiam_client import HexIAMOIDCClient
from app.api.auth_oidc import router as auth_oidc_router
from app.api.router import api_router
from app.api.uploads import router as uploads_router
from app.api.user import router as user_router
from app.auth.share_token_auth import ShareTokenDependency
from app.auth.tenant_auth import TenantAuthDependency
from app.infra.factories import (
    AccessControlFactory,
    AuthenticatorFactory,
    ObjectStorageFactory,
    StorageFactory,
)
from app.services import AnalyticsService, DocumentService, LinkService, UploadService, ViewerService


@asynccontextmanager
async def lifespan(fastapi_app: FastAPI):
    dp_pool = await asyncpg.create_pool(dsn=os.getenv("DATABASE_URL"))

    preferred_storage = os.getenv("HEXSHARE_STORAGE", "postgres")
    preferred_access_control = os.getenv("HEXSHARE_ACCESS_CONTROL", "hybrid")
    preferred_authenticator = os.getenv("HEXSHARE_AUTHENTICATOR", "hexiam")
    preferred_object_storage = os.getenv("HEXSHARE_OBJECT_STORAGE", "cloudinary")

    import app.infra.bootstrap  # noqa: F401

    authorizer = HexIAMAuthorizer()
    authenticator = AuthenticatorFactory.create(preferred_authenticator)

    persistence_layer = StorageFactory.create(preferred_storage, pool=dp_pool)
    object_storage = ObjectStorageFactory.create(preferred_object_storage)

    access_control = AccessControlFactory.create(
        preferred_access_control,
        authorizer=authorizer,
        authenticator=authenticator,
        iam_url="http://host.docker.internal:8000",
        client_id=os.getenv("HEXSHARE_PDP_CLIENT_ID", ""),
        client_secret=os.getenv("HEXSHARE_PDP_CLIENT_SECRET", ""),
    )

    token_adapter = JWTTokenAdapter()
    event_bus = NoopEventBus()
    document_service = DocumentService(persistence_layer, event_bus)
    link_service = LinkService(persistence_layer, token_adapter, event_bus)
    upload_service = UploadService(
        metadata_storage=persistence_layer,
        object_storage=object_storage,
        document_service=document_service,
    )
    viewer_service = ViewerService(
        storage=persistence_layer,
        object_storage=object_storage,
        document_service=document_service,
        link_service=link_service,
    )

    fastapi_app.state.pool = dp_pool
    fastapi_app.state.storage = persistence_layer
    fastapi_app.state.object_storage = object_storage
    fastapi_app.state.token_adapter = token_adapter
    fastapi_app.state.event_bus = event_bus
    fastapi_app.state.document_service = document_service
    fastapi_app.state.upload_service = upload_service
    fastapi_app.state.link_service = link_service
    fastapi_app.state.viewer_service = viewer_service
    fastapi_app.state.analytics_service = AnalyticsService(persistence_layer)
    fastapi_app.state.access_control = access_control
    fastapi_app.state.tenant_auth = TenantAuthDependency(authenticator=authenticator)
    fastapi_app.state.share_auth = ShareTokenDependency(token_port=token_adapter)
    fastapi_app.state.oidc_clients = {
        "hexiam": HexIAMOIDCClient(
            iam_url=os.getenv("HEXIAM_URL", "http://localhost:8000"),
            client_id=os.getenv("HEXSHARE_PDP_CLIENT_ID", ""),
            client_secret=os.getenv("HEXSHARE_PDP_CLIENT_SECRET", ""),
        )
    }

    yield

    await dp_pool.close()


def create_app(*args, **kwargs) -> FastAPI:
    app = FastAPI(title="HexShare", version="0.1.0", lifespan=lifespan)

    app.include_router(api_router(), prefix="/api/v1")
    app.include_router(uploads_router, prefix="/api/v1")
    app.include_router(auth_oidc_router, prefix="/api")
    app.include_router(user_router, prefix="/api/user")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    return app


if __name__ == "__main__":
    import uvicorn

    app = create_app()

    uvicorn.run(app, host="0.0.0.0", port=8000)
