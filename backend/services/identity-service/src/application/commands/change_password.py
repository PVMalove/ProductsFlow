"""Команда и handler change-password."""

import logging
from dataclasses import dataclass

from kernel_domain.result import Result

from application.ports import PasswordHasher
from contracts.user import UserView
from domain.errors import IdentityErrors
from domain.unit_of_work import IdentityUnitOfWork
from domain.value_objects.raw_password import RawPassword
from domain.value_objects.user_id import UserId

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ChangePasswordCommand:
    """DTO для изменения пароля пользователя."""

    user_id: UserId
    old_password: str
    new_password: str


class ChangePasswordCommandHandler:
    """
    Business Logic Summary

    Context & Purpose: Смена пароля текущего пользователя.
    Validations: Сравнение старого пароля, проверка сложности нового пароля.
    Side Effects: Пароль в репозитории обновляется (хешируется).
    """

    def __init__(
        self, uow: IdentityUnitOfWork, password_hasher: PasswordHasher
    ) -> None:
        self._uow = uow
        self._password_hasher = password_hasher

    async def execute(self, command: ChangePasswordCommand) -> Result[UserView]:
        async with self._uow:
            user = await self._uow.users.get_by_id(command.user_id)
            if user is None or not self._password_hasher.verify(
                command.old_password, user.password_hash
            ):
                logger.warning(
                    "Смена пароля отклонена: неверный текущий пароль user_id=%s",
                    command.user_id.value,
                )
                return Result[UserView].fail(IdentityErrors.old_password_mismatch())
            password = RawPassword.create(command.new_password)
            if password.is_err:
                return Result[UserView].fail(password.error)
            result = user.change_password(
                self._password_hasher.hash(password.value.value)
            )
            if result.is_err:
                logger.warning(
                    "Смена пароля отклонена: user_id=%s code=%s",
                    command.user_id.value,
                    result.error.code,
                )
                return Result[UserView].fail(result.error)
            await self._uow.users.save(user)
            await self._uow.commit()
            logger.info("Пароль изменён: user_id=%s", command.user_id.value)
            return Result[UserView].ok(UserView.from_user(user))
