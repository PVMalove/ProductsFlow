from typing import Any, Protocol

from kernel_platform.security.identity_client import CurrentUserInfo


class IdentityGateway(Protocol):
    """Форма, совместимая с `kernel_platform.security.identity_client.IdentityClient`
    (ADR 0016) — в production за ней стоит настоящий `IdentityClient`, в
    интеграционных тестах (ADR 0018, Seam A) — фейковый TokenVerifier."""

    async def verify_token(self, token: str) -> dict[str, Any]: ...
    async def fetch_current_user(self, token: str) -> CurrentUserInfo: ...
