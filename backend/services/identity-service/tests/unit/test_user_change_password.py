from kernel_domain.errors import ErrorType

from domain.entities.user import User
from domain.events import PasswordChanged
from domain.value_objects.email import Email


def _user(*, is_active: bool) -> User:
    user = User.register(Email.create("user@example.com").value, "old-hash").value
    user.pull_events()
    if not is_active:
        user.deactivate()
        user.pull_events()
    return user


def test_change_password_updates_the_hash_and_pulls_a_password_changed_event() -> None:
    user = _user(is_active=True)

    result = user.change_password("new-hash")

    assert result.is_ok
    assert user.password_hash == "new-hash"
    events = user.pull_events()
    assert len(events) == 1
    event = events[0]
    assert isinstance(event, PasswordChanged)
    assert event.user_id == user.id


def test_change_password_rejects_a_deactivated_user_without_mutating_the_hash() -> None:
    user = _user(is_active=False)

    result = user.change_password("new-hash")

    assert result.is_err
    assert result.error.type == ErrorType.FORBIDDEN
    assert user.password_hash == "old-hash"
    assert user.pull_events() == []
