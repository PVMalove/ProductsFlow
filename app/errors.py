from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

logger = logging.getLogger(__name__)


# Человекочитаемые имена полей (именительный падеж, для подстановки в шаблоны).
# Ключ — это "путь" поля, собранный из loc (например "price" или "items.price"
# для вложенных моделей).
FIELD_NAMES: dict[str, str] = {
    "name": "Название продукта",
    "category": "Категория продукта",
    "price": "Цена продукта",
    "product_id": "ID продукта",
    "limit": "Лимит выборки",
}

# Шаблоны сообщений по типу ошибки Pydantic v2 (error["type"]).
# {field} подставляется из FIELD_NAMES (или из самого field_key, если имени нет).
ERROR_TEMPLATES: dict[str, str] = {
    "string_type": "{field} должно быть строкой",
    "string_too_short": "{field} слишком короткое",
    "string_too_long": "{field} слишком длинное",
    "greater_than_equal": "{field} должно быть положительным числом",
    "greater_than": "{field} должно быть положительным числом",
    "less_than_equal": "{field} превышает допустимое значение",
    "less_than": "{field} превышает допустимое значение",
    "missing": "{field} обязательно для заполнения",
    "int_parsing": "{field} должно быть целым числом",
    "float_parsing": "{field} должно быть числом",
}

# Дефолтный шаблон, если для типа ошибки нет перевода — используем оригинальное
# сообщение Pydantic, но хотя бы подставляем понятное имя поля.
FALLBACK_TEMPLATE = "{field}: {msg}"

# Контейнеры loc, которые мы ожидаем как первый элемент.
# Если придёт что-то другое — это сигнал, что предположение о структуре loc
# больше не верно (например, изменилась версия FastAPI/Pydantic).
KNOWN_LOC_ROOTS = {"body", "query", "path", "header", "cookie"}


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(RequestValidationError, _validation_exception_handler)
    app.add_exception_handler(IntegrityError, _integrity_exception_handler)


async def _validation_exception_handler(
    _request: Request,
    exc: Exception,
) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)

    raw_errors = exc.errors()
    logger.debug("Validation failed: %s", raw_errors)

    errors: list[dict[str, str]] = []
    for error in raw_errors:
        field_key = _build_field_key(tuple(error["loc"]))
        message = _build_message(field_key, error["type"], error["msg"])
        errors.append(
            {
                "field": field_key,
                "type": error["type"],
                "message": message,
            }
        )

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={"detail": errors},
    )


async def _integrity_exception_handler(
    _request: Request,
    exc: Exception,
) -> JSONResponse:
    assert isinstance(exc, IntegrityError)

    logger.debug("Integrity error: %s", exc)

    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={
            "detail": "Ошибка целостности данных. Возможно, нарушено уникальное "
            "ограничение или внешний ключ."
        },
    )


def _build_field_key(loc: tuple[Any, ...]) -> str:
    """
    Собирает ключ поля из loc.
    """
    if not loc:
        return "unknown"

    root, *rest = loc

    if root not in KNOWN_LOC_ROOTS:
        logger.warning("Unexpected validation error loc root: %r", loc)
        return ".".join(map(str, loc))

    if not rest:
        return str(root)

    return ".".join(map(str, rest))


def _build_message(field_key: str, error_type: str, raw_msg: str) -> str:
    field_label = FIELD_NAMES.get(field_key, field_key)
    template = ERROR_TEMPLATES.get(error_type, FALLBACK_TEMPLATE)
    return template.format(field=field_label, msg=raw_msg)
