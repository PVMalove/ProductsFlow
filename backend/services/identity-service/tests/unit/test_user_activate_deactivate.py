from domain.email import Email
from domain.events import Activated, Deactivated
from domain.role import Role
from domain.user import User
from domain.user_id import UserId


def _user(*, is_active: bool) -> User:
    return User(
        UserId.generate(),
        email=Email("user@example.com"),
        password_hash="some-hash",
        role=Role.USER,
        is_active=is_active,
    )


def test_deactivate_an_active_user_succeeds_and_pulls_a_deactivated_event() -> None:
    user = _user(is_active=True)

    result = user.deactivate()

    assert result.is_ok
    assert user.is_active is False
    events = user.pull_events()
    assert len(events) == 1
    event = events[0]
    assert isinstance(event, Deactivated)
    assert event.user_id == user.id


def test_deactivate_an_already_deactivated_user_fails() -> None:
    user = _user(is_active=False)

    result = user.deactivate()

    assert result.is_err
    assert user.is_active is False
    assert user.pull_events() == []


def test_activate_a_deactivated_user_succeeds_and_pulls_an_activated_event() -> None:
    user = _user(is_active=False)

    result = user.activate()

    assert result.is_ok
    assert user.is_active is True
    events = user.pull_events()
    assert len(events) == 1
    event = events[0]
    assert isinstance(event, Activated)
    assert event.user_id == user.id


def test_activate_an_already_active_user_fails() -> None:
    user = _user(is_active=True)

    result = user.activate()

    assert result.is_err
    assert user.is_active is True
    assert user.pull_events() == []
