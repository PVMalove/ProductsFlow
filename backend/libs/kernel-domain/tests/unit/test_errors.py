# ruff: noqa: E501
from kernel_domain.errors import Error, ErrorType


def test_error_type_has_exactly_the_seven_values() -> None:
    assert {member.name for member in ErrorType} == {
        "VALIDATION",
        "NOT_FOUND",
        "CONFLICT",
        "FORBIDDEN",
        "UNAUTHORIZED",
        "PROBLEM",
        "FAILURE",
    }


def test_error_carries_code_description_and_type() -> None:
    error = Error(
        code="user.not_found",
        description="Пользователь не найден",
        type=ErrorType.NOT_FOUND,
    )

    assert error.code == "user.not_found"
    assert error.description == "Пользователь не найден"
    assert error.type is ErrorType.NOT_FOUND
