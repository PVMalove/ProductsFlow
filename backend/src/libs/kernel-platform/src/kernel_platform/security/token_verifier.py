import logging
import time
from typing import Any

import httpx
import jwt
from jwt.algorithms import RSAAlgorithm

logger = logging.getLogger(__name__)

ALGORITHM = "RS256"
DEFAULT_JWKS_PATH = "/.well-known/jwks.json"
DEFAULT_TTL_SECONDS = 600.0
DEFAULT_UNKNOWN_KID_THROTTLE_SECONDS = 60.0


class TokenVerifier:
    """Кэширующий JWKS-клиент: проверяет RS256-токены identity локально по
    закэшированному публичному ключу — без сетевого вызова на каждый запрос
    (ADR 0011, TD §4.1). Кэш живёт TTL; незнакомый kid вызывает ровно один
    внеочередной refetch, троттлированный отдельным окном, чтобы поток
    токенов с выдуманным kid не превращался в усилитель запросов к identity.
    """

    def __init__(
        self,
        http_client: httpx.AsyncClient,
        *,
        jwks_path: str = DEFAULT_JWKS_PATH,
        ttl_seconds: float = DEFAULT_TTL_SECONDS,
        unknown_kid_throttle_seconds: float = DEFAULT_UNKNOWN_KID_THROTTLE_SECONDS,
    ) -> None:
        self._http_client = http_client
        self._jwks_path = jwks_path
        self._ttl_seconds = ttl_seconds
        self._unknown_kid_throttle_seconds = unknown_kid_throttle_seconds
        self._keys: dict[str, Any] = {}
        self._fetched_at: float | None = None
        self._last_unknown_kid_refetch_at: float | None = None

    async def preload(self) -> None:
        """Предзагрузка при старте: неудача не фатальна и не блокирует
        запуск — дальше при первой верификации сработает ленивый fetch
        (ADR 0011). Ловим Exception намеренно: контракт этого метода —
        никогда не поднимать исключение наверх, независимо от причины сбоя
        (сеть, битый статус, невалидное тело JWKS-ответа)."""
        try:
            await self._fetch()
        except Exception:
            logger.warning("Не удалось предзагрузить JWKS при старте", exc_info=True)

    async def verify(self, token: str) -> dict[str, Any]:
        kid = jwt.get_unverified_header(token).get("kid")
        key = await self._resolve_key(kid)
        result: dict[str, Any] = jwt.decode(token, key=key, algorithms=[ALGORITHM])
        return result

    async def _resolve_key(self, kid: str | None) -> Any:
        if self._is_stale():
            await self._fetch()
        if kid not in self._keys:
            await self._maybe_refetch_for_unknown_kid()
        if kid not in self._keys:
            raise jwt.InvalidTokenError(f"Неизвестный kid: {kid!r}")
        return self._keys[kid]

    def _is_stale(self) -> bool:
        return self._fetched_at is None or (
            time.monotonic() - self._fetched_at >= self._ttl_seconds
        )

    async def _maybe_refetch_for_unknown_kid(self) -> None:
        now = time.monotonic()
        if (
            self._last_unknown_kid_refetch_at is not None
            and now - self._last_unknown_kid_refetch_at
            < self._unknown_kid_throttle_seconds
        ):
            return
        self._last_unknown_kid_refetch_at = now
        await self._fetch()

    async def _fetch(self) -> None:
        response = await self._http_client.get(self._jwks_path)
        response.raise_for_status()
        keys: dict[str, Any] = {
            jwk["kid"]: RSAAlgorithm.from_jwk(jwk) for jwk in response.json()["keys"]
        }
        self._keys = keys
        self._fetched_at = time.monotonic()
