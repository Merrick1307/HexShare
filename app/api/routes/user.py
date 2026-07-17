import os

from fastapi import APIRouter, Depends
from starlette.responses import RedirectResponse

from app.adapters.rate_limiting import rate_limit


def build_router() -> APIRouter:
    router = APIRouter(dependencies=[Depends(rate_limit("api_general"))])

    @router.get("/dashboard")
    async def dashboard():
        frontend_url = os.getenv("HEXSHARE_FRONTEND_URL", "http://localhost:3003")
        return RedirectResponse(f"{frontend_url.rstrip('/')}/dashboard", status_code=302)

    return router