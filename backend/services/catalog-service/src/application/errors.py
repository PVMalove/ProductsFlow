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


class ProductNotFoundError(ApplicationError):
    """The requested product does not exist or is not visible."""

    code = "PRODUCT_NOT_FOUND"
    message = "Товар не найден"
    status_code = HTTPStatus.NOT_FOUND


class ProductAccessDeniedError(ApplicationError):
    """The actor is not allowed to perform the requested product operation."""

    code = "PRODUCT_ACCESS_DENIED"
    message = "Нет прав на этот товар"
    status_code = HTTPStatus.FORBIDDEN


class ProductImageNotFoundError(ApplicationError):
    """The product is visible, but has no image record."""

    code = "PRODUCT_IMAGE_NOT_FOUND"
    message = "У товара нет картинки!"
    status_code = HTTPStatus.NOT_FOUND


class IdentityUnavailableError(ApplicationError):
    """The identity service could not answer an authorization query."""

    code = "IDENTITY_UNAVAILABLE"
    message = "identity-service недоступен"
    status_code = HTTPStatus.SERVICE_UNAVAILABLE


class ProductListCursorConflictError(ApplicationError):
    """Both `after` and `before` pagination cursors were supplied together."""

    code = "PRODUCT_LIST_CURSOR_CONFLICT"
    message = "Нельзя одновременно указать after и before"
    status_code = HTTPStatus.BAD_REQUEST


class ProductListInvalidCursorError(ApplicationError):
    """A pagination cursor could not be decoded."""

    code = "PRODUCT_LIST_INVALID_CURSOR"
    message = "Некорректный курсор пагинации"
    status_code = HTTPStatus.BAD_REQUEST
