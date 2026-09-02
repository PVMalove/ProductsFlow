"""Platform-owned FastAPI exception handlers (ADR 0031).

Нормализуют FastAPI `HTTPException`, request-validation, ожидаемые
service-исключения и неожиданные сбои в единую структурированную
`ErrorResponse`. `register_error_handlers` не импортирует ни одного
service-specific класса — исключение сервиса передаётся параметром, поэтому
kernel_platform не получает зависимость от catalog/identity/support."""

import logging
from collections.abc import Mapping
from http import HTTPStatus
from typing import Protocol, cast

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from kernel_platform.http.errors import ApiError, ErrorBody, ErrorResponse

logger = logging.getLogger(__name__)

# Канонические коды из doc/architecture/bff_api_contract.md — переопределяют
# HTTPStatus.name там, где doc называет отдельное машиночитаемое имя
# (400/422 — единый VALIDATION_ERROR, а не BAD_REQUEST/UNPROCESSABLE_ENTITY).
_CANONICAL_CODE_OVERRIDES: dict[int, str] = {
    status.HTTP_400_BAD_REQUEST: "VALIDATION_ERROR",
    status.HTTP_422_UNPROCESSABLE_CONTENT: "VALIDATION_ERROR",
}


class _StructuredError(Protocol):
    """Структурная форма, которую должно предоставлять ожидаемое
    service-исключение — код, безопасное сообщение и HTTP-статус."""

    code: str
    message: str
    status_code: int


def _canonical_code(status_code: int) -> str:
    if status_code in _CANONICAL_CODE_OVERRIDES:
        return _CANONICAL_CODE_OVERRIDES[status_code]
    try:
        return HTTPStatus(status_code).name
    except ValueError:
        return "HTTP_ERROR"


def _error_response(
    *,
    status_code: int,
    code: str,
    message: str,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    body = ErrorResponse(error=ErrorBody(code=code, message=message))
    return JSONResponse(
        status_code=status_code, content=body.model_dump(), headers=headers
    )


async def _http_exception_handler(_request: Request, exc: Exception) -> JSONResponse:
    http_exc = cast(StarletteHTTPException, exc)
    message = http_exc.detail if isinstance(http_exc.detail, str) else "Ошибка запроса"
    return _error_response(
        status_code=http_exc.status_code,
        code=_canonical_code(http_exc.status_code),
        message=message,
        headers=http_exc.headers,
    )


async def _validation_error_handler(_request: Request, _exc: Exception) -> JSONResponse:
    return _error_response(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        code="VALIDATION_ERROR",
        message="Некорректные данные запроса",
    )


async def _structured_error_handler(_request: Request, exc: Exception) -> JSONResponse:
    structured = cast(_StructuredError, exc)
    return _error_response(
        status_code=structured.status_code,
        code=structured.code,
        message=structured.message,
    )


async def _unhandled_exception_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    logger.exception(
        "Unhandled exception while processing %s", request.url, exc_info=exc
    )
    return _error_response(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        code="INTERNAL_ERROR",
        message="Внутренняя ошибка сервера",
    )


def register_error_handlers(
    app: FastAPI, *, service_error_type: type[Exception]
) -> None:
    """Регистрирует platform-owned exception handlers на FastAPI-приложении
    сервиса. `service_error_type` — базовый класс ожидаемых application-
    исключений самого сервиса (например, catalog `ApplicationError`);
    kernel_platform его не импортирует, только принимает здесь."""
    app.add_exception_handler(StarletteHTTPException, _http_exception_handler)
    app.add_exception_handler(RequestValidationError, _validation_error_handler)
    app.add_exception_handler(ApiError, _structured_error_handler)
    app.add_exception_handler(service_error_type, _structured_error_handler)
    app.add_exception_handler(Exception, _unhandled_exception_handler)
