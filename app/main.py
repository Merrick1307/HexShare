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

from app.adapters import NoopEventBus, InMemoryEventBus, JWTTokenAdapter
from app.adapters.authz.hex_iam import HexIAMAuthorizer
from app.adapters.email import TransactionalEmailAdapter, NoopEmailAdapter
from app.adapters.email.template_loader import EmailTemplateLoader
from app.adapters.event_dispatcher import EventDispatcher
from app.adapters.rate_limiting import PolicyLoader
from app.adapters.rate_limiting.backends import (
    InMemoryRateLimitBackend,
    PostgresRateLimitBackend,
    RedisRateLimitBackend,
)
from app.adapters.oidc import GoogleOIDCClient, HexIAMOIDCClient
from app.api.router import api_router
from app.api.routes.uploads import build_router as build_uploads_router
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
    NdaService,
    UploadService,
    ViewerService,
)
from app.services.local_session_service import LocalSessionService


def _to_bool(value: str | None, *, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def get_email_adapter(adapter: str):
    if adapter == "noop":
        email_adapter = NoopEmailAdapter()
    elif adapter == "smtp":
        from app.adapters.email import SmtpEmailAdapter
        email_adapter = SmtpEmailAdapter()
    else:
        email_adapter = TransactionalEmailAdapter()
    return email_adapter


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
    preferred_email_adapter = os.getenv("HEXSHARE_EMAIL_ADAPTER", "noop")
    preferred_rate_limit_backend = os.getenv("HEXSHARE_RATE_LIMIT_BACKEND", "memory")
    rate_limit_enabled = _to_bool(os.getenv("HEXSHARE_RATE_LIMIT_ENABLED"), default=False)
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
    event_bus = InMemoryEventBus()

    # Initialize email adapter
    email_adapter = get_email_adapter(preferred_email_adapter)

    template_loader = EmailTemplateLoader()
    event_dispatcher = EventDispatcher(event_bus=event_bus, email_service=email_adapter)

    # Initialize rate limiting
    policy_loader = PolicyLoader(persistence_layer)
    
    if rate_limit_enabled:
        match preferred_rate_limit_backend:
            case "redis":
                # Requires Redis connection
                try:
                    import redis.asyncio as redis
                    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
                    redis_client = redis.from_url(redis_url)
                    rate_limit_backend = RedisRateLimitBackend(redis_client)
                except Exception as e:
                    logging.getLogger("hexshare").warning(
                        f"Redis rate limit backend failed ({e}), falling back to PostgreSQL"
                    )
                    rate_limit_backend = PostgresRateLimitBackend(dp_pool)
            case "postgres":
                rate_limit_backend = PostgresRateLimitBackend(dp_pool)
            case _:
                rate_limit_backend = InMemoryRateLimitBackend()
    else:
        rate_limit_backend = None

    document_service = DocumentService(persistence_layer, event_bus)
    document_group_service = DocumentGroupService(persistence_layer, iam_policy)
    link_service = LinkService(persistence_layer, token_adapter, event_bus)
    external_room_access_service = ExternalRoomAccessService(storage=persistence_layer, event_bus=event_bus)
    nda_service = NdaService(storage=persistence_layer, object_storage=object_storage, event_bus=event_bus)
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
        nda_service=nda_service,
        event_bus=event_bus,
    )
    external_room_viewer_service = ExternalRoomViewerService(
        storage=persistence_layer,
        object_storage=object_storage,
        rendered_page_cache=rendered_page_cache,
        document_processor=document_processor,
        document_service=document_service,
        nda_service=nda_service,
        event_bus=event_bus,
    )

    fastapi_app.state.pool = dp_pool
    fastapi_app.state.storage = persistence_layer
    fastapi_app.state.object_storage = object_storage
    fastapi_app.state.rendered_page_cache = rendered_page_cache
    fastapi_app.state.task_queue = task_queue
    fastapi_app.state.token_adapter = token_adapter
    fastapi_app.state.event_bus = event_bus
    fastapi_app.state.email_adapter = email_adapter
    fastapi_app.state.template_loader = template_loader
    fastapi_app.state.event_dispatcher = event_dispatcher
    fastapi_app.state.policy_loader = policy_loader
    fastapi_app.state.rate_limit_backend = rate_limit_backend
    fastapi_app.state.rate_limit_enabled = rate_limit_enabled
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
    fastapi_app.state.nda_service = nda_service
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
    from fastapi.responses import JSONResponse

    from app.services import NdaAcceptanceRequired

    app = FastAPI(title="HexShare", version="0.2.0", lifespan=lifespan)

    @app.exception_handler(NdaAcceptanceRequired)
    async def _nda_required_handler(_request, exc: NdaAcceptanceRequired):
        return JSONResponse(status_code=403, content={"detail": exc.detail})

    app.include_router(api_router(), prefix="/api/v1")
    # app.include_router(build_uploads_router(), prefix="/api/v1")

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
