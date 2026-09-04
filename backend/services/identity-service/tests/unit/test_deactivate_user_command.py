from kernel_domain.errors import ErrorType

from application.deactivate_user import (
    DeactivateUserCommand,
    DeactivateUserCommandHandler,
)
from application.register_user import RegisterUserCommand, RegisterUserCommandHandler
from domain.entities.user import User
from domain.events import Deactivated
from tests.unit.fake_identity_unit_of_work import FakeIdentityUnitOfWork
from tests.unit.fake_password_hasher import FakePasswordHasher
from tests.unit.fake_user_repository import FakeUserRepository


async def _register(
    repository: FakeUserRepository, hasher: FakePasswordHasher, email: str
) -> User:
    handler = RegisterUserCommandHandler(FakeIdentityUnitOfWork(repository), hasher)
    await handler.execute(RegisterUserCommand(email, "password1"))
    return repository.users[email]


async def test_deactivate_rejects_an_actor_deactivating_themself() -> None:
    repository = FakeUserRepository()
    hasher = FakePasswordHasher()
    user = await _register(repository, hasher, "user@example.com")

    handler = DeactivateUserCommandHandler(FakeIdentityUnitOfWork(repository))
    result = await handler.execute(
        DeactivateUserCommand(target_user_id=user.id, actor_user_id=user.id)
    )

    assert result.is_err
    assert result.error.type == ErrorType.FORBIDDEN
    assert user.is_active is True


async def test_deactivate_happy_path_delegates_to_the_aggregate_and_persists() -> None:
    repository = FakeUserRepository()
    hasher = FakePasswordHasher()
    target = await _register(repository, hasher, "target@example.com")
    target.pull_events()
    actor = await _register(repository, hasher, "actor@example.com")

    handler = DeactivateUserCommandHandler(FakeIdentityUnitOfWork(repository))
    result = await handler.execute(
        DeactivateUserCommand(target_user_id=target.id, actor_user_id=actor.id)
    )

    assert result.is_ok
    assert result.value.is_active is False
    persisted = await repository.get_by_id(target.id)
    assert persisted is not None
    assert persisted.is_active is False
    events = target.pull_events()
    assert len(events) == 1
    assert isinstance(events[0], Deactivated)
