import logging
import time
import uuid
from contextvars import Token
from typing import Any, Protocol

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from kernel_platform.logging.context import actor_id_var, request_id_var

logger = logging.getLogger(__name__)


class TokenVerifier(Protocol):
    """Форма, совместимая с `IdentityClient.verify_token` (identity передаёт
    локальный verifier, catalog/support — `IdentityClient`, ADR 0016)."""

    async def verify_token(self, token: str) -> dict[str, Any]: ...


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Единая точка, где `request_id`/`actor_id` попадают в контекст запроса
    и в одну access-log-строку на запрос (ADR 0016). Middleware не знает,
    какой `TokenVerifier` ему подсунули."""

    def __init__(self, app: ASGIApp, verifier: TokenVerifier) -> None:
        super().__init__(app)
        self._verifier = verifier

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        request_id_reset = request_id_var.set(request_id)
        actor_id_reset = await self._set_actor_id(request)

        started_at = time.perf_counter()
        try:
            response = await call_next(request)
            duration_ms = (time.perf_counter() - started_at) * 1000
            response.headers["X-Request-ID"] = request_id
            logger.info(
                "%s %s",
                request.method,
                request.url.path,
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code,
                    "duration_ms": duration_ms,
                },
            )
            return response
        finally:
            request_id_var.reset(request_id_reset)
            if actor_id_reset is not None:
                actor_id_var.reset(actor_id_reset)

    async def _set_actor_id(self, request: Request) -> Token[int | None] | None:
        auth_header = request.headers.get("authorization", "")
        if not auth_header.lower().startswith("bearer "):
            return None
        try:
            payload = await self._verifier.verify_token(auth_header[7:])
            sub = payload.get("sub")
            if sub is None:
                return None
            return actor_id_var.set(int(sub))
        except Exception:
            # Терпимый паттерн ADR 0016 — сюда прилетает и невалидный
            # токен (jwt.*Error), и сбой самого TokenVerifier (например,
            # IdentityClient не смог добрать JWKS); ни один из этих
            # случаев не должен блокировать запрос — actor_id_var
            # остаётся None, авторизацию конкретного эндпоинта эта
            # прослойка не подменяет.
            logger.warning("Не удалось верифицировать bearer-токен", exc_info=True)
            return None
