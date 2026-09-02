"""Login command and handler."""

from dataclasses import dataclass

from kernel_domain.errors import Error, ErrorType
from kernel_domain.result import Result

from application.ports import PasswordHasher
from domain.email import Email
from domain.repositories import UserRepository
from domain.user import User


@dataclass(frozen=True)
class LoginCommand:
    """DTO для входа пользователя в систему."""

    email: str
    password: str


class LoginCommandHandler:
    """
    Business Logic Summary

    Context & Purpose: Аутентификация пользователя и генерация токена сессии.
    Validations: Проверка валидности email и соответствия хеша пароля.
    Side Effects: Нет.
    """

    def __init__(self, users: UserRepository, password_hasher: PasswordHasher) -> None:
        self._users = users
        self._password_hasher = password_hasher

    def execute(self, command: LoginCommand) -> Result[User]:
        user = self._users.get_by_email(Email(command.email))
        if user is None or not self._password_hasher.verify(
            command.password, user.password_hash
        ):
            return Result.fail(
                Error(
                    code="invalid_credentials",
                    description="Неверный email или пароль",
                    type=ErrorType.UNAUTHORIZED,
                )
            )
        if not user.is_active:
            return Result.fail(
                Error(
                    code="user_deactivated",
                    description="Пользователь деактивирован",
                    type=ErrorType.FORBIDDEN,
                )
            )
        return Result.ok(user)
