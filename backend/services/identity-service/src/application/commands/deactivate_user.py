"""Команды и хендлеры активации и деактивации."""

import logging
from dataclasses import dataclass

from kernel_domain.result import Result

from application.commands.activate_user import (
    ActivateUserCommand,
    ActivateUserCommandHandler,
)
from contracts.user import UserView
from domain.errors import IdentityErrors
from domain.unit_of_work import IdentityUnitOfWork
from domain.value_objects.user_id import UserId

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DeactivateUserCommand:
    target_user_id: UserId
    actor_user_id: UserId


class DeactivateUserCommandHandler:
    def __init__(self, uow: IdentityUnitOfWork) -> None:
        self._uow = uow

    async def execute(self, command: DeactivateUserCommand) -> Result[UserView]:
        async with self._uow:
            if command.target_user_id == command.actor_user_id:
                logger.warning(
                    "Деактивация отклонена: попытка деактивировать себя user_id=%s",
                    command.actor_user_id.value,
                )
                return Result[UserView].fail(IdentityErrors.cannot_deactivate_self())
            user = await self._uow.users.get_by_id(command.target_user_id)
            if user is None:
                logger.warning(
                    "Деактивация отклонена: пользователь не найден user_id=%s",
                    command.target_user_id.value,
                )
                return Result[UserView].fail(IdentityErrors.user_not_found())
            result = user.deactivate()
            if result.is_err:
                logger.warning(
                    "Деактивация отклонена: user_id=%s code=%s",
                    command.target_user_id.value,
                    result.error.code,
                )
                return Result[UserView].fail(result.error)
            await self._uow.users.save(user)
            await self._uow.commit()
            logger.info(
                "Пользователь деактивирован: user_id=%s actor_id=%s",
                command.target_user_id.value,
                command.actor_user_id.value,
            )
            return Result[UserView].ok(UserView.from_user(user))


__all__ = [
    "ActivateUserCommand",
    "ActivateUserCommandHandler",
    "DeactivateUserCommand",
    "DeactivateUserCommandHandler",
]
