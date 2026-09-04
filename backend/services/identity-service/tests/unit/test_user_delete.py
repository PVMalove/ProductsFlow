from domain.entities.user import User
from domain.events import Deleted
from domain.value_objects.email import Email


def _user() -> User:
    user = User.register(Email.create("user@example.com").value, "some-hash").value
    user.pull_events()
    return user


def test_delete_anonymizes_and_pulls_a_deleted_event() -> None:
    user = _user()
    original_id = user.id

    result = user.delete()

    assert result.is_ok
    assert user.is_active is False
    assert user.is_deleted is True
    assert user.email.value != "user@example.com"
    assert user.email.value.endswith("@tombstone.invalid")
    assert user.password_hash != "some-hash"
    events = user.pull_events()
    assert len(events) == 1
    event = events[0]
    assert isinstance(event, Deleted)
    assert event.user_id == original_id


def test_delete_an_already_deleted_user_fails() -> None:
    user = _user()
    user.delete()
    user.pull_events()

    result = user.delete()

    assert result.is_err
    assert user.pull_events() == []


def test_activate_a_deleted_user_fails() -> None:
    user = _user()
    user.delete()
    user.pull_events()

    result = user.activate()

    assert result.is_err
    assert result.error.code == "user_deleted"
    assert user.is_active is False
    assert user.pull_events() == []
