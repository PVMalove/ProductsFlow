import uuid
from typing import Any

import httpx
import jwt
from kernel_platform.security.identity_client import CurrentUserInfo


class FakeIdentityClient:
    """Фейковый identity-клиент (ADR 0013, Seam A): не бьёт по сети, HTTP-слой
    order-service тестируется против настоящего Postgres, но против
    подставного identity. Любой зарегистрированный токен проходит
    `RequiredAuth` — order-service не сверяет роль (архитектурный бриф D2).
    `fetch_current_user` (issue #372) — синхронная сверка активности для
    `RequiredActiveUser`/checkout (ADR 0016:11)."""

    def __init__(self) -> None:
        self._users: dict[str, CurrentUserInfo] = {}
        self.unavailable = False

    def register(
        self,
        token: str,
        *,
        user_id: uuid.UUID,
        role: str = "user",
        is_active: bool = True,
    ) -> None:
        self._users[token] = CurrentUserInfo(id=user_id, role=role, is_active=is_active)

    async def verify_token(self, token: str) -> dict[str, Any]:
        info = self._users.get(token)
        if info is None:
            raise jwt.InvalidTokenError(f"Неизвестный токен: {token!r}")
        return {"sub": str(info.id)}

    async def fetch_current_user(self, token: str) -> CurrentUserInfo:
        if self.unavailable:
            raise httpx.ConnectError(
                "identity-service недоступен", request=httpx.Request("GET", "http://identity")
            )
        info = self._users.get(token)
        if info is None:
            raise httpx.HTTPStatusError(
                "unknown token",
                request=httpx.Request("GET", "http://identity"),
                response=httpx.Response(401),
            )
        return info
