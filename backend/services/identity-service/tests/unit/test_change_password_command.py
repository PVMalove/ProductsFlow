from kernel_domain.errors import ErrorType

from application.change_password import (
    ChangePasswordCommand,
    ChangePasswordCommandHandler,
)
from application.register_user import RegisterUserCommand, RegisterUserCommandHandler
from domain.events import PasswordChanged
from tests.unit.fake_password_hasher import FakePasswordHasher
from tests.unit.fake_user_repository import FakeUserRepository


def _register(repository: FakeUserRepository, hasher: FakePasswordHasher):
    return (
        RegisterUserCommandHandler(repository, hasher)
        .execute(RegisterUserCommand("user@example.com", "password1"))
        .value
    )


def test_change_password_updates_the_hash_and_pulls_a_password_changed_event() -> None:
    repository = FakeUserRepository()
    hasher = FakePasswordHasher()
    user = _register(repository, hasher)
    user.pull_events()

    result = ChangePasswordCommandHandler(repository, hasher).execute(
        ChangePasswordCommand(user.id, "password1", "newpassword2")
    )

    assert result.is_ok
    assert result.value.password_hash == hasher.hash("newpassword2")
    events = result.value.pull_events()
    assert len(events) == 1
    event = events[0]
    assert isinstance(event, PasswordChanged)
    assert event.user_id == user.id


def test_change_password_fails_without_mutating_when_the_old_password_is_wrong() -> (
    None
):
    repository = FakeUserRepository()
    hasher = FakePasswordHasher()
    user = _register(repository, hasher)
    original_hash = user.password_hash

    result = ChangePasswordCommandHandler(repository, hasher).execute(
        ChangePasswordCommand(user.id, "wrong-old-password", "newpassword2")
    )

    assert result.is_err
    assert result.error.type == ErrorType.UNAUTHORIZED
    assert user.password_hash == original_hash


def test_change_password_fails_with_validation_on_a_weak_new_password() -> None:
    repository = FakeUserRepository()
    hasher = FakePasswordHasher()
    user = _register(repository, hasher)
    original_hash = user.password_hash

    result = ChangePasswordCommandHandler(repository, hasher).execute(
        ChangePasswordCommand(user.id, "password1", "short")
    )

    assert result.is_err
    assert result.error.type == ErrorType.VALIDATION
    assert user.password_hash == original_hash


def test_change_password_rejects_a_deactivated_user() -> None:
    repository = FakeUserRepository()
    hasher = FakePasswordHasher()
    user = _register(repository, hasher)
    user.is_active = False

    result = ChangePasswordCommandHandler(repository, hasher).execute(
        ChangePasswordCommand(user.id, "password1", "newpassword2")
    )

    assert result.is_err
    assert result.error.type == ErrorType.FORBIDDEN
