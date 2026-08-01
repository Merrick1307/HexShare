"""Unauthenticated liveness endpoint for container orchestration."""
from fastapi import APIRouter


def build_router() -> APIRouter:
    router = APIRouter()

    @router.get("/healthz", include_in_schema=False)
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return router
