from typing import Any, Protocol

import httpx
from kernel_platform.security.identity_client import CurrentUserInfo

from application.errors import IdentityUnavailableError
from application.ports import (
    IdentityGateway as ApplicationIdentityGateway,
)
from application.ports import (
    IdentityUser,
)


class IdentityGateway(Protocol):
    """Форма, совместимая с `kernel_platform.security.identity_client.IdentityClient`
    (ADR 0005) — в production за ней стоит настоящий `IdentityClient`, в
    интеграционных тестах (ADR 0013, Seam A) — фейковый TokenVerifier."""

    async def verify_token(self, token: str) -> dict[str, Any]: ...
    async def fetch_current_user(self, token: str) -> CurrentUserInfo: ...


class IdentityGatewayAdapter:
    """Транслирует платформенный identity-клиент в application-порт."""

    def __init__(self, gateway: IdentityGateway) -> None:
        self._gateway = gateway

    async def fetch_current_user(self, token: str) -> IdentityUser:
        try:
            info = await self._gateway.fetch_current_user(token)
        except httpx.HTTPError as exc:
            raise IdentityUnavailableError from exc
        return IdentityUser(id=info.id, role=info.role, is_active=info.is_active)


_identity_gateway_adapter: type[ApplicationIdentityGateway] = IdentityGatewayAdapter
