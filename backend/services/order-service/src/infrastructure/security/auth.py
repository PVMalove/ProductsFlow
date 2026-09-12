import uuid
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
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


@dataclass(frozen=True)
class AuthContext:
    """Проверенный вызывающий: `user_id` — из `sub` токена (дешёвая JWKS-
    верификация, зеркалит payment/inventory-service's `AuthContext`,
    архитектурный бриф issue #369 D2). Любой аутентифицированный пользователь
    допускается ко всем операциям над собственной корзиной — роль не
    проверяется, синхронный `fetch_current_user()` не требуется вовсе."""

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


__all__ = [
    "AuthContext",
    "IdentityClientDI",
    "RequiredAuth",
    "get_identity_client",
    "get_required_auth",
]
