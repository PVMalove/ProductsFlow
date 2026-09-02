from kernel_domain.errors import ErrorType

from application.login import LoginCommand, LoginCommandHandler
from application.register_user import RegisterUserCommand, RegisterUserCommandHandler
from tests.unit.fake_password_hasher import FakePasswordHasher
from tests.unit.fake_user_repository import FakeUserRepository


def _register(repository: FakeUserRepository, hasher: FakePasswordHasher) -> None:
    RegisterUserCommandHandler(repository, hasher).execute(
        RegisterUserCommand("user@example.com", "password1")
    )


def test_login_succeeds_with_the_authenticated_user() -> None:
    repository = FakeUserRepository()
    hasher = FakePasswordHasher()
    _register(repository, hasher)

    result = LoginCommandHandler(repository, hasher).execute(
        LoginCommand("user@example.com", "password1")
    )

    assert result.is_ok
    assert result.value.email.value == "user@example.com"


def test_login_fails_with_unauthorized_on_a_wrong_password() -> None:
    repository = FakeUserRepository()
    hasher = FakePasswordHasher()
    _register(repository, hasher)

    result = LoginCommandHandler(repository, hasher).execute(
        LoginCommand("user@example.com", "wrong-password")
    )

    assert result.is_err
    assert result.error.type == ErrorType.UNAUTHORIZED


def test_login_fails_with_unauthorized_when_the_email_is_unknown() -> None:
    result = LoginCommandHandler(FakeUserRepository(), FakePasswordHasher()).execute(
        LoginCommand("nobody@example.com", "password1")
    )

    assert result.is_err
    assert result.error.type == ErrorType.UNAUTHORIZED


def test_login_rejects_a_deactivated_user() -> None:
    repository = FakeUserRepository()
    hasher = FakePasswordHasher()
    _register(repository, hasher)
    repository.users["user@example.com"].is_active = False

    result = LoginCommandHandler(repository, hasher).execute(
        LoginCommand("user@example.com", "password1")
    )

    assert result.is_err
    assert result.error.type == ErrorType.FORBIDDEN
