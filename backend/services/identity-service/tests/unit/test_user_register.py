from domain.email import Email
from domain.events import UserRegistered
from domain.role import Role
from domain.user import User


def test_register_succeeds_with_an_active_user_role() -> None:
    result = User.register(Email("user@example.com"), "some-password-hash")

    assert result.is_ok
    user = result.value
    assert user.is_active is True
    assert user.role == Role.USER
    assert user.email == Email("user@example.com")
    assert user.password_hash == "some-password-hash"


def test_register_pulls_a_user_registered_event_with_the_new_id_and_email() -> None:
    result = User.register(Email("user@example.com"), "some-password-hash")
    user = result.value

    events = user.pull_events()

    assert len(events) == 1
    event = events[0]
    assert isinstance(event, UserRegistered)
    assert event.user_id == user.id
    assert event.email == Email("user@example.com")


def test_user_registered_event_implements_the_outbox_contract() -> None:
    result = User.register(Email("user@example.com"), "some-password-hash")
    event = result.value.pull_events()[0]

    assert isinstance(event, UserRegistered)
    assert event.event_type == "user.registered.v1"
    assert event.aggregate_type == "User"
    assert event.aggregate_id() == result.value.id.value
    assert event.to_payload() == {
        "user_id": str(result.value.id.value),
        "email": "user@example.com",
    }
    assert event.email == Email("user@example.com")
