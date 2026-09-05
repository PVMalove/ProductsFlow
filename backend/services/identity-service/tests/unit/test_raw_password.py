import pytest
from kernel_domain.errors import ErrorList, ErrorType

from domain.value_objects.raw_password import RawPassword


def _password(value: str) -> RawPassword:
    return RawPassword.create(value).value


def test_raw_passwords_with_the_same_value_are_equal() -> None:
    assert _password("password1") == _password("password1")


def test_raw_passwords_with_the_same_value_hash_the_same() -> None:
    assert hash(_password("password1")) == hash(_password("password1"))


def test_raw_passwords_with_different_values_are_not_equal() -> None:
    assert _password("password1") != _password("password2")


def test_create_succeeds_with_a_strong_password() -> None:
    result = RawPassword.create("password1")

    assert result.is_ok
    assert result.value == _password("password1")


def test_create_rejects_a_password_shorter_than_eight_characters() -> None:
    result = RawPassword.create("abc1")

    assert result.is_err
    assert result.error.type == ErrorType.VALIDATION
    assert result.error.code == "password_too_short"
    assert result.error.invalid_field == "password"


def test_create_rejects_a_password_without_a_lowercase_letter() -> None:
    result = RawPassword.create("PASSWORD1")

    assert result.is_err
    assert result.error.type == ErrorType.VALIDATION
    assert result.error.code == "password_missing_lowercase"
    assert result.error.invalid_field == "password"


def test_create_rejects_a_password_without_a_digit() -> None:
    result = RawPassword.create("password")

    assert result.is_err
    assert result.error.type == ErrorType.VALIDATION
    assert result.error.code == "password_missing_digit"
    assert result.error.invalid_field == "password"


def test_create_accumulates_independent_password_violations() -> None:
    result = RawPassword.create("abc")

    assert result.is_err
    error = result.error
    assert isinstance(error, ErrorList)
    assert error.type is ErrorType.VALIDATION
    assert [child.code for child in error.errors] == [
        "password_too_short",
        "password_missing_digit",
    ]
    assert all(child.invalid_field == "password" for child in error.errors)


def test_direct_construction_raises_runtime_error() -> None:
    with pytest.raises(RuntimeError):
        RawPassword("password1")
