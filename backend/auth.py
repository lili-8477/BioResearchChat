"""Simple username/password auth with JWT tokens and PostgreSQL."""

import asyncio
from datetime import datetime, timedelta, timezone

import asyncpg
import bcrypt
import jwt
from fastapi import HTTPException, Request, WebSocket, status

from config import settings

_pool: asyncpg.Pool | None = None


async def get_db_pool() -> asyncpg.Pool:
    """Get or create the database connection pool."""
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(settings.DATABASE_URL, min_size=2, max_size=10)
    return _pool


async def close_db_pool():
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


# --- Password ---


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


# --- JWT ---


def create_token(user_id: int, username: str) -> str:
    payload = {
        "sub": str(user_id),
        "username": username,
        "exp": datetime.now(timezone.utc) + timedelta(hours=settings.JWT_EXPIRY_HOURS),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm="HS256")


def decode_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"])
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return None


# --- Login ---


async def authenticate_user(username: str, password: str) -> dict | None:
    """Verify credentials against the database. Returns user dict or None."""
    pool = await get_db_pool()
    row = await pool.fetchrow(
        "SELECT id, username, password_hash, display_name FROM users WHERE username = $1 AND is_active = TRUE",
        username,
    )
    if not row:
        return None
    if not verify_password(password, row["password_hash"]):
        return None
    return {"id": row["id"], "username": row["username"], "display_name": row["display_name"]}


# --- Middleware helpers ---


def _extract_token(request: Request) -> str | None:
    """Extract JWT from Authorization header or cookie."""
    auth = request.headers.get("authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:]
    return request.cookies.get("biochat_token")


def _extract_token_ws(websocket: WebSocket) -> str | None:
    """Extract JWT from query param or cookie for WebSocket."""
    token = websocket.query_params.get("token")
    if token:
        return token
    return websocket.cookies.get("biochat_token")


async def require_auth(request: Request) -> dict:
    """Dependency: require a valid JWT. Returns the decoded payload."""
    token = _extract_token(request)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    payload = decode_token(token)
    if not payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")
    return payload


def ws_get_user(websocket: WebSocket) -> dict | None:
    """Get user from WebSocket token. Returns payload or None."""
    token = _extract_token_ws(websocket)
    if not token:
        return None
    return decode_token(token)
