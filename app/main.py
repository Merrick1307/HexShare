"""
Application entry point for HexShare.
"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

import asyncpg
from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware

from app.adapters import NoopEventBus, JWTTokenAdapter
from app.adapters.authz.hex_iam import HexIAMAuthorizer
from app.adapters.oidc import GoogleOIDCClient, HexIAMOIDCClient
from app.api.auth_oidc import router as auth_oidc_router
from app.api.router import api_router
from app.api.uploads import router as uploads_router
from app.api.user import router as user_router
from app.auth.share_token_auth import ShareTokenDependency
from app.auth.tenant_auth import TenantAuthDependency
from app.auth.external_room_auth import ExternalRoomAuthDependency
from app.infra.factories import (
    AccessControlFactory,
    AuthenticatorFactory,
    IAMPolicyFactory,
    ObjectStorageFactory,
    RenderedPageCacheFactory,
    StorageFactory,
    TaskQueueFactory,
)
from app.services import (
    AnalyticsService,
    DocumentProcessor,
    DocumentGroupService,
    DocumentService,
    ExternalRoomAccessService,
    ExternalRoomViewerService,
    LinkService,
    UploadService,
    ViewerService,
)
from app.services.local_session_service import LocalSessionService


def _to_bool(value: str | None, *, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@asynccontextmanager
async def lifespan(fastapi_app: FastAPI):
    dp_pool = await asyncpg.create_pool(dsn=os.getenv("DATABASE_URL"))

    preferred_storage = os.getenv("HEXSHARE_STORAGE", "postgres")
    preferred_access_control = os.getenv("HEXSHARE_ACCESS_CONTROL", "hybrid")
    preferred_authenticator = os.getenv("HEXSHARE_AUTHENTICATOR", "hexiam")
    preferred_oidc_idp = os.getenv("HEXSHARE_DEFAULT_OIDC_IDP", "hexiam").strip() or "hexiam"
    preferred_object_storage = os.getenv("HEXSHARE_OBJECT_STORAGE", "s3")
    preferred_rendered_page_cache = os.getenv("HEXSHARE_RENDERED_PAGE_CACHE", "inmemory")
    preferred_task_queue = os.getenv("HEXSHARE_TASK_QUEUE", "noop")
    preferred_iam_policy = os.getenv("HEXSHARE_IAM_POLICY", "hexiam")
    pdp_iam_url = os.getenv("HEXIAM_PDP_URL") or os.getenv("HEXIAM_URL", "http://localhost:8000")
    viewer_strategy = os.getenv("HEXSHARE_VIEWER_STRATEGY", "secure_streaming").strip() or "secure_streaming"
    document_processing_enabled = _to_bool(
        os.getenv("HEXSHARE_DOCUMENT_PROCESSING_ENABLED"),
        default=True,
    )
    frontend_url = os.getenv("HEXSHARE_FRONTEND_URL", "http://localhost:3000").rstrip("/")
    demo_mode = _to_bool(os.getenv("HEXSHARE_DEMO_MODE"), default=False)

    if demo_mode:
        logging.getLogger("hexshare").warning(
            "DEMO MODE ENABLED — credential-free login (/api/auth/demo-login) is active "
            "and the workspace is shared and public. Never set HEXSHARE_DEMO_MODE=true "
            "in a real deployment."
        )
        if preferred_authenticator != "local":
            logging.getLogger("hexshare").warning(
                "HEXSHARE_DEMO_MODE is on but HEXSHARE_AUTHENTICATOR=%s; demo login "
                "requires 'local' and will return 500 until that is set.",
                preferred_authenticator,
            )

    if preferred_authenticator == "local" and preferred_access_control == "hybrid":
        preferred_access_control = "edge"
    if preferred_authenticator == "local" and preferred_access_control == "pdp":
        raise RuntimeError("HEXSHARE_ACCESS_CONTROL=pdp is not compatible with HEXSHARE_AUTHENTICATOR=local")

    import app.infra.bootstrap  # noqa: F401

    authorizer = HexIAMAuthorizer()
    authenticator = AuthenticatorFactory.create(preferred_authenticator)

    persistence_layer = StorageFactory.create(preferred_storage, pool=dp_pool)
    object_storage = ObjectStorageFactory.create(preferred_object_storage)
    rendered_page_cache = RenderedPageCacheFactory.create(preferred_rendered_page_cache)
    task_queue = TaskQueueFactory.create(preferred_task_queue)
    iam_policy = IAMPolicyFactory.create(preferred_iam_policy, pool=dp_pool)

    access_control = AccessControlFactory.create(
        preferred_access_control,
        authorizer=authorizer,
        authenticator=authenticator,
        iam_url=pdp_iam_url,
        client_id=os.getenv("HEXSHARE_PDP_CLIENT_ID", ""),
        client_secret=os.getenv("HEXSHARE_PDP_CLIENT_SECRET", ""),
    )

    token_adapter = JWTTokenAdapter()
    local_session_service = (
        LocalSessionService(pool=dp_pool)
        if preferred_authenticator == "local"
        else None
    )
    event_bus = NoopEventBus()
    document_service = DocumentService(persistence_layer, event_bus)
    document_group_service = DocumentGroupService(persistence_layer, iam_policy)
    link_service = LinkService(persistence_layer, token_adapter, event_bus)
    external_room_access_service = ExternalRoomAccessService(storage=persistence_layer)
    document_processor = DocumentProcessor()
    max_upload = os.getenv("HEXSHARE_MAX_UPLOAD_SIZE_BYTES")
    upload_service = UploadService(
        metadata_storage=persistence_layer,
        object_storage=object_storage,
        document_service=document_service,
        max_size_bytes=int(max_upload) if max_upload else None,
    )
    viewer_service = ViewerService(
        storage=persistence_layer,
        object_storage=object_storage,
        rendered_page_cache=rendered_page_cache,
        task_queue=task_queue,
        document_processor=document_processor,
        document_service=document_service,
        link_service=link_service,
    )
    external_room_viewer_service = ExternalRoomViewerService(
        storage=persistence_layer,
        object_storage=object_storage,
        rendered_page_cache=rendered_page_cache,
        document_processor=document_processor,
        document_service=document_service,
    )

    fastapi_app.state.pool = dp_pool
    fastapi_app.state.storage = persistence_layer
    fastapi_app.state.object_storage = object_storage
    fastapi_app.state.rendered_page_cache = rendered_page_cache
    fastapi_app.state.task_queue = task_queue
    fastapi_app.state.token_adapter = token_adapter
    fastapi_app.state.event_bus = event_bus
    fastapi_app.state.document_service = document_service
    fastapi_app.state.document_group_service = document_group_service
    fastapi_app.state.document_processor = document_processor
    fastapi_app.state.viewer_strategy = viewer_strategy
    fastapi_app.state.document_processing_enabled = document_processing_enabled
    fastapi_app.state.iam_policy = iam_policy
    fastapi_app.state.upload_service = upload_service
    fastapi_app.state.link_service = link_service
    fastapi_app.state.external_room_access_service = external_room_access_service
    fastapi_app.state.external_room_viewer_service = external_room_viewer_service
    fastapi_app.state.viewer_service = viewer_service
    fastapi_app.state.analytics_service = AnalyticsService(persistence_layer)
    fastapi_app.state.access_control = access_control
    fastapi_app.state.tenant_auth = TenantAuthDependency(authenticator=authenticator)
    fastapi_app.state.share_auth = ShareTokenDependency(token_port=token_adapter)
    fastapi_app.state.external_room_auth = ExternalRoomAuthDependency(service=external_room_access_service)
    hexiam_url = os.getenv("HEXIAM_URL", "").strip()
    hexiam_client_id = os.getenv("HEXSHARE_CLIENT_ID") or os.getenv("HEXSHARE_PDP_CLIENT_ID", "")
    hexiam_client_secret = os.getenv("HEXSHARE_CLIENT_SECRET") or os.getenv("HEXSHARE_PDP_CLIENT_SECRET", "")
    oidc_clients = {}
    if preferred_oidc_idp == "hexiam" or (hexiam_url and hexiam_client_id):
        oidc_clients["hexiam"] = HexIAMOIDCClient(
            iam_url=hexiam_url or "http://localhost:8000",
            client_id=hexiam_client_id,
            client_secret=hexiam_client_secret,
        )
    if preferred_oidc_idp == "google" or os.getenv("GOOGLE_OIDC_CLIENT_ID"):
        oidc_clients["google"] = GoogleOIDCClient()
    if preferred_oidc_idp not in oidc_clients:
        raise RuntimeError(f"Configured default OIDC provider '{preferred_oidc_idp}' is not available")
    fastapi_app.state.oidc_clients = oidc_clients
    fastapi_app.state.default_oidc_idp = preferred_oidc_idp
    fastapi_app.state.authenticator_mode = preferred_authenticator
    fastapi_app.state.local_session_service = local_session_service
    fastapi_app.state.frontend_url = frontend_url
    fastapi_app.state.demo_mode = demo_mode

    yield

    await dp_pool.close()


def create_app(*args, **kwargs) -> FastAPI:
    app = FastAPI(title="HexShare", version="0.1.0", lifespan=lifespan)

    app.include_router(api_router(), prefix="/api/v1")
    app.include_router(uploads_router, prefix="/api/v1")
    app.include_router(auth_oidc_router, prefix="/api")
    app.include_router(user_router, prefix="/api/user")

    frontend_url = os.getenv("HEXSHARE_FRONTEND_URL", "http://localhost:3000").rstrip("/")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[frontend_url, "http://localhost:3000", "http://localhost:3003"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    return app


if __name__ == "__main__":
    import uvicorn

    app = create_app()

    uvicorn.run(app, host="0.0.0.0", port=8000)
