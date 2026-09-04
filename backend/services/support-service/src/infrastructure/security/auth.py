import uuid
from functools import lru_cache
from typing import Annotated, Any

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from kernel_platform.http.errors import ApiError
from kernel_platform.security import Actor, ActorRole

from application.ports import UserProjectionPort
from core.settings import settings
from infrastructure.db.session import DbSessionDI
from infrastructure.db.user_projection import SqlUserProjection

_bearer = HTTPBearer(auto_error=False)

_AUTH_REQUIRED = ApiError(
    status_code=401, code="UNAUTHORIZED", message="Требуется авторизация"
)
_INVALID_TOKEN = ApiError(
    status_code=401, code="UNAUTHORIZED", message="Не удалось проверить токен"
)
_UNKNOWN_ACTOR = ApiError(
    status_code=401, code="UNAUTHORIZED", message="Пользователь неизвестен"
)
_ACCOUNT_DISABLED = ApiError(
    status_code=403, code="FORBIDDEN", message="Учётная запись отключена"
)


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


def _decode(token: str) -> dict[str, Any]:
    return jwt.decode(
        token, _public_key(), algorithms=["RS256"], issuer=settings.support_jwt_issuer
    )


def get_user_projection(session: DbSessionDI) -> UserProjectionPort:
    return SqlUserProjection(session)


UserProjectionDI = Annotated[UserProjectionPort, Depends(get_user_projection)]


async def _verify_token(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> uuid.UUID:
    """Только локальная проверка JWT — без обращения к БД, поэтому
    отсутствующий/невалидный токен отклоняется до того, как вообще
    открывается сессия БД."""
    if credentials is None:
        raise _AUTH_REQUIRED
    try:
        payload = _decode(credentials.credentials)
        return uuid.UUID(str(payload["sub"]))
    except (jwt.InvalidTokenError, KeyError, ValueError, RuntimeError, OSError) as exc:
        raise _INVALID_TOKEN from exc


async def get_current_actor(
    user_id: Annotated[uuid.UUID, Depends(_verify_token)],
    projection: UserProjectionDI,
) -> Actor:
    """Строит transport-neutral `Actor` из собственной локальной проекции
    пользователя support — никогда из claims JWT (ADR 0005/0012).
    Deny-by-default: отсутствующая строка проекции — `401` (вызывающий
    может быть настоящим, но асинхронная проекция ещё не догнала), неактивная
    или tombstoned — `403`."""
    snapshot = await projection.get(user_id)
    if snapshot is None:
        raise _UNKNOWN_ACTOR
    if snapshot.deleted or not snapshot.is_active:
        raise _ACCOUNT_DISABLED
    return Actor(id=user_id, role=ActorRole(snapshot.role))


RequiredActor = Annotated[Actor, Depends(get_current_actor)]


__all__ = ["RequiredActor", "get_current_actor"]
