# ruff: noqa: E501
import logging
import time
import uuid
from contextvars import Token
from typing import Any, Protocol

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from observability.context import actor_id_var, request_id_var

logger = logging.getLogger(__name__)


class TokenVerifier(Protocol):
    """Форма, совместимая с `IdentityClient.verify_token` (identity передаёт
    локальный verifier, catalog/support — `IdentityClient`, )."""

    async def verify_token(self, token: str) -> dict[str, Any]:
        """Валидирует JWT-токен и извлекает пэйлоад.

        Ожидается, что реализация сходит в кеш/сеть за JWKS, проверит подпись, срок жизни (exp) и аудиторию (aud).

        Args:
            token (str): Сырой Bearer-токен без префикса.

        Returns:
            dict[str, Any]: Декодированный пэйлоад токена.

        Raises:
            Exception: При любой проблеме с валидацией (протух, подпись кривая, сеть отвалилась)."""
        ...


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Единая точка, где `request_id`/`actor_id` попадают в контекст запроса
    и в одну access-log-строку на запрос . Middleware не знает,
    какой `TokenVerifier` ему подсунули."""

    def __init__(self, app: ASGIApp, verifier: TokenVerifier) -> None:
        """Сетапит мидлварь.

        Args:
            app (ASGIApp): Next ASGI-апп (FastAPI/Starlette).
            verifier (TokenVerifier): Зависимость для валидации токена. Может быть локальным jwt-декодером или gRPC/HTTP клиентом в identity."""
        super().__init__(app)
        self._verifier = verifier

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        """Перехватывает HTTP-запрос, биндит контекст (`request_id`, `actor_id`) и пишет access log.

        Флоу:
        1. Выцепляет `X-Request-ID` из хэдеров или генерит свежий UUIDv4. Пишет в `contextvars`.
        2. Дергает парсинг токена для инжекта `actor_id` в контекст.
        3. Засекает `perf_counter` и прокидывает запрос дальше по ASGI-пайплайну.
        4. В блоке `finally` считает `duration_ms` и пишет один жирный лог уровня INFO со всеми метриками запроса в `extra`.
        5. Откатывает `contextvars` через `reset()`, чтобы не запрачило соседние таски в том же event loop.
        6. Прошивает `X-Request-ID` в response.

        Args:
            request (Request): Входящий Starlette-реквест.
            call_next (RequestResponseEndpoint): Коллбек для вызова следующей мидлвари/роутера.

        Returns:
            Response: Отформатированный ответ, в который добавлен `X-Request-ID` хэдер."""
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        request_id_reset = request_id_var.set(request_id)
        actor_id_reset = await self._set_actor_id(request)
        started_at = time.perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            duration_ms = (time.perf_counter() - started_at) * 1000
            # x_user_id/x_user_role — сырые значения хэдеров как они дошли до
            # сервиса (в норме — пустые: gateway их зануляет, ADR 0005/issue
            # #286). Единственный способ автоматически подтвердить это
            # anti-spoofing поведение по issue #292 — их непустое значение
            # здесь сигнализирует о попытке подделки или об обходе gateway.
            logger.info(
                "%s %s request_id=%s x_user_id=%r x_user_role=%r",
                request.method,
                request.url.path,
                request_id,
                request.headers.get("x-user-id", ""),
                request.headers.get("x-user-role", ""),
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": status_code,
                    "duration_ms": duration_ms,
                },
            )
            request_id_var.reset(request_id_reset)
            if actor_id_reset is not None:
                actor_id_var.reset(actor_id_reset)

    async def _set_actor_id(self, request: Request) -> Token[int | str | None] | None:
        """Хелпер. Выковыривает токен, валидирует через `verifier` и сетит `actor_id_var`.

        Проглатывает любые эксепшены при валидации, чтобы не ронять запрос — аутентификация это забота эндпоинтов, мидлварь работает по best effort.

        Args:
            request (Request): Реквест.

        Returns:
            Token[int | str | None] | None: Токен contextvar для последующего отката, или None если нет хидера/упала валидация."""
        auth_header = request.headers.get("authorization", "")
        if not auth_header.lower().startswith("bearer "):
            return None
        try:
            payload = await self._verifier.verify_token(auth_header[7:])
            sub = payload.get("sub")
            if sub is None:
                return None
            try:
                actor_id: int | str = int(sub)
            except TypeError, ValueError:
                actor_id = str(sub)
            return actor_id_var.set(actor_id)
        except Exception:
            logger.warning("Не удалось верифицировать bearer-токен", exc_info=True)
            return None
