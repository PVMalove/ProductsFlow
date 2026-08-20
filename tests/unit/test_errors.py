import json
from unittest.mock import Mock

from fastapi.exceptions import RequestValidationError
from sqlalchemy.exc import IntegrityError

from app.errors import _integrity_exception_handler, _validation_exception_handler


async def test_validation_handler_translates_a_known_field_and_error_type():
    exc = RequestValidationError(
        [
            {
                "type": "greater_than_equal",
                "loc": ("body", "price"),
                "msg": "Input should be greater than or equal to 0",
                "input": -5,
            }
        ]
    )

    response = await _validation_exception_handler(Mock(), exc)
    error = json.loads(bytes(response.body))["detail"][0]

    assert response.status_code == 422
    assert error["field"] == "price"
    assert error["message"] == "Цена продукта должно быть положительным числом"


async def test_validation_handler_translates_the_null_not_allowed_error_type():
    exc = RequestValidationError(
        [
            {
                "type": "null_not_allowed",
                "loc": ("body", "description"),
                "msg": "это поле нельзя явно сбросить в null",
                "input": None,
            }
        ]
    )

    response = await _validation_exception_handler(Mock(), exc)
    error = json.loads(bytes(response.body))["detail"][0]

    assert error["field"] == "description"
    assert error["message"].startswith("Описание продукта нельзя явно сбросить в null")
    assert "Value error" not in error["message"]


async def test_validation_handler_falls_back_to_raw_message_for_unknown_error_type():
    exc = RequestValidationError(
        [
            {
                "type": "some_future_pydantic_error_type",
                "loc": ("body", "username"),
                "msg": "some new pydantic message",
                "input": None,
            }
        ]
    )

    response = await _validation_exception_handler(Mock(), exc)
    error = json.loads(bytes(response.body))["detail"][0]

    assert error["message"] == "username: some new pydantic message"


async def test_integrity_handler_returns_409_with_a_human_readable_message():
    exc = IntegrityError("INSERT INTO users ...", {}, Exception("duplicate key"))

    response = await _integrity_exception_handler(Mock(), exc)
    detail = json.loads(bytes(response.body))["detail"]

    assert response.status_code == 409
    assert "целостности данных" in detail
