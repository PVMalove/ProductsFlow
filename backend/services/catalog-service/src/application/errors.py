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


class ProductNotFoundError(ApplicationError):
    """Запрошенный товар не существует или не виден."""

    code = "PRODUCT_NOT_FOUND"
    message = "Товар не найден"
    status_code = HTTPStatus.NOT_FOUND


class ProductAccessDeniedError(ApplicationError):
    """Actor не имеет права выполнить запрошенную операцию над товаром."""

    code = "PRODUCT_ACCESS_DENIED"
    message = "Нет прав на этот товар"
    status_code = HTTPStatus.FORBIDDEN


class ProductImageNotFoundError(ApplicationError):
    """Товар виден, но у него нет записи картинки."""

    code = "PRODUCT_IMAGE_NOT_FOUND"
    message = "У товара нет картинки!"
    status_code = HTTPStatus.NOT_FOUND


class IdentityUnavailableError(ApplicationError):
    """identity-service не смог ответить на запрос авторизации."""

    code = "IDENTITY_UNAVAILABLE"
    message = "identity-service недоступен"
    status_code = HTTPStatus.SERVICE_UNAVAILABLE


class ProductListCursorConflictError(ApplicationError):
    """Курсоры пагинации `after` и `before` переданы одновременно."""

    code = "PRODUCT_LIST_CURSOR_CONFLICT"
    message = "Нельзя одновременно указать after и before"
    status_code = HTTPStatus.BAD_REQUEST


class ProductListInvalidCursorError(ApplicationError):
    """Курсор пагинации не удалось декодировать."""

    code = "PRODUCT_LIST_INVALID_CURSOR"
    message = "Некорректный курсор пагинации"
    status_code = HTTPStatus.BAD_REQUEST


class ProductImageUnsupportedMediaTypeError(ApplicationError):
    """Тип содержимого загруженной картинки не входит в число допустимых форматов."""

    code = "PRODUCT_IMAGE_UNSUPPORTED_MEDIA_TYPE"
    message = "Допустимы только JPEG, PNG, WEBP форматы"
    status_code = HTTPStatus.UNSUPPORTED_MEDIA_TYPE


class ProductImageTooLargeError(ApplicationError):
    """Загруженная картинка превышает максимально допустимый размер."""

    code = "PRODUCT_IMAGE_TOO_LARGE"
    message = "Файл больше 5 МБ"
    status_code = HTTPStatus.REQUEST_ENTITY_TOO_LARGE
