from kernel_domain.errors import ErrorType

from application.register_user import RegisterUserCommand, RegisterUserCommandHandler
from domain.role import Role
from tests.unit.fake_password_hasher import FakePasswordHasher
from tests.unit.fake_user_repository import FakeUserRepository


async def test_register_persists_the_user_and_returns_ok() -> None:
    repository = FakeUserRepository()
    hasher = FakePasswordHasher()
    handler = RegisterUserCommandHandler(repository, hasher)

    result = await handler.execute(RegisterUserCommand("user@example.com", "password1"))

    assert result.is_ok
    user = result.value
    assert user.role == Role.USER
    assert user.is_active is True
    assert user.password_hash == hasher.hash("password1")
    assert repository.users["user@example.com"] is user


async def test_register_fails_with_conflict_when_email_already_exists() -> None:
    repository = FakeUserRepository()
    handler = RegisterUserCommandHandler(repository, FakePasswordHasher())
    first = await handler.execute(RegisterUserCommand("user@example.com", "password1"))
    assert first.is_ok

    second = await handler.execute(RegisterUserCommand("user@example.com", "password2"))

    assert second.is_err
    assert second.error.type == ErrorType.CONFLICT


async def test_register_does_not_construct_the_aggregate_on_a_duplicate_email() -> None:
    repository = FakeUserRepository()
    handler = RegisterUserCommandHandler(repository, FakePasswordHasher())
    await handler.execute(RegisterUserCommand("user@example.com", "password1"))
    users_before = dict(repository.users)

    await handler.execute(RegisterUserCommand("user@example.com", "password2"))

    assert repository.users == users_before


async def test_register_fails_with_validation_on_a_weak_password() -> None:
    handler = RegisterUserCommandHandler(FakeUserRepository(), FakePasswordHasher())

    result = await handler.execute(RegisterUserCommand("user@example.com", "short"))

    assert result.is_err
    assert result.error.type == ErrorType.VALIDATION


async def test_register_does_not_hash_a_weak_password() -> None:
    repository = FakeUserRepository()
    handler = RegisterUserCommandHandler(repository, FakePasswordHasher())

    await handler.execute(RegisterUserCommand("user@example.com", "short"))

    assert repository.users == {}
