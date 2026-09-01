from application.commands import ActivateUserCommand, ActivateUserCommandHandler
from application.queries import GetUserQuery, GetUserQueryHandler
from application.register_user import RegisterUserCommand, RegisterUserCommandHandler
from domain.user_id import UserId
from tests.unit.fake_password_hasher import FakePasswordHasher
from tests.unit.fake_user_repository import FakeUserRepository


def test_get_user_query_reads_through_a_read_handler() -> None:
    repository = FakeUserRepository()
    registered = RegisterUserCommandHandler(repository, FakePasswordHasher()).handle(
        RegisterUserCommand("user@example.com", "password1")
    )

    result = GetUserQueryHandler(repository).handle(GetUserQuery(registered.value.id))

    assert result.is_ok
    assert result.value is registered.value


def test_get_user_query_returns_not_found_without_mutating_the_repository() -> None:
    repository = FakeUserRepository()

    result = GetUserQueryHandler(repository).handle(GetUserQuery(UserId.generate()))

    assert result.is_err
    assert result.error.code == "user_not_found"
    assert repository.users == {}


def test_activate_user_command_persists_the_aggregate_and_domain_event() -> None:
    repository = FakeUserRepository()
    user = (
        RegisterUserCommandHandler(repository, FakePasswordHasher())
        .handle(RegisterUserCommand("user@example.com", "password1"))
        .value
    )
    user.pull_events()
    user.is_active = False

    result = ActivateUserCommandHandler(repository).handle(
        ActivateUserCommand(target_user_id=user.id)
    )

    assert result.is_ok
    assert repository.get_by_id(user.id) is user
    assert user.is_active is True
    assert user.pull_events()[0].__class__.__name__ == "Activated"
