"""API router assembly for HexShare HTTP routes."""
from __future__ import annotations

from fastapi import APIRouter

from app.api.routes import (
    analytics,
    auth_oidc,
    documents,
    external_room,
    groups,
    nda,
    shares,
    uploads,
    user,
    viewer,
    workspace,
)


def api_router() -> APIRouter:
    router = APIRouter()
    router.include_router(documents.build_router())
    router.include_router(shares.build_router())
    router.include_router(analytics.build_router())
    router.include_router(groups.build_router())
    router.include_router(external_room.build_router())
    router.include_router(nda.build_router())
    router.include_router(workspace.build_router())
    router.include_router(viewer.build_router())
    router.include_router(uploads.build_router())
    router.include_router(auth_oidc.build_router())
    router.include_router(user.build_router(), prefix="/user")
    return router
