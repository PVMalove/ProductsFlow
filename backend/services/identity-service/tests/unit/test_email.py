import pytest

from domain.value_objects.email import Email


def _email(value: str) -> Email:
    return Email.create(value).value


def test_emails_with_the_same_value_are_equal() -> None:
    assert _email("user@example.com") == _email("user@example.com")


def test_emails_with_the_same_value_hash_the_same() -> None:
    assert hash(_email("user@example.com")) == hash(_email("user@example.com"))


def test_emails_with_different_values_are_not_equal() -> None:
    assert _email("a@example.com") != _email("b@example.com")


def test_an_email_is_not_equal_to_a_bare_string() -> None:
    assert _email("user@example.com") != "user@example.com"


@pytest.mark.parametrize(
    "value", ["not-an-email", "missing-domain@", "@missing-local.com", ""]
)
def test_an_invalid_email_is_rejected(value: str) -> None:
    result = Email.create(value)

    assert result.is_err
    assert result.error.code == "invalid_email"
    assert result.error.invalid_field == "email"


def test_an_invalid_email_error_does_not_reflect_the_submitted_value() -> None:
    result = Email.create("not-an-email@")

    assert result.is_err
    assert "not-an-email@" not in result.error.description


def test_direct_construction_raises_runtime_error() -> None:
    with pytest.raises(RuntimeError):
        Email("user@example.com")
