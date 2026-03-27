"""Security helpers for HTTP and WebSocket access control."""

import secrets

from fastapi import HTTPException, Request, WebSocket, status
from fastapi.responses import JSONResponse

from config import settings

CONTROL_TOKEN_HEADER = "x-control-token"
CONTROL_TOKEN_QUERY = "control_token"


def control_auth_enabled() -> bool:
    return bool(settings.CONTROL_API_TOKEN)


def _matches_control_token(token: str | None) -> bool:
    return bool(token) and secrets.compare_digest(token, settings.CONTROL_API_TOKEN)


def _request_authenticated(request: Request) -> tuple[bool, bool]:
    """Return (authenticated, authenticated_via_header)."""
    if not control_auth_enabled():
        return True, False

    cookie_token = request.cookies.get(settings.CONTROL_COOKIE_NAME)
    if _matches_control_token(cookie_token):
        return True, False

    header_token = request.headers.get(CONTROL_TOKEN_HEADER)
    if _matches_control_token(header_token):
        return True, True

    return False, False


async def control_token_http_middleware(request: Request, call_next):
    """Protect the control plane and mint an auth cookie from a valid header."""
    if request.method == "OPTIONS" or request.url.path == "/api/health":
        return await call_next(request)

    authenticated, via_header = _request_authenticated(request)
    if not authenticated:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"detail": "Control token required"},
        )

    response = await call_next(request)
    if via_header:
        response.set_cookie(
            key=settings.CONTROL_COOKIE_NAME,
            value=settings.CONTROL_API_TOKEN,
            httponly=True,
            secure=settings.CONTROL_COOKIE_SECURE,
            samesite="lax",
            path="/",
        )
    return response


def websocket_authenticated(websocket: WebSocket) -> bool:
    if not control_auth_enabled():
        return True

    cookie_token = websocket.cookies.get(settings.CONTROL_COOKIE_NAME)
    if _matches_control_token(cookie_token):
        return True

    query_token = websocket.query_params.get(CONTROL_TOKEN_QUERY)
    return _matches_control_token(query_token)


def require_dev_endpoints_enabled():
    if settings.ENABLE_DEV_ENDPOINTS:
        return
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
