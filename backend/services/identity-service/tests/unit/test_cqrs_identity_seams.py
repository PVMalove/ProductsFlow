from application.commands.activate_user import (
    ActivateUserCommand,
    ActivateUserCommandHandler,
)
from application.ports import UserReadModel
from application.queries.get_user import GetUserQuery, GetUserQueryHandler
from application.register_user import RegisterUserCommand, RegisterUserCommandHandler
from domain.user_id import UserId
from tests.unit.fake_password_hasher import FakePasswordHasher
from tests.unit.fake_user_repository import FakeUserRepository


class ReadOnlyUserProjection:
    def __init__(self, repository: FakeUserRepository) -> None:
        self._repository = repository

    async def get_by_id(self, user_id: UserId) -> UserReadModel | None:
        user = await self._repository.get_by_id(user_id)
        return (
            None
            if user is None
            else UserReadModel(
                id=user.id, email=user.email, role=user.role, is_active=user.is_active
            )
        )


async def test_get_user_query_reads_through_a_read_handler() -> None:
    repository = FakeUserRepository()
    registered = await RegisterUserCommandHandler(
        repository, FakePasswordHasher()
    ).execute(RegisterUserCommand("user@example.com", "password1"))

    result = await GetUserQueryHandler(ReadOnlyUserProjection(repository)).execute(
        GetUserQuery(UserId(registered.value.id))
    )

    assert result.is_ok
    assert result.value.id.value == registered.value.id
    assert result.value.is_active is True


async def test_get_user_query_returns_not_found_without_mutating_the_repository() -> (
    None
):
    repository = FakeUserRepository()

    result = await GetUserQueryHandler(ReadOnlyUserProjection(repository)).execute(
        GetUserQuery(UserId.generate())
    )

    assert result.is_err
    assert result.error.code == "user_not_found"
    assert repository.users == {}


async def test_activate_user_command_persists_the_aggregate_and_domain_event() -> None:
    repository = FakeUserRepository()
    await RegisterUserCommandHandler(repository, FakePasswordHasher()).execute(
        RegisterUserCommand("user@example.com", "password1")
    )
    user = repository.users["user@example.com"]
    user.pull_events()
    user.is_active = False

    result = await ActivateUserCommandHandler(repository).execute(
        ActivateUserCommand(target_user_id=user.id)
    )

    assert result.is_ok
    assert result.value.is_active is True
    assert await repository.get_by_id(user.id) is user
    assert user.is_active is True
    assert user.pull_events()[0].__class__.__name__ == "Activated"
