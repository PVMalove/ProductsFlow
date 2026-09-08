"""Команда и handler delete-own-account."""

import logging
from dataclasses import dataclass

from kernel_domain.result import Result

from domain.errors import IdentityErrors
from domain.unit_of_work import IdentityUnitOfWork
from domain.value_objects.user_id import UserId

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DeleteAccountCommand:
    """DTO для самостоятельного удаления учётной записи."""

    user_id: UserId


class DeleteAccountCommandHandler:
    """Заменяет учётную запись анонимизированным tombstone (ADR 0007)."""

    def __init__(self, uow: IdentityUnitOfWork) -> None:
        self._uow = uow

    async def execute(self, command: DeleteAccountCommand) -> Result[None]:
        async with self._uow:
            user = await self._uow.users.get_by_id(command.user_id)
            if user is None:
                logger.warning(
                    "Удаление аккаунта отклонено: пользователь не найден user_id=%s",
                    command.user_id.value,
                )
                return Result[None].fail(IdentityErrors.user_not_found())
            result = user.delete()
            if result.is_err:
                logger.warning(
                    "Удаление аккаунта отклонено: user_id=%s code=%s",
                    command.user_id.value,
                    result.error.code,
                )
                return Result[None].fail(result.error)
            await self._uow.users.save(user)
            await self._uow.commit()
            logger.info("Аккаунт удалён (tombstone): user_id=%s", command.user_id.value)
            return Result[None].ok(None)
