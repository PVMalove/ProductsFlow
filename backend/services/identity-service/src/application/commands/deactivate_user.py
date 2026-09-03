"""Activation and deactivation commands and handlers."""

from dataclasses import dataclass

from kernel_domain.errors import Error, ErrorType
from kernel_domain.result import Result

from application.commands.activate_user import (
    ActivateUserCommand,
    ActivateUserCommandHandler,
)
from domain.repositories import UserRepository
from domain.user import User
from domain.user_id import UserId


@dataclass(frozen=True)
class DeactivateUserCommand:
    target_user_id: UserId
    actor_user_id: UserId


class DeactivateUserCommandHandler:
    def __init__(self, users: UserRepository) -> None:
        self._users = users

    async def execute(self, command: DeactivateUserCommand) -> Result[User]:
        if command.target_user_id == command.actor_user_id:
            return Result[User].fail(
                Error(
                    code="cannot_deactivate_self",
                    description="Пользователь не может деактивировать самого себя",
                    type=ErrorType.FORBIDDEN,
                )
            )
        user = await self._users.get_by_id(command.target_user_id)
        if user is None:
            return Result[User].fail(
                Error(
                    code="user_not_found",
                    description="Пользователь не найден",
                    type=ErrorType.NOT_FOUND,
                )
            )
        result = user.deactivate()
        if result.is_err:
            return Result[User].fail(result.error)
        await self._users.save(user)
        return Result[User].ok(user)


__all__ = [
    "ActivateUserCommand",
    "ActivateUserCommandHandler",
    "DeactivateUserCommand",
    "DeactivateUserCommandHandler",
]
