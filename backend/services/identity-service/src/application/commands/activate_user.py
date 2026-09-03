"""Activate-user command and handler."""

from dataclasses import dataclass

from kernel_domain.errors import Error, ErrorType
from kernel_domain.result import Result

from domain.repositories import UserRepository
from domain.user import User
from domain.user_id import UserId


@dataclass(frozen=True)
class ActivateUserCommand:
    """DTO для активации пользователя."""

    target_user_id: UserId


class ActivateUserCommandHandler:
    """Активирует деактивированную учётную запись и сохраняет агрегат."""

    def __init__(self, users: UserRepository) -> None:
        self._users = users

    async def execute(self, command: ActivateUserCommand) -> Result[User]:
        user = await self._users.get_by_id(command.target_user_id)
        if user is None:
            return Result[User].fail(
                Error(
                    code="user_not_found",
                    description="Пользователь не найден",
                    type=ErrorType.NOT_FOUND,
                )
            )
        result = user.activate()
        if result.is_err:
            return Result[User].fail(result.error)
        await self._users.save(user)
        return Result[User].ok(user)
