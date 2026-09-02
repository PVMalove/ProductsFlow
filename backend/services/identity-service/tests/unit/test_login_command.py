from kernel_domain.errors import ErrorType

from application.login import LoginCommand, LoginCommandHandler
from application.register_user import RegisterUserCommand, RegisterUserCommandHandler
from tests.unit.fake_password_hasher import FakePasswordHasher
from tests.unit.fake_user_repository import FakeUserRepository


async def _register(repository: FakeUserRepository, hasher: FakePasswordHasher) -> None:
    await RegisterUserCommandHandler(repository, hasher).execute(
        RegisterUserCommand("user@example.com", "password1")
    )


async def test_login_succeeds_with_the_authenticated_user() -> None:
    repository = FakeUserRepository()
    hasher = FakePasswordHasher()
    await _register(repository, hasher)

    result = await LoginCommandHandler(repository, hasher).execute(
        LoginCommand("user@example.com", "password1")
    )

    assert result.is_ok
    assert result.value.email.value == "user@example.com"


async def test_login_fails_with_unauthorized_on_a_wrong_password() -> None:
    repository = FakeUserRepository()
    hasher = FakePasswordHasher()
    await _register(repository, hasher)

    result = await LoginCommandHandler(repository, hasher).execute(
        LoginCommand("user@example.com", "wrong-password")
    )

    assert result.is_err
    assert result.error.type == ErrorType.UNAUTHORIZED


async def test_login_fails_with_unauthorized_when_the_email_is_unknown() -> None:
    result = await LoginCommandHandler(
        FakeUserRepository(), FakePasswordHasher()
    ).execute(LoginCommand("nobody@example.com", "password1"))

    assert result.is_err
    assert result.error.type == ErrorType.UNAUTHORIZED


async def test_login_fails_with_unauthorized_for_an_invalid_email() -> None:
    result = await LoginCommandHandler(
        FakeUserRepository(), FakePasswordHasher()
    ).execute(LoginCommand("not-an-email", "password1"))

    assert result.is_err
    assert result.error.type == ErrorType.UNAUTHORIZED


async def test_login_rejects_a_deactivated_user() -> None:
    repository = FakeUserRepository()
    hasher = FakePasswordHasher()
    await _register(repository, hasher)
    repository.users["user@example.com"].is_active = False

    result = await LoginCommandHandler(repository, hasher).execute(
        LoginCommand("user@example.com", "password1")
    )

    assert result.is_err
    assert result.error.type == ErrorType.FORBIDDEN
