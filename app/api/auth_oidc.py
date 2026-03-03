import os

from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import RedirectResponse, JSONResponse

from app.api.dependencies.services import get_oidc_client_service
from app.core.authz import OIDC_TMP_COOKIE, AUTH_COOKIE
from app.services.oidc_service import OIDCFlowService

router = APIRouter()

def _redirect_uri(request: Request) -> str:
    return str(os.getenv("HEXSHARE_PUBLIC_URL")).rstrip("/") + "/api/auth/callback"

def _secure_cookie(request: Request) -> bool:
    public = (os.getenv("HEXSHARE_PUBLIC_URL") or "").strip()
    if public.startswith("https://"):
        return True
    return request.url.scheme == "https"

def _safe_next(next_url: str) -> str:
    # avoid open-redirect: allow only relative paths
    if not next_url.startswith("/") or next_url.startswith("//"):
        return "/"
    return next_url


@router.get("/auth/login")
async def login(
        request: Request,
        next: str = "/api/user/dashboard",
        idp: str = "hexiam"
):
    next: str = _safe_next(next)
    oidc_clients = request.app.state.oidc_clients
    svc = OIDCFlowService(
        oidc=oidc_clients[idp],
        state=request.app.state.flow_state,
    )
    start = svc.start_login(redirect_uri=_redirect_uri(request), next_url=next)
    resp = RedirectResponse(start.authorize_url, status_code=302)
    resp.set_cookie(OIDC_TMP_COOKIE, start.tmp_state_token, httponly=True, samesite="lax", path="/", max_age=600)
    return resp

@router.get("/auth/callback")
async def callback(
        request: Request,
        code: str,
        state: str,
        idp: str = "hexiam"
):
    tmp = request.cookies.get(OIDC_TMP_COOKIE)
    if not tmp:
        # user hit back/refresh after successful login
        if request.cookies.get(AUTH_COOKIE):
            return RedirectResponse("/", status_code=302)
        raise HTTPException(400, "Missing OIDC temp cookie")
    oidc_clients = request.app.state.oidc_clients
    svc = OIDCFlowService(
        oidc=oidc_clients[idp],
        state=request.app.state.flow_state,
    )
    try:
        finish = await svc.finish_login(
            redirect_uri=_redirect_uri(request),
            code=code,
            state=state,
            tmp_state_token=tmp,
        )
    except ValueError:
        raise HTTPException(400, "Invalid state")

    resp = RedirectResponse(finish.next_url, status_code=302)
    resp.set_cookie(
        AUTH_COOKIE,
        finish.tokens.access_token,
        httponly=True,
        samesite="lax",
        path="/",
        max_age=finish.tokens.expires_in
    )
    resp.delete_cookie(OIDC_TMP_COOKIE, path="/")
    return resp


@router.get("/auth/signup")
async def auth_signup(request: Request, next: str = "/api/user/dashboard", idp: str = "hexiam"):
    """
    Starts signup:
      - dedicated signup page providers: redirect directly (no tmp cookie)
      - signup-via-authorize providers: set tmp cookie + redirect to /authorize
    """
    oidc_clients = request.app.state.oidc_clients
    svc = OIDCFlowService(
        oidc=oidc_clients[idp],
        state=request.app.state.flow_state,
    )
    next_url = _safe_next(next)

    res = svc.signup_start(
        redirect_uri=_redirect_uri(request),
        next_url=next_url
    )

    mode = res.get("mode")
    if mode == "dedicated":
        return RedirectResponse(url=res["url"], status_code=302)

    if mode == "oidc":
        resp = RedirectResponse(url=res["authorize_url"], status_code=302)
        resp.set_cookie(
            key=OIDC_TMP_COOKIE,
            value=res["tmp"],
            httponly=True,
            secure=_secure_cookie(request),
            samesite="lax",
            path="/",
            max_age=600,
        )
        return resp

    raise HTTPException(status_code=500, detail="Unexpected signup_start() result")