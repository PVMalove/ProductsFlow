"""Команда и handler change-user-role."""

from dataclasses import dataclass

from kernel_domain.errors import Error, ErrorType
from kernel_domain.result import Result

from domain.entities.user import User
from domain.role import Role
from domain.unit_of_work import IdentityUnitOfWork
from domain.value_objects.user_id import UserId


@dataclass(frozen=True)
class ChangeUserRoleCommand:
    """DTO для смены роли пользователя."""

    target_user_id: UserId
    role: Role


class ChangeUserRoleCommandHandler:
    """Меняет роль учётной записи и сохраняет агрегат."""

    def __init__(self, uow: IdentityUnitOfWork) -> None:
        self._uow = uow

    async def execute(self, command: ChangeUserRoleCommand) -> Result[User]:
        async with self._uow:
            user = await self._uow.users.get_by_id(command.target_user_id)
            if user is None:
                return Result[User].fail(
                    Error(
                        code="user_not_found",
                        description="Пользователь не найден",
                        type=ErrorType.NOT_FOUND,
                    )
                )
            result = user.change_role(command.role)
            if result.is_err:
                return Result[User].fail(result.error)
            await self._uow.users.save(user)
            await self._uow.commit()
            return Result[User].ok(user)
