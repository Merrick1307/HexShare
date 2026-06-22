from __future__ import annotations

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.authz import EXTERNAL_AUTH_COOKIE
from app.services.external_room_access_service import ExternalRoomAccessService, ExternalRoomPrincipal


_http_bearer = HTTPBearer(auto_error=False)


class ExternalRoomAuthDependency:
    def __init__(self, service: ExternalRoomAccessService) -> None:
        self._service = service

    def __call__(self):
        async def verify(
            credentials: HTTPAuthorizationCredentials = Depends(_http_bearer),
            request: Request = None,
        ) -> ExternalRoomPrincipal:
            token = credentials.credentials if credentials else None
            if not token and request is not None:
                token = request.cookies.get(EXTERNAL_AUTH_COOKIE)
            if not token:
                raise HTTPException(status_code=401, detail="Missing external access token")
            try:
                return await self._service.authenticate_access_token(access_token=token)
            except ValueError as exc:
                raise HTTPException(status_code=401, detail=str(exc))
            except Exception:
                raise HTTPException(status_code=401, detail="Invalid or expired external access token")

        return verify


async def get_external_room_principal(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(_http_bearer),
) -> ExternalRoomPrincipal:
    service: ExternalRoomAccessService = request.app.state.external_room_access_service
    token = credentials.credentials if credentials else None
    if not token:
        token = request.cookies.get(EXTERNAL_AUTH_COOKIE)
    if not token:
        raise HTTPException(status_code=401, detail="Missing external access token")
    try:
        return await service.authenticate_access_token(access_token=token)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc))
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired external access token")
