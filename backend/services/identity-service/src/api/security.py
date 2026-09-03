import uuid
from typing import Annotated, Any

import jwt
from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from kernel_platform.http.errors import ApiError
from kernel_platform.security import Actor, ActorRole, require_admin

from api.dependencies import UserQueryRepositoryDI
from core.security.tokens import decode_access_token
from domain.user_id import UserId

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

_INVALID_TOKEN = ApiError(
    status_code=401, code="UNAUTHORIZED", message="Не удалось проверить токен"
)
_ACCOUNT_DISABLED = ApiError(
    status_code=403, code="FORBIDDEN", message="Учётная запись отключена"
)


async def get_current_actor(
    token: Annotated[str, Depends(oauth2_scheme)],
    users: UserQueryRepositoryDI,
) -> Actor:
    """Decode the token, then reload the user to build a transport-neutral
    `Actor` off the caller's current state — never off JWT claims, which
    carry no role and can be stale (ADR 0033)."""
    try:
        payload: dict[str, Any] = decode_access_token(token)
        user_id = UserId(uuid.UUID(str(payload["sub"])))
    except (KeyError, TypeError, ValueError, jwt.PyJWTError) as exc:
        raise _INVALID_TOKEN from exc

    user = await users.get_by_id(user_id)
    if user is None:
        raise _INVALID_TOKEN
    if not user.is_active:
        raise _ACCOUNT_DISABLED
    return Actor(id=user.id.value, role=ActorRole(user.role.value))


RequiredActor = Annotated[Actor, Depends(get_current_actor)]


async def require_admin_actor(actor: RequiredActor) -> Actor:
    return require_admin(actor)


AdminActor = Annotated[Actor, Depends(require_admin_actor)]


__all__ = ["AdminActor", "RequiredActor", "get_current_actor", "require_admin_actor"]
