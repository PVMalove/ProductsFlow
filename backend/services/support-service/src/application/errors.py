# ruff: noqa: E501
from http import HTTPStatus


class ApplicationError(Exception):
    """Базовый класс ожидаемых отказов на границе application-слоя.

    Структурно экспонирует `code`, `message` и `status_code` (ADR 0003), чтобы
    exception handler `kernel_platform` мог транслировать её в форму BFF-ошибки,
    не импортируя классы исключений этого сервиса."""

    code: str
    message: str
    status_code: int

    def __init__(self) -> None:
        super().__init__(self.message)


class TicketListCursorConflictError(ApplicationError):
    """Курсоры пагинации `after` и `before` переданы одновременно."""

    code = "TICKET_LIST_CURSOR_CONFLICT"
    message = "Нельзя одновременно указать after и before"
    status_code = HTTPStatus.BAD_REQUEST


class TicketListInvalidCursorError(ApplicationError):
    """Курсор пагинации не удалось декодировать."""

    code = "TICKET_LIST_INVALID_CURSOR"
    message = "Некорректный курсор пагинации"
    status_code = HTTPStatus.BAD_REQUEST
