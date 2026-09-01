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
    email: str
    password: str


class LoginCommandHandler:
    def __init__(self, users: UserRepository, password_hasher: PasswordHasher) -> None:
        self._users = users
        self._password_hasher = password_hasher

    def handle(self, command: LoginCommand) -> Result[User]:
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
