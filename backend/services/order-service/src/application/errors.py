# ruff: noqa: E501
"""Базовый класс и подклассы ожидаемых application-исключений order-service
(ADR 0003, issue #369). Мирует catalog's разделение (архитектурный бриф D7):
доменные бизнес-правила (`quantity <= 0`) идут через `Result.fail(...)`,
«строка не найдена» / «строка не твоя» — через эти `ApplicationError`
подклассы, брошенные из handler'а."""

from http import HTTPStatus


class ApplicationError(Exception):
    """Структурно экспонирует `code`, `message` и `status_code`, чтобы
    exception handler `kernel_platform` мог транслировать её в форму BFF-
    ошибки, не импортируя классы исключений этого сервиса."""

    code: str
    message: str
    status_code: int

    def __init__(self) -> None:
        super().__init__(self.message)


class CartLineNotFoundError(ApplicationError):
    """`line_id` не существует вовсе (D5/D7)."""

    code = "CART_LINE_NOT_FOUND"
    message = "Строка корзины не найдена"
    status_code = HTTPStatus.NOT_FOUND


class CartAccessDeniedError(ApplicationError):
    """`line_id` существует, но принадлежит другому пользователю (D5/D7)."""

    code = "CART_ACCESS_DENIED"
    message = "Нет прав на эту строку корзины"
    status_code = HTTPStatus.FORBIDDEN
