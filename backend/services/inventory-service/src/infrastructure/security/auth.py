import uuid
from dataclasses import dataclass
from typing import Annotated

import httpx
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from kernel_platform.security import Actor, ActorRole, require_admin
from kernel_platform.security.identity_client import IdentityClient

# `auto_error=False`: обрабатываем отсутствие токена сами (401 через
# `_AUTH_REQUIRED`), а не полагаемся на дефолтное поведение HTTPBearer.
_bearer_scheme = HTTPBearer(auto_error=False)

_INVALID_TOKEN = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED, detail="Не удалось проверить токен"
)
_AUTH_REQUIRED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED, detail="Требуется авторизация"
)
_IDENTITY_UNAVAILABLE = HTTPException(
    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
    detail="identity-service недоступен",
)
_ADMIN_ONLY = HTTPException(
    status_code=status.HTTP_403_FORBIDDEN,
    detail="Доступ только для администраторов!",
)


@dataclass(frozen=True)
class AuthContext:
    """Проверенный вызывающий: `user_id` — из `sub` токена (дешёвая JWKS-
    верификация, зеркалит catalog's `AuthContext`, ADR 0011). `token`
    хранится рядом — единственный способ добрать роль через
    `IdentityClient.fetch_current_user()` относится только к предъявителю
    именно этого токена."""

    token: str
    user_id: uuid.UUID


def get_identity_client(request: Request) -> IdentityClient:
    client: IdentityClient = request.app.state.identity_client
    return client


IdentityClientDI = Annotated[IdentityClient, Depends(get_identity_client)]


async def _authenticate(
    credentials: HTTPAuthorizationCredentials, identity: IdentityClient
) -> AuthContext:
    token = credentials.credentials
    try:
        payload = await identity.verify_token(token)
    except Exception as exc:
        raise _INVALID_TOKEN from exc

    sub = payload.get("sub")
    if sub is None:
        raise _INVALID_TOKEN
    try:
        user_id = uuid.UUID(str(sub))
    except ValueError as exc:
        raise _INVALID_TOKEN from exc
    return AuthContext(token=token, user_id=user_id)


async def get_required_auth(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)
    ],
    identity: IdentityClientDI,
) -> AuthContext:
    if credentials is None:
        raise _AUTH_REQUIRED
    return await _authenticate(credentials, identity)


RequiredAuth = Annotated[AuthContext, Depends(get_required_auth)]


async def require_admin_actor(auth: RequiredAuth, identity: IdentityClientDI) -> Actor:
    """Admin-only гейт (issue #367, единственная операция сервиса, требующая
    роль) — зеркалит catalog's `is_admin`: синхронная сверка роли на identity
    при каждом вызове (никогда из claims токена — не протухает и не
    кэшируется), fail closed 503 при недоступности identity. Переиспользует
    `kernel_platform.security.require_admin` как есть (ADR 0005)."""
    try:
        info = await identity.fetch_current_user(auth.token)
    except httpx.HTTPError as exc:
        raise _IDENTITY_UNAVAILABLE from exc
    if not info.is_active:
        raise _ADMIN_ONLY
    actor = Actor(id=auth.user_id, role=ActorRole(info.role))
    return require_admin(actor)


AdminActor = Annotated[Actor, Depends(require_admin_actor)]


__all__ = [
    "AdminActor",
    "AuthContext",
    "IdentityClientDI",
    "RequiredAuth",
    "get_identity_client",
    "get_required_auth",
    "require_admin_actor",
]
