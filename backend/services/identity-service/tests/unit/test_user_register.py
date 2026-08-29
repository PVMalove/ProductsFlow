from kernel_domain.errors import ErrorType

from identity.domain.email import Email
from identity.domain.events import UserRegistered
from identity.domain.role import Role
from identity.domain.user import User


def test_register_succeeds_with_an_active_user_role() -> None:
    result = User.register(Email("user@example.com"), "password1")

    assert result.is_ok
    user = result.value
    assert user.is_active is True
    assert user.role == Role.USER
    assert user.email == Email("user@example.com")
    assert user.password_hash == "password1"


def test_register_pulls_a_user_registered_event_with_the_new_id_and_email() -> None:
    result = User.register(Email("user@example.com"), "password1")
    user = result.value

    events = user.pull_events()

    assert len(events) == 1
    event = events[0]
    assert isinstance(event, UserRegistered)
    assert event.user_id == user.id
    assert event.email == Email("user@example.com")


def test_register_rejects_a_password_shorter_than_eight_characters() -> None:
    result = User.register(Email("user@example.com"), "abc1")

    assert result.is_err
    assert result.error.type == ErrorType.VALIDATION
    assert result.error.code == "password_too_short"


def test_register_rejects_a_password_without_a_lowercase_letter() -> None:
    result = User.register(Email("user@example.com"), "PASSWORD1")

    assert result.is_err
    assert result.error.type == ErrorType.VALIDATION
    assert result.error.code == "password_missing_lowercase"


def test_register_rejects_a_password_without_a_digit() -> None:
    result = User.register(Email("user@example.com"), "password")

    assert result.is_err
    assert result.error.type == ErrorType.VALIDATION
    assert result.error.code == "password_missing_digit"
