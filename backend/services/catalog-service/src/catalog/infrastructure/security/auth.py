import uuid
from dataclasses import dataclass
from typing import Annotated

import httpx
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from catalog.infrastructure.identity_gateway import IdentityGateway

# `auto_error=False`: без заголовка — `None`, а не 401 — ADR 0002 требует
# анонимного просмотра там, где токен не обязателен; невалидный (но
# предъявленный) токен — всё равно ошибка, не тихий откат к анонимному виду.
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


@dataclass(frozen=True)
class AuthContext:
    """Проверенный вызывающий (issue #149): `user_id` — из `sub` токена,
    локален и не протухает (ADR 0012). `token` хранится рядом — единственный
    способ добрать `role`/`is_active` через `IdentityClient.fetch_current_user()`
    относится только к предъявителю именно этого токена."""

    token: str
    user_id: uuid.UUID


def get_identity_gateway(request: Request) -> IdentityGateway:
    gateway: IdentityGateway = request.app.state.identity_gateway
    return gateway


IdentityGatewayDI = Annotated[IdentityGateway, Depends(get_identity_gateway)]


async def _authenticate(
    credentials: HTTPAuthorizationCredentials, identity: IdentityGateway
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


async def get_optional_auth(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)
    ],
    identity: IdentityGatewayDI,
) -> AuthContext | None:
    if credentials is None:
        return None
    return await _authenticate(credentials, identity)


async def get_required_auth(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)
    ],
    identity: IdentityGatewayDI,
) -> AuthContext:
    if credentials is None:
        raise _AUTH_REQUIRED
    return await _authenticate(credentials, identity)


OptionalAuth = Annotated[AuthContext | None, Depends(get_optional_auth)]
RequiredAuth = Annotated[AuthContext, Depends(get_required_auth)]


async def is_admin(auth: AuthContext | None, identity: IdentityGateway) -> bool:
    """ADR 0012 «Админская ветка»: синхронная сверка, вызывается только там,
    где доступ действительно решается ролью — не на каждый аутентифицированный
    запрос. Недоступность identity здесь — fail closed (503), а не «считать
    не-админом»: тихий откат замаскировал бы отказ инфраструктуры под
    обычный `403`."""
    if auth is None:
        return False
    try:
        info = await identity.fetch_current_user(auth.token)
    except httpx.HTTPError as exc:
        raise _IDENTITY_UNAVAILABLE from exc
    return info.role == "admin" and info.is_active


async def ensure_owner_or_admin(
    auth: AuthContext, product_user_id: uuid.UUID, identity: IdentityGateway
) -> None:
    """Владение проверяется локально и первым — не протухает (ADR 0012),
    синхронный вызов к identity не нужен вовсе. Только если владение не
    совпало, доступ может дать ещё и роль — и только тогда выполняется
    синхронная сверка."""
    if auth.user_id == product_user_id:
        return
    if await is_admin(auth, identity):
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN, detail="Нет прав на этот товар"
    )
