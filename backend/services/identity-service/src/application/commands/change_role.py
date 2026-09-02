"""Change-user-role command and handler."""

from dataclasses import dataclass

from kernel_domain.errors import Error, ErrorType
from kernel_domain.result import Result

from domain.repositories import UserRepository
from domain.role import Role
from domain.user import User
from domain.user_id import UserId


@dataclass(frozen=True)
class ChangeUserRoleCommand:
    """DTO для смены роли пользователя."""

    target_user_id: UserId
    role: Role


class ChangeUserRoleCommandHandler:
    """Меняет роль учётной записи и сохраняет агрегат."""

    def __init__(self, users: UserRepository) -> None:
        self._users = users

    async def execute(self, command: ChangeUserRoleCommand) -> Result[User]:
        user = await self._users.get_by_id(command.target_user_id)
        if user is None:
            return Result.fail(
                Error(
                    code="user_not_found",
                    description="Пользователь не найден",
                    type=ErrorType.NOT_FOUND,
                )
            )
        result = user.change_role(command.role)
        if result.is_err:
            return Result.fail(result.error)
        await self._users.save(user)
        return Result.ok(user)
