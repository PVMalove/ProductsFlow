from kernel_domain.errors import ErrorType

from identity.domain.raw_password import RawPassword


def test_raw_passwords_with_the_same_value_are_equal() -> None:
    assert RawPassword("password1") == RawPassword("password1")


def test_raw_passwords_with_the_same_value_hash_the_same() -> None:
    assert hash(RawPassword("password1")) == hash(RawPassword("password1"))


def test_raw_passwords_with_different_values_are_not_equal() -> None:
    assert RawPassword("password1") != RawPassword("password2")


def test_create_succeeds_with_a_strong_password() -> None:
    result = RawPassword.create("password1")

    assert result.is_ok
    assert result.value == RawPassword("password1")


def test_create_rejects_a_password_shorter_than_eight_characters() -> None:
    result = RawPassword.create("abc1")

    assert result.is_err
    assert result.error.type == ErrorType.VALIDATION
    assert result.error.code == "password_too_short"


def test_create_rejects_a_password_without_a_lowercase_letter() -> None:
    result = RawPassword.create("PASSWORD1")

    assert result.is_err
    assert result.error.type == ErrorType.VALIDATION
    assert result.error.code == "password_missing_lowercase"


def test_create_rejects_a_password_without_a_digit() -> None:
    result = RawPassword.create("password")

    assert result.is_err
    assert result.error.type == ErrorType.VALIDATION
    assert result.error.code == "password_missing_digit"
