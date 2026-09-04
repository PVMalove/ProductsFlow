from application.commands.register_user import (
    RegisterUserCommand,
    RegisterUserCommandHandler,
)
from application.ports import UserReadModel
from application.queries.get_current_user import (
    GetCurrentUserHandler,
    GetCurrentUserQuery,
)
from contracts.user import UserView
from domain.role import Role
from domain.value_objects.user_id import UserId
from tests.unit.fake_identity_unit_of_work import FakeIdentityUnitOfWork
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


async def test_get_current_user_reloads_state_and_returns_a_view() -> None:
    repository = FakeUserRepository()
    registered = await RegisterUserCommandHandler(
        FakeIdentityUnitOfWork(repository), FakePasswordHasher()
    ).execute(RegisterUserCommand("user@example.com", "password1"))

    result = await GetCurrentUserHandler(ReadOnlyUserProjection(repository)).execute(
        GetCurrentUserQuery(UserId.create(registered.value.id))
    )

    assert result.is_ok
    assert result.value == UserView(
        id=registered.value.id,
        email="user@example.com",
        role=Role.USER,
        is_active=True,
    )


async def test_get_current_user_returns_not_found_for_an_unknown_actor() -> None:
    repository = FakeUserRepository()

    result = await GetCurrentUserHandler(ReadOnlyUserProjection(repository)).execute(
        GetCurrentUserQuery(UserId.new_id())
    )

    assert result.is_err
    assert result.error.code == "user_not_found"
