import uuid
from typing import Annotated, Any

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from api.dependencies import UserQueryRepositoryDI
from application.ports import UserReadModel
from core.security.tokens import decode_access_token
from domain.role import Role
from domain.user_id import UserId

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

_INVALID_TOKEN = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Не удалось проверить токен",
    headers={"WWW-Authenticate": "Bearer"},
)


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    users: UserQueryRepositoryDI,
) -> UserReadModel:
    """Decode the token and reload the user to enforce current account state."""
    try:
        payload: dict[str, Any] = decode_access_token(token)
        user_id = UserId(uuid.UUID(str(payload["sub"])))
    except (KeyError, TypeError, ValueError, jwt.PyJWTError) as exc:
        raise _INVALID_TOKEN from exc

    user = await users.get_by_id(user_id)
    if user is None:
        raise _INVALID_TOKEN
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Учётная запись отключена",
        )
    return user


CurrentUser = Annotated[UserReadModel, Depends(get_current_user)]


async def require_admin(current_user: CurrentUser) -> UserReadModel:
    if current_user.role is not Role.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Доступ только для администраторов!",
        )
    return current_user


AdminUser = Annotated[UserReadModel, Depends(require_admin)]


__all__ = ["AdminUser", "CurrentUser", "get_current_user"]
