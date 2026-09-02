from kernel_domain.errors import ErrorType

from application.deactivate_user import (
    DeactivateUserCommand,
    DeactivateUserCommandHandler,
)
from application.register_user import RegisterUserCommand, RegisterUserCommandHandler
from domain.events import Deactivated
from tests.unit.fake_password_hasher import FakePasswordHasher
from tests.unit.fake_user_repository import FakeUserRepository


def _register(repository: FakeUserRepository, hasher: FakePasswordHasher, email: str):
    return (
        RegisterUserCommandHandler(repository, hasher)
        .execute(RegisterUserCommand(email, "password1"))
        .value
    )


def test_deactivate_rejects_an_actor_deactivating_themself() -> None:
    repository = FakeUserRepository()
    hasher = FakePasswordHasher()
    user = _register(repository, hasher, "user@example.com")

    result = DeactivateUserCommandHandler(repository).execute(
        DeactivateUserCommand(target_user_id=user.id, actor_user_id=user.id)
    )

    assert result.is_err
    assert result.error.type == ErrorType.FORBIDDEN
    assert user.is_active is True


def test_deactivate_happy_path_delegates_to_the_aggregate_and_persists() -> None:
    repository = FakeUserRepository()
    hasher = FakePasswordHasher()
    target = _register(repository, hasher, "target@example.com")
    target.pull_events()
    actor = _register(repository, hasher, "actor@example.com")

    result = DeactivateUserCommandHandler(repository).execute(
        DeactivateUserCommand(target_user_id=target.id, actor_user_id=actor.id)
    )

    assert result.is_ok
    assert result.value.is_active is False
    persisted = repository.get_by_id(target.id)
    assert persisted is not None
    assert persisted.is_active is False
    events = result.value.pull_events()
    assert len(events) == 1
    assert isinstance(events[0], Deactivated)
