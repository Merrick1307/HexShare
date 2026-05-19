import os

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse, RedirectResponse

from app.core.authz import OIDC_TMP_COOKIE, AUTH_COOKIE, REFRESH_COOKIE
from app.services.oidc_service import OIDCFlowService

router = APIRouter()

def _redirect_uri(request: Request) -> str:
    return str(os.getenv("HEXSHARE_PUBLIC_URL", "http://localhost:8099")).rstrip("/") + "/api/auth/callback"

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


def _frontend_dashboard_url() -> str:
    return f"{os.getenv('HEXSHARE_FRONTEND_URL', 'http://localhost:3000').rstrip('/')}/dashboard"


def _resolve_oidc_client(request: Request, idp: str | None):
    resolved_idp = (idp or request.app.state.default_oidc_idp or "hexiam").strip()
    oidc = request.app.state.oidc_clients.get(resolved_idp)
    if not oidc:
        raise HTTPException(400, f"Unknown IDP: {resolved_idp}")
    return resolved_idp, oidc


@router.get("/auth/login")
async def login(
        request: Request,
        next: str = "/api/user/dashboard",
        idp: str | None = None
):
    next: str = _safe_next(next)
    _, oidc = _resolve_oidc_client(request, idp)
    svc = OIDCFlowService(oidc=oidc)
    start = svc.start_login(redirect_uri=_redirect_uri(request), next_url=next)
    resp = RedirectResponse(start.authorize_url, status_code=302)
    resp.set_cookie(OIDC_TMP_COOKIE, start.tmp_state_token, httponly=True, samesite="lax", path="/", max_age=600)
    return resp

@router.get("/auth/callback")
async def callback(
        request: Request,
        code: str,
        state: str,
        idp: str | None = None
):
    tmp = request.cookies.get(OIDC_TMP_COOKIE)
    if not tmp:
        # user hit back/refresh after successful login
        if request.cookies.get(AUTH_COOKIE):
            return RedirectResponse(_frontend_dashboard_url(), status_code=302)
        raise HTTPException(400, "Missing OIDC temp cookie")
    resolved_idp, oidc = _resolve_oidc_client(request, idp)
    svc = OIDCFlowService(oidc=oidc)
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
    secure = _secure_cookie(request)
    if request.app.state.authenticator_mode == "local":
        local_session_service = request.app.state.local_session_service
        if local_session_service is None:
            raise HTTPException(500, "Local session service is not configured")
        try:
            user_info = await oidc.get_user_info(
                access_token=finish.tokens.access_token,
                id_token=finish.tokens.id_token,
            )
            local_tokens = await local_session_service.issue_session_from_user_info(
                idp=resolved_idp,
                user_info=user_info,
            )
        except NotImplementedError:
            raise HTTPException(500, "Configured IDP does not support user info retrieval")
        except ValueError as exc:
            raise HTTPException(400, str(exc))
        except Exception as exc:
            raise HTTPException(401, f"Login failed: {str(exc)}")
        resp.set_cookie(
            AUTH_COOKIE,
            local_tokens.access_token,
            httponly=True,
            secure=secure,
            samesite="lax",
            path="/",
            max_age=local_tokens.expires_in,
        )
        resp.set_cookie(
            REFRESH_COOKIE,
            local_tokens.refresh_token,
            httponly=True,
            secure=secure,
            samesite="lax",
            path="/",
            max_age=local_tokens.refresh_expires_in,
        )
    else:
        resp.set_cookie(
            AUTH_COOKIE,
            finish.tokens.access_token,
            httponly=True,
            secure=secure,
            samesite="lax",
            path="/",
            max_age=finish.tokens.expires_in
        )
        if finish.tokens.refresh_token:
            resp.set_cookie(
                REFRESH_COOKIE,
                finish.tokens.refresh_token,
                httponly=True,
                secure=secure,
                samesite="lax",
                path="/",
                max_age=60 * 60 * 24 * 30
            )
    resp.delete_cookie(OIDC_TMP_COOKIE, path="/")
    return resp


@router.get("/auth/signup")
async def auth_signup(request: Request, next: str = "/api/user/dashboard", idp: str | None = None):
    """
    Starts signup:
      - dedicated signup page providers: redirect directly (no tmp cookie)
      - signup-via-authorize providers: set tmp cookie + redirect to /authorize
    """
    _, oidc = _resolve_oidc_client(request, idp)
    svc = OIDCFlowService(oidc=oidc)
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


@router.post("/auth/refresh")
async def refresh_token(request: Request, idp: str | None = None):
    """
    Refresh access token using the stored refresh_token cookie.
    Returns JSON with new tokens and sets updated cookies.
    """
    refresh_cookie = request.cookies.get(REFRESH_COOKIE)
    if not refresh_cookie:
        raise HTTPException(401, "No refresh token available")

    secure = _secure_cookie(request)
    if request.app.state.authenticator_mode == "local":
        local_session_service = request.app.state.local_session_service
        if local_session_service is None:
            raise HTTPException(500, "Local session service is not configured")
        try:
            tokens = await local_session_service.refresh_session(refresh_token=refresh_cookie)
        except Exception as exc:
            raise HTTPException(401, f"Token refresh failed: {str(exc)}")

        resp = JSONResponse({
            "access_token": tokens.access_token,
            "expires_in": tokens.expires_in,
            "token_type": tokens.token_type,
        })
        resp.set_cookie(
            AUTH_COOKIE,
            tokens.access_token,
            httponly=True,
            secure=secure,
            samesite="lax",
            path="/",
            max_age=tokens.expires_in
        )
        resp.set_cookie(
            REFRESH_COOKIE,
            tokens.refresh_token,
            httponly=True,
            secure=secure,
            samesite="lax",
            path="/",
            max_age=tokens.refresh_expires_in
        )
        return resp

    _, oidc = _resolve_oidc_client(request, idp)

    try:
        tokens = await oidc.refresh(refresh_token=refresh_cookie)
    except Exception as e:
        raise HTTPException(401, f"Token refresh failed: {str(e)}")

    resp = JSONResponse({
        "access_token": tokens.access_token,
        "expires_in": tokens.expires_in,
        "token_type": tokens.token_type,
    })
    resp.set_cookie(
        AUTH_COOKIE,
        tokens.access_token,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/",
        max_age=tokens.expires_in
    )
    if tokens.refresh_token:
        resp.set_cookie(
            REFRESH_COOKIE,
            tokens.refresh_token,
            httponly=True,
            secure=secure,
            samesite="lax",
            path="/",
            max_age=60 * 60 * 24 * 30  # 30 days
        )
    return resp


@router.post("/auth/logout")
async def logout(request: Request):
    """
    Clear auth cookies and return success.
    """
    resp = JSONResponse({"status": "logged_out"})
    resp.delete_cookie(AUTH_COOKIE, path="/")
    resp.delete_cookie(REFRESH_COOKIE, path="/")
    return resp