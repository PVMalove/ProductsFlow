from kernel_domain.errors import ErrorType

from application.change_password import (
    ChangePasswordCommand,
    ChangePasswordCommandHandler,
)
from application.register_user import RegisterUserCommand, RegisterUserCommandHandler
from domain.entities.user import User
from domain.events import PasswordChanged
from tests.unit.fake_identity_unit_of_work import FakeIdentityUnitOfWork
from tests.unit.fake_password_hasher import FakePasswordHasher
from tests.unit.fake_user_repository import FakeUserRepository


async def _register(repository: FakeUserRepository, hasher: FakePasswordHasher) -> User:
    handler = RegisterUserCommandHandler(FakeIdentityUnitOfWork(repository), hasher)
    await handler.execute(RegisterUserCommand("user@example.com", "password1"))
    return repository.users["user@example.com"]


async def test_change_password_updates_hash_and_records_event() -> None:
    repository = FakeUserRepository()
    hasher = FakePasswordHasher()
    user = await _register(repository, hasher)
    user.pull_events()

    handler = ChangePasswordCommandHandler(FakeIdentityUnitOfWork(repository), hasher)
    result = await handler.execute(
        ChangePasswordCommand(user.id, "password1", "newpassword2")
    )

    assert result.is_ok
    assert result.value.id == user.id.value
    assert user.password_hash == hasher.hash("newpassword2")
    events = user.pull_events()
    assert len(events) == 1
    event = events[0]
    assert isinstance(event, PasswordChanged)
    assert event.user_id == user.id


async def test_change_password_rejects_wrong_old_password_without_mutating() -> None:
    repository = FakeUserRepository()
    hasher = FakePasswordHasher()
    user = await _register(repository, hasher)
    original_hash = user.password_hash

    handler = ChangePasswordCommandHandler(FakeIdentityUnitOfWork(repository), hasher)
    result = await handler.execute(
        ChangePasswordCommand(user.id, "wrong-old-password", "newpassword2")
    )

    assert result.is_err
    assert result.error.type == ErrorType.UNAUTHORIZED
    assert user.password_hash == original_hash


async def test_change_password_fails_with_validation_on_a_weak_new_password() -> None:
    repository = FakeUserRepository()
    hasher = FakePasswordHasher()
    user = await _register(repository, hasher)
    original_hash = user.password_hash

    handler = ChangePasswordCommandHandler(FakeIdentityUnitOfWork(repository), hasher)
    result = await handler.execute(ChangePasswordCommand(user.id, "password1", "short"))

    assert result.is_err
    assert result.error.type == ErrorType.VALIDATION
    assert user.password_hash == original_hash


async def test_change_password_rejects_a_deactivated_user() -> None:
    repository = FakeUserRepository()
    hasher = FakePasswordHasher()
    user = await _register(repository, hasher)
    user.is_active = False

    handler = ChangePasswordCommandHandler(FakeIdentityUnitOfWork(repository), hasher)
    result = await handler.execute(
        ChangePasswordCommand(user.id, "password1", "newpassword2")
    )

    assert result.is_err
    assert result.error.type == ErrorType.FORBIDDEN
