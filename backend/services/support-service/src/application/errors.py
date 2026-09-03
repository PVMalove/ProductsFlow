# ruff: noqa: E501
from http import HTTPStatus


class ApplicationError(Exception):
    """Base class for expected failures at the application boundary.

    Exposes `code`, `message`, and `status_code` structurally (ADR 0031) so
    kernel_platform's exception handler can translate it into the BFF error
    shape without importing this service's exception classes."""

    code: str
    message: str
    status_code: int

    def __init__(self) -> None:
        super().__init__(self.message)


class TicketListCursorConflictError(ApplicationError):
    """Both `after` and `before` pagination cursors were supplied together."""

    code = "TICKET_LIST_CURSOR_CONFLICT"
    message = "Нельзя одновременно указать after и before"
    status_code = HTTPStatus.BAD_REQUEST


class TicketListInvalidCursorError(ApplicationError):
    """A pagination cursor could not be decoded."""

    code = "TICKET_LIST_INVALID_CURSOR"
    message = "Некорректный курсор пагинации"
    status_code = HTTPStatus.BAD_REQUEST
