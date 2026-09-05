"""Команда и handler delete-own-account."""

from dataclasses import dataclass

from kernel_domain.result import Result

from domain.errors import IdentityErrors
from domain.unit_of_work import IdentityUnitOfWork
from domain.value_objects.user_id import UserId


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
                return Result[None].fail(IdentityErrors.user_not_found())
            result = user.delete()
            if result.is_err:
                return Result[None].fail(result.error)
            await self._uow.users.save(user)
            await self._uow.commit()
            return Result[None].ok(None)
