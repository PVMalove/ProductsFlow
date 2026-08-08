from typing import Any, Dict, List

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

VALIDATION_MESSAGES: Dict[tuple[str, str], str] = {
    ("name", "string_type"): "Название продукта должно быть строкой",
    ("name", "string_too_short"): "Название продукта слишком короткое",
    ("name", "string_too_long"): "Название продукта слишком длинное",
    ("category", "string_type"): "Категория продукта должна быть строкой",
    ("category", "string_too_short"): "Категория продукта слишком короткая",
    ("category", "string_too_long"): "Категория продукта слишком длинная",
    ("price", "greater_than_equal"): "Цена продукта должна быть положительным числом",
    ("product_id", "greater_than"): "ID продукта должен быть положительным числом",
}


async def validation_exception_handler(
    _request: Request,
    exc: Exception,
) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    errors: List[Dict[str, Any]] = []

    for error in exc.errors():
        loc = list(error["loc"])
        field_key = ".".join(map(str, loc[1:])) if len(loc) > 1 else loc[-1]
        message = VALIDATION_MESSAGES.get((field_key, error["type"]), error["msg"])
        errors.append(
            {
                "field": field_key,
                "type": error["type"],
                "message": message,
            }
        )

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": errors},
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
