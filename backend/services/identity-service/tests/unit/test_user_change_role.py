from kernel_domain.errors import ErrorType

from domain.entities.user import User
from domain.events import RoleChanged
from domain.role import Role
from domain.value_objects.email import Email


def _user(*, role: Role) -> User:
    user = User.register(Email.create("user@example.com").value, "some-hash").value
    user.pull_events()
    if role != Role.USER:
        user.change_role(role)
        user.pull_events()
    return user


def test_change_role_updates_the_role_and_pulls_a_role_changed_event() -> None:
    user = _user(role=Role.USER)

    result = user.change_role(Role.ADMIN)

    assert result.is_ok
    assert user.role == Role.ADMIN
    events = user.pull_events()
    assert len(events) == 1
    event = events[0]
    assert isinstance(event, RoleChanged)
    assert event.user_id == user.id
    assert event.role == Role.ADMIN


def test_change_role_to_the_current_role_fails_without_mutating_the_user() -> None:
    user = _user(role=Role.ADMIN)

    result = user.change_role(Role.ADMIN)

    assert result.is_err
    assert result.error.type == ErrorType.CONFLICT
    assert user.role == Role.ADMIN
    assert user.pull_events() == []
