import os

from fastapi import APIRouter
from starlette.responses import RedirectResponse

router = APIRouter()


@router.get("/dashboard")
async def dashboard():
    frontend_url = os.getenv("HEXSHARE_FRONTEND_URL", "http://localhost:3003")
    return RedirectResponse(f"{frontend_url.rstrip('/')}/dashboard", status_code=302)