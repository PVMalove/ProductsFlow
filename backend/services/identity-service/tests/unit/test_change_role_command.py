from kernel_domain.errors import ErrorType

from application.commands.change_role import (
    ChangeUserRoleCommand,
    ChangeUserRoleCommandHandler,
)
from application.register_user import RegisterUserCommand, RegisterUserCommandHandler
from domain.role import Role
from domain.user_id import UserId
from tests.unit.fake_password_hasher import FakePasswordHasher
from tests.unit.fake_user_repository import FakeUserRepository


async def _register(repository: FakeUserRepository, email: str) -> UserId:
    result = await RegisterUserCommandHandler(repository, FakePasswordHasher()).execute(
        RegisterUserCommand(email, "password1")
    )
    return UserId(result.value.id)


async def test_change_role_happy_path_delegates_to_the_aggregate_and_persists() -> None:
    repository = FakeUserRepository()
    user_id = await _register(repository, "user@example.com")

    result = await ChangeUserRoleCommandHandler(repository).execute(
        ChangeUserRoleCommand(target_user_id=user_id, role=Role.ADMIN)
    )

    assert result.is_ok
    assert result.value.role == Role.ADMIN
    persisted = await repository.get_by_id(user_id)
    assert persisted is not None
    assert persisted.role == Role.ADMIN


async def test_change_role_fails_with_not_found_for_an_unknown_user() -> None:
    repository = FakeUserRepository()

    result = await ChangeUserRoleCommandHandler(repository).execute(
        ChangeUserRoleCommand(target_user_id=UserId.generate(), role=Role.ADMIN)
    )

    assert result.is_err
    assert result.error.type == ErrorType.NOT_FOUND


async def test_change_role_to_the_current_role_fails_and_does_not_persist() -> None:
    repository = FakeUserRepository()
    user_id = await _register(repository, "user@example.com")

    result = await ChangeUserRoleCommandHandler(repository).execute(
        ChangeUserRoleCommand(target_user_id=user_id, role=Role.USER)
    )

    assert result.is_err
    assert result.error.type == ErrorType.CONFLICT
