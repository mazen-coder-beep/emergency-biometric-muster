"""
auth.py
───────
JWT authentication layer.

Roles
-----
  camera_node  – edge cameras / CV scripts; may POST to /api/event
  dashboard    – frontend clients; may connect to /ws and GET /api/export/*

Flow
----
  1. Client POSTs { client_id, client_secret } to /auth/token
  2. Server validates credentials against environment variables
     (swap for DB lookup in production)
  3. Server returns { access_token, token_type, expires_in }
  4. Client attaches token:
       • REST  → Authorization: Bearer <token>
       • WS   → ws://host/ws?token=<token>   (headers not supported in WS)
"""

import os
from datetime import datetime, timedelta, timezone
from typing import Annotated

from dotenv import load_dotenv
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from pydantic import BaseModel

load_dotenv()

# ── Config ────────────────────────────────────────────────────────────────────

JWT_SECRET: str = os.environ["JWT_SECRET"]
JWT_ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")
JWT_EXPIRE_MINUTES: int = int(os.getenv("JWT_EXPIRE_MINUTES", "60"))

# Credential store – in production replace with a DB table of hashed secrets
_CLIENTS: dict[str, dict] = {
    os.environ["CAMERA_CLIENT_ID"]: {
        "secret": os.environ["CAMERA_CLIENT_SECRET"],
        "role": "camera_node",
    },
    os.environ["DASHBOARD_CLIENT_ID"]: {
        "secret": os.environ["DASHBOARD_CLIENT_SECRET"],
        "role": "dashboard",
    },
}

# ── Pydantic schemas ──────────────────────────────────────────────────────────

class TokenRequest(BaseModel):
    client_id: str
    client_secret: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds


class TokenData(BaseModel):
    sub: str          # client_id
    role: str


# ── JWT helpers ───────────────────────────────────────────────────────────────

def _create_access_token(sub: str, role: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=JWT_EXPIRE_MINUTES)
    payload = {"sub": sub, "role": role, "exp": expire}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def _decode_token(token: str) -> TokenData:
    """
    Decode and validate a JWT.
    Raises HTTP 401 on any failure.
    """
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        sub: str = payload.get("sub")
        role: str = payload.get("role")
        if sub is None or role is None:
            raise ValueError("Missing claims")
        return TokenData(sub=sub, role=role)
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid or expired token: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        )


# ── FastAPI dependency helpers ────────────────────────────────────────────────

_oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token", auto_error=False)


async def get_current_token(
    bearer: Annotated[str | None, Depends(_oauth2_scheme)] = None,
) -> TokenData:
    """Dependency for standard Bearer-header protected endpoints."""
    if bearer is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return _decode_token(bearer)


def require_role(*roles: str):
    """
    Factory that returns a dependency enforcing one of the given roles.

    Usage:
        @router.post("/api/event", dependencies=[Depends(require_role("camera_node"))])
    """
    async def _check(token: Annotated[TokenData, Depends(get_current_token)]):
        if token.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{token.role}' is not permitted here. Required: {roles}",
            )
        return token
    return _check


async def ws_token_auth(token: str = Query(..., description="JWT access token")) -> TokenData:
    """
    Dependency for WebSocket endpoints.
    WebSocket clients pass the token as a query parameter:
        ws://host/ws?token=<jwt>
    because the browser WebSocket API cannot set custom headers.
    """
    return _decode_token(token)


# ── Router ────────────────────────────────────────────────────────────────────

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/token", response_model=TokenResponse, summary="Obtain a JWT access token")
async def get_token(body: TokenRequest):
    """
    Exchange client credentials for a signed JWT.

    - **camera_node** clients use this token to POST events to `/api/event`.
    - **dashboard** clients use this token to connect to `/ws` and call
      `/api/export/police-brief`.
    """
    client = _CLIENTS.get(body.client_id)
    if client is None or client["secret"] != body.client_secret:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid client_id or client_secret",
        )

    token = _create_access_token(sub=body.client_id, role=client["role"])
    return TokenResponse(
        access_token=token,
        expires_in=JWT_EXPIRE_MINUTES * 60,
    )
