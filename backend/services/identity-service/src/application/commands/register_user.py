"""Register-user command and handler."""

from dataclasses import dataclass

from kernel_domain.errors import Error, ErrorType
from kernel_domain.result import Result

from application.ports import PasswordHasher
from contracts.user import UserView
from domain.email import Email
from domain.raw_password import RawPassword
from domain.unit_of_work import IdentityUnitOfWork
from domain.user import User


@dataclass(frozen=True)
class RegisterUserCommand:
    """DTO для регистрации нового пользователя."""

    email: str
    password: str


class RegisterUserCommandHandler:
    """
    Business Logic Summary

    Context & Purpose: Регистрация новой учетной записи пользователя.
    Validations: Уникальность email, требования к сложности пароля.
    Side Effects: В репозитории создается новый пользователь с хешированным паролем.
    """

    def __init__(
        self, uow: IdentityUnitOfWork, password_hasher: PasswordHasher
    ) -> None:
        self._uow = uow
        self._password_hasher = password_hasher

    async def execute(self, command: RegisterUserCommand) -> Result[UserView]:
        async with self._uow:
            email = Email(command.email)
            if await self._uow.users.exists_by_email(email):
                return Result[UserView].fail(
                    Error(
                        code="email_already_registered",
                        description=f"Email {command.email!r} уже зарегистрирован",
                        type=ErrorType.CONFLICT,
                    )
                )
            password = RawPassword.create(command.password)
            if password.is_err:
                return Result[UserView].fail(password.error)
            result = User.register(
                email, self._password_hasher.hash(password.value.value)
            )
            if result.is_err:
                return Result[UserView].fail(result.error)
            await self._uow.users.add(result.value)
            await self._uow.commit()
            return Result[UserView].ok(UserView.from_user(result.value))
