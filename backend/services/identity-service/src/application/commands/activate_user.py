"""Команда и handler activate-user."""

import logging
from dataclasses import dataclass

from kernel_domain.result import Result

from contracts.user import UserView
from domain.errors import IdentityErrors
from domain.unit_of_work import IdentityUnitOfWork
from domain.value_objects.user_id import UserId

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ActivateUserCommand:
    """DTO для активации пользователя."""

    target_user_id: UserId


class ActivateUserCommandHandler:
    """Активирует деактивированную учётную запись и сохраняет агрегат."""

    def __init__(self, uow: IdentityUnitOfWork) -> None:
        self._uow = uow

    async def execute(self, command: ActivateUserCommand) -> Result[UserView]:
        async with self._uow:
            user = await self._uow.users.get_by_id(command.target_user_id)
            if user is None:
                logger.warning(
                    "Активация отклонена: пользователь не найден user_id=%s",
                    command.target_user_id.value,
                )
                return Result[UserView].fail(IdentityErrors.user_not_found())
            result = user.activate()
            if result.is_err:
                logger.warning(
                    "Активация отклонена: user_id=%s code=%s",
                    command.target_user_id.value,
                    result.error.code,
                )
                return Result[UserView].fail(result.error)
            await self._uow.users.save(user)
            await self._uow.commit()
            logger.info(
                "Пользователь активирован: user_id=%s", command.target_user_id.value
            )
            return Result[UserView].ok(UserView.from_user(user))
