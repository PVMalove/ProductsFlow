import pytest

from domain.email import Email


def test_emails_with_the_same_value_are_equal() -> None:
    assert Email("user@example.com") == Email("user@example.com")


def test_emails_with_the_same_value_hash_the_same() -> None:
    assert hash(Email("user@example.com")) == hash(Email("user@example.com"))


def test_emails_with_different_values_are_not_equal() -> None:
    assert Email("a@example.com") != Email("b@example.com")


def test_an_email_is_not_equal_to_a_bare_string() -> None:
    assert Email("user@example.com") != "user@example.com"


@pytest.mark.parametrize(
    "value", ["not-an-email", "missing-domain@", "@missing-local.com", ""]
)
def test_an_invalid_email_is_rejected(value: str) -> None:
    with pytest.raises(ValueError):
        Email(value)
