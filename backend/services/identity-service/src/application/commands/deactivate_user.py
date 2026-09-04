"""Activation and deactivation commands and handlers."""

from dataclasses import dataclass

from kernel_domain.errors import Error, ErrorType
from kernel_domain.result import Result

from application.commands.activate_user import (
    ActivateUserCommand,
    ActivateUserCommandHandler,
)
from contracts.user import UserView
from domain.unit_of_work import IdentityUnitOfWork
from domain.value_objects.user_id import UserId


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
                return Result[UserView].fail(
                    Error(
                        code="cannot_deactivate_self",
                        description="Пользователь не может деактивировать самого себя",
                        type=ErrorType.FORBIDDEN,
                    )
                )
            user = await self._uow.users.get_by_id(command.target_user_id)
            if user is None:
                return Result[UserView].fail(
                    Error(
                        code="user_not_found",
                        description="Пользователь не найден",
                        type=ErrorType.NOT_FOUND,
                    )
                )
            result = user.deactivate()
            if result.is_err:
                return Result[UserView].fail(result.error)
            await self._uow.users.save(user)
            await self._uow.commit()
            return Result[UserView].ok(UserView.from_user(user))


__all__ = [
    "ActivateUserCommand",
    "ActivateUserCommandHandler",
    "DeactivateUserCommand",
    "DeactivateUserCommandHandler",
]
