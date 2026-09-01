from kernel_domain.errors import ErrorType

from domain.email import Email
from domain.events import PasswordChanged
from domain.role import Role
from domain.user import User
from domain.user_id import UserId


def test_change_password_updates_the_hash_and_pulls_a_password_changed_event() -> None:
    user = User(
        UserId.generate(),
        email=Email("user@example.com"),
        password_hash="old-hash",
        role=Role.USER,
        is_active=True,
    )

    result = user.change_password("new-hash")

    assert result.is_ok
    assert user.password_hash == "new-hash"
    events = user.pull_events()
    assert len(events) == 1
    event = events[0]
    assert isinstance(event, PasswordChanged)
    assert event.user_id == user.id


def test_change_password_rejects_a_deactivated_user_without_mutating_the_hash() -> None:
    user = User(
        UserId.generate(),
        email=Email("user@example.com"),
        password_hash="old-hash",
        role=Role.USER,
        is_active=False,
    )

    result = user.change_password("new-hash")

    assert result.is_err
    assert result.error.type == ErrorType.FORBIDDEN
    assert user.password_hash == "old-hash"
    assert user.pull_events() == []
