from kernel_domain.errors import ErrorType

from application.register_user import RegisterUserCommand
from domain.role import Role
from tests.unit.fake_password_hasher import FakePasswordHasher
from tests.unit.fake_user_repository import FakeUserRepository


def test_register_persists_the_user_and_returns_ok() -> None:
    repository = FakeUserRepository()
    hasher = FakePasswordHasher()
    command = RegisterUserCommand(repository, hasher)

    result = command.execute("user@example.com", "password1")

    assert result.is_ok
    user = result.value
    assert user.role == Role.USER
    assert user.is_active is True
    assert user.password_hash == hasher.hash("password1")
    assert repository.users["user@example.com"] is user


def test_register_fails_with_conflict_when_email_already_exists() -> None:
    repository = FakeUserRepository()
    command = RegisterUserCommand(repository, FakePasswordHasher())
    first = command.execute("user@example.com", "password1")
    assert first.is_ok

    second = command.execute("user@example.com", "password2")

    assert second.is_err
    assert second.error.type == ErrorType.CONFLICT


def test_register_does_not_construct_the_aggregate_on_a_duplicate_email() -> None:
    repository = FakeUserRepository()
    command = RegisterUserCommand(repository, FakePasswordHasher())
    command.execute("user@example.com", "password1")
    users_before = dict(repository.users)

    command.execute("user@example.com", "password2")

    assert repository.users == users_before


def test_register_fails_with_validation_on_a_weak_password() -> None:
    command = RegisterUserCommand(FakeUserRepository(), FakePasswordHasher())

    result = command.execute("user@example.com", "short")

    assert result.is_err
    assert result.error.type == ErrorType.VALIDATION


def test_register_does_not_hash_a_weak_password() -> None:
    repository = FakeUserRepository()
    command = RegisterUserCommand(repository, FakePasswordHasher())

    command.execute("user@example.com", "short")

    assert repository.users == {}
