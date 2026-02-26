import time

import jwt
from fastapi import Depends, HTTPException, Query, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import config

security = HTTPBearer(auto_error=False)


def create_token() -> str:
    payload = {
        "iat": time.time(),
        "exp": time.time() + (config.JWT_EXPIRE_HOURS * 3600),
        "sub": "claude-remote",
    }
    return jwt.encode(payload, config.JWT_SECRET, algorithm=config.JWT_ALGORITHM)


def _decode(token: str) -> dict:
    try:
        return jwt.decode(
            token, config.JWT_SECRET, algorithms=[config.JWT_ALGORITHM]
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired"
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token"
        )


def require_auth(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> dict:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
        )
    return _decode(credentials.credentials)


def ws_auth(token: str = Query(..., alias="token")) -> dict:
    """WebSocket auth via query param (Bearer header not possible for WS handshake)."""
    return _decode(token)
