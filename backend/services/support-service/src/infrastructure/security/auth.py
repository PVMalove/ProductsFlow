import uuid
from functools import lru_cache
from typing import Annotated, Any

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from core.settings import settings

_bearer = HTTPBearer(auto_error=False)


@lru_cache(maxsize=1)
def _public_key() -> str:
    if settings.support_jwt_public_key:
        return settings.support_jwt_public_key
    if settings.support_jwt_public_key_path:
        with open(settings.support_jwt_public_key_path, encoding="utf-8") as key_file:
            return key_file.read()
    raise RuntimeError(
        "SUPPORT_JWT_PUBLIC_KEY_PATH or SUPPORT_JWT_PUBLIC_KEY is required"
    )


async def get_required_auth(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> uuid.UUID:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Требуется авторизация"
        )
    try:
        payload = _decode(credentials.credentials)
        return uuid.UUID(str(payload["sub"]))
    except (jwt.InvalidTokenError, KeyError, ValueError, RuntimeError, OSError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Не удалось проверить токен",
        ) from exc


RequiredAuth = Annotated[uuid.UUID, Depends(get_required_auth)]


async def get_admin_auth(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> uuid.UUID:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Требуется авторизация"
        )
    try:
        payload = _decode(credentials.credentials)
        if payload.get("role") != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав"
            )
        return uuid.UUID(str(payload["sub"]))
    except HTTPException:
        raise
    except (jwt.InvalidTokenError, KeyError, ValueError, RuntimeError, OSError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Не удалось проверить токен",
        ) from exc


def _decode(token: str) -> dict[str, Any]:
    return jwt.decode(
        token, _public_key(), algorithms=["RS256"], issuer=settings.support_jwt_issuer
    )


AdminAuth = Annotated[uuid.UUID, Depends(get_admin_auth)]


async def get_is_admin(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> bool:
    if credentials is None:
        return False
    try:
        return _decode(credentials.credentials).get("role") == "admin"
    except jwt.InvalidTokenError, KeyError, ValueError, RuntimeError, OSError:
        return False


OptionalAdmin = Annotated[bool, Depends(get_is_admin)]
