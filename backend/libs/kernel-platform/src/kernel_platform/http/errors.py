"""Structured BFF error shape + domain `Result` status mapping (ADR 0031)."""

from kernel_domain.errors import ErrorType
from pydantic import BaseModel

_STATUS_BY_ERROR_TYPE: dict[ErrorType, int] = {
    ErrorType.VALIDATION: 400,
    ErrorType.NOT_FOUND: 404,
    ErrorType.CONFLICT: 409,
    ErrorType.FORBIDDEN: 403,
    ErrorType.UNAUTHORIZED: 401,
    ErrorType.PROBLEM: 400,
    ErrorType.FAILURE: 500,
}


def status_code_for_error_type(error_type: ErrorType) -> int:
    """HTTP-статус для домейного `ErrorType` — единая таблица для всех
    сервисов, не зависящая ни от одного service-specific DTO."""
    return _STATUS_BY_ERROR_TYPE[error_type]


class ErrorBody(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    """Структурированная форма ошибки BFF-контракта: `code` — машиночитаемый,
    `message` — безопасный для показа пользователю текст без деталей
    реализации."""

    error: ErrorBody


class ApiError(Exception):
    """Ошибка, готовая к сериализации в `ErrorResponse` — то, что выбрасывают
    `match_result`/`match_created` на неуспешном `Result`. Экспонирует
    `code`/`message`/`status_code` структурно — той же формой, которой должны
    следовать ожидаемые service-исключения, перехватываемые
    `register_error_handlers`."""

    def __init__(self, *, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
