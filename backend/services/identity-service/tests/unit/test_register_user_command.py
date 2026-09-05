from kernel_domain.errors import ErrorList, ErrorType

from application.register_user import RegisterUserCommand, RegisterUserCommandHandler
from domain.role import Role
from tests.unit.fake_identity_unit_of_work import FakeIdentityUnitOfWork
from tests.unit.fake_password_hasher import FakePasswordHasher
from tests.unit.fake_user_repository import FakeUserRepository


async def test_register_persists_the_user_and_returns_ok() -> None:
    repository = FakeUserRepository()
    hasher = FakePasswordHasher()
    uow = FakeIdentityUnitOfWork(repository)
    handler = RegisterUserCommandHandler(uow, hasher)

    result = await handler.execute(RegisterUserCommand("user@example.com", "password1"))

    assert result.is_ok
    view = result.value
    assert view.role == Role.USER
    assert view.is_active is True
    stored = repository.users["user@example.com"]
    assert stored.id.value == view.id
    assert stored.password_hash == hasher.hash("password1")
    assert uow.committed is True


async def test_register_fails_with_conflict_when_email_already_exists() -> None:
    repository = FakeUserRepository()
    handler = RegisterUserCommandHandler(
        FakeIdentityUnitOfWork(repository), FakePasswordHasher()
    )
    first = await handler.execute(RegisterUserCommand("user@example.com", "password1"))
    assert first.is_ok

    second = await handler.execute(RegisterUserCommand("user@example.com", "password2"))

    assert second.is_err
    assert second.error.type == ErrorType.CONFLICT


async def test_register_does_not_construct_the_aggregate_on_a_duplicate_email() -> None:
    repository = FakeUserRepository()
    handler = RegisterUserCommandHandler(
        FakeIdentityUnitOfWork(repository), FakePasswordHasher()
    )
    await handler.execute(RegisterUserCommand("user@example.com", "password1"))
    users_before = dict(repository.users)

    await handler.execute(RegisterUserCommand("user@example.com", "password2"))

    assert repository.users == users_before


async def test_register_fails_with_validation_on_a_weak_password() -> None:
    handler = RegisterUserCommandHandler(
        FakeIdentityUnitOfWork(FakeUserRepository()), FakePasswordHasher()
    )

    result = await handler.execute(RegisterUserCommand("user@example.com", "short"))

    assert result.is_err
    assert result.error.type == ErrorType.VALIDATION


async def test_register_does_not_hash_a_weak_password() -> None:
    repository = FakeUserRepository()
    handler = RegisterUserCommandHandler(
        FakeIdentityUnitOfWork(repository), FakePasswordHasher()
    )

    await handler.execute(RegisterUserCommand("user@example.com", "short"))

    assert repository.users == {}


async def test_register_aggregates_independent_email_and_password_violations() -> None:
    handler = RegisterUserCommandHandler(
        FakeIdentityUnitOfWork(FakeUserRepository()), FakePasswordHasher()
    )

    result = await handler.execute(RegisterUserCommand("not-an-email", "password"))

    assert result.is_err
    error = result.error
    assert isinstance(error, ErrorList)
    assert error.type is ErrorType.VALIDATION
    assert [child.code for child in error.errors] == [
        "invalid_email",
        "password_missing_digit",
    ]


async def test_register_does_not_persist_on_combined_validation_failure() -> None:
    repository = FakeUserRepository()
    uow = FakeIdentityUnitOfWork(repository)
    handler = RegisterUserCommandHandler(uow, FakePasswordHasher())

    await handler.execute(RegisterUserCommand("not-an-email", "password"))

    assert repository.users == {}
    assert uow.committed is False
