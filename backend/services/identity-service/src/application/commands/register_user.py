"""Register-user command and handler."""

from dataclasses import dataclass

from kernel_domain.errors import Error, ErrorType
from kernel_domain.result import Result

from application.ports import PasswordHasher
from domain.email import Email
from domain.raw_password import RawPassword
from domain.repositories import UserRepository
from domain.user import User


@dataclass(frozen=True)
class RegisterUserCommand:
    email: str
    password: str


class RegisterUserCommandHandler:
    def __init__(self, users: UserRepository, password_hasher: PasswordHasher) -> None:
        self._users = users
        self._password_hasher = password_hasher

    def handle(self, command: RegisterUserCommand) -> Result[User]:
        email = Email(command.email)
        if self._users.exists_by_email(email):
            return Result.fail(
                Error(
                    code="email_already_registered",
                    description=f"Email {command.email!r} уже зарегистрирован",
                    type=ErrorType.CONFLICT,
                )
            )
        password = RawPassword.create(command.password)
        if password.is_err:
            return Result.fail(password.error)
        result = User.register(email, self._password_hasher.hash(password.value.value))
        if result.is_ok:
            self._users.add(result.value)
        return result
