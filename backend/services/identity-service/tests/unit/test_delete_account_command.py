from kernel_domain.errors import ErrorType

from application.commands.delete_account import (
    DeleteAccountCommand,
    DeleteAccountCommandHandler,
)
from application.commands.register_user import (
    RegisterUserCommand,
    RegisterUserCommandHandler,
)
from domain.value_objects.user_id import UserId
from tests.unit.fake_identity_unit_of_work import FakeIdentityUnitOfWork
from tests.unit.fake_password_hasher import FakePasswordHasher
from tests.unit.fake_user_repository import FakeUserRepository


async def _register(repository: FakeUserRepository, email: str) -> UserId:
    result = await RegisterUserCommandHandler(
        FakeIdentityUnitOfWork(repository), FakePasswordHasher()
    ).execute(RegisterUserCommand(email, "password1"))
    return UserId.create(result.value.id)


async def test_delete_account_happy_path_anonymizes_and_persists() -> None:
    repository = FakeUserRepository()
    user_id = await _register(repository, "user@example.com")

    handler = DeleteAccountCommandHandler(FakeIdentityUnitOfWork(repository))
    result = await handler.execute(DeleteAccountCommand(user_id=user_id))

    assert result.is_ok
    persisted = await repository.get_by_id(user_id)
    assert persisted is not None
    assert persisted.is_deleted is True
    assert persisted.is_active is False
    assert persisted.email.value != "user@example.com"


async def test_delete_account_fails_with_not_found_for_an_unknown_user() -> None:
    repository = FakeUserRepository()

    handler = DeleteAccountCommandHandler(FakeIdentityUnitOfWork(repository))
    result = await handler.execute(DeleteAccountCommand(user_id=UserId.new_id()))

    assert result.is_err
    assert result.error.type == ErrorType.NOT_FOUND


async def test_delete_account_twice_fails_with_conflict() -> None:
    repository = FakeUserRepository()
    user_id = await _register(repository, "user@example.com")
    handler = DeleteAccountCommandHandler(FakeIdentityUnitOfWork(repository))
    await handler.execute(DeleteAccountCommand(user_id=user_id))

    result = await handler.execute(DeleteAccountCommand(user_id=user_id))

    assert result.is_err
    assert result.error.type == ErrorType.CONFLICT
