"""Команда и handler register-user."""

from dataclasses import dataclass

from kernel_domain.errors import Error, ErrorList
from kernel_domain.result import Result

from application.ports import PasswordHasher
from contracts.user import UserView
from domain.entities.user import User
from domain.errors import IdentityErrors
from domain.unit_of_work import IdentityUnitOfWork
from domain.value_objects.email import Email
from domain.value_objects.raw_password import RawPassword


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
            email_result = Email.create(command.email)
            password_result = RawPassword.create(command.password)

            validation_errors: list[Error] = []
            if email_result.is_err:
                validation_errors.append(email_result.error)
            if password_result.is_err:
                validation_errors.append(password_result.error)
            if validation_errors:
                return Result[UserView].fail(ErrorList.of(validation_errors))

            email = email_result.value
            password = password_result.value
            if await self._uow.users.exists_by_email(email):
                return Result[UserView].fail(IdentityErrors.email_already_registered())

            result = User.register(email, self._password_hasher.hash(password.value))
            if result.is_err:
                return Result[UserView].fail(result.error)
            await self._uow.users.add(result.value)
            await self._uow.commit()
            return Result[UserView].ok(UserView.from_user(result.value))
