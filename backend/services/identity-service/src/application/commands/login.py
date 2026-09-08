"""Команда и handler логина."""

import logging
from dataclasses import dataclass

from kernel_domain.result import Result

from application.ports import PasswordHasher
from domain.entities.user import User
from domain.errors import IdentityErrors
from domain.unit_of_work import IdentityUnitOfWork
from domain.value_objects.email import Email

logger = logging.getLogger(__name__)


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

    def __init__(
        self, uow: IdentityUnitOfWork, password_hasher: PasswordHasher
    ) -> None:
        self._uow = uow
        self._password_hasher = password_hasher

    async def execute(self, command: LoginCommand) -> Result[User]:
        async with self._uow:
            email_result = Email.create(command.email)
            if email_result.is_err:
                logger.warning("Вход отклонён: неверные учётные данные")
                return Result[User].fail(IdentityErrors.invalid_credentials())
            user = await self._uow.users.get_by_email(email_result.value)
            if user is None or not self._password_hasher.verify(
                command.password, user.password_hash
            ):
                logger.warning("Вход отклонён: неверные учётные данные")
                return Result[User].fail(IdentityErrors.invalid_credentials())
            if not user.is_active:
                logger.warning(
                    "Вход отклонён: учётная запись деактивирована user_id=%s",
                    user.id.value,
                )
                return Result[User].fail(IdentityErrors.user_deactivated())
            await self._uow.commit()
            logger.info("Успешный вход: user_id=%s", user.id.value)
            return Result[User].ok(user)
