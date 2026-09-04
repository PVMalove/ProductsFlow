from domain.entities.user import User
from domain.events import Activated, Deactivated
from domain.value_objects.email import Email


def _user(*, is_active: bool) -> User:
    user = User.register(Email.create("user@example.com").value, "some-hash").value
    user.pull_events()
    if not is_active:
        user.deactivate()
        user.pull_events()
    return user


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
