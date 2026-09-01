from typing import Any, Protocol

from kernel_platform.security.identity_client import CurrentUserInfo

from application.ports import (
    IdentityGateway as ApplicationIdentityGateway,
)
from application.ports import (
    IdentityUser,
)


class IdentityGateway(Protocol):
    """Форма, совместимая с `kernel_platform.security.identity_client.IdentityClient`
    (ADR 0016) — в production за ней стоит настоящий `IdentityClient`, в
    интеграционных тестах (ADR 0018, Seam A) — фейковый TokenVerifier."""

    async def verify_token(self, token: str) -> dict[str, Any]: ...
    async def fetch_current_user(self, token: str) -> CurrentUserInfo: ...


class IdentityGatewayAdapter:
    """Translate the platform identity client into the application port."""

    def __init__(self, gateway: IdentityGateway) -> None:
        self._gateway = gateway

    async def fetch_current_user(self, token: str) -> IdentityUser:
        info = await self._gateway.fetch_current_user(token)
        return IdentityUser(id=info.id, role=info.role, is_active=info.is_active)


_identity_gateway_adapter: type[ApplicationIdentityGateway] = IdentityGatewayAdapter
